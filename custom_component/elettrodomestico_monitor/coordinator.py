# ============================================================
# FILE:    coordinator.py
# VERSION: 5.0.0
# DESC:    Main coordinator — data update, power sharing, cycle tracking, notifications
# CHANGED: 2026-06-11
# ============================================================
"""Coordinator for Elettrodomestico Monitor v9.

Key addition vs v8: optional CONF_TRIGGER_ENTITY
  - If set, the AC binary sensor state is driven by the external entity
    (climate.*, binary_sensor.*, switch.*, input_boolean.*)
    rather than by the power threshold comparison.
  - Active = any state NOT in {off, idle, unavailable, unknown, ""}
  - Power sensor still used for kWh integration regardless.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_point_in_time,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    VACUUM_ACTIVE_STATES, VACUUM_INACTIVE_STATES,
    DOMAIN, VERSION, COORDINATOR_UPDATE_INTERVAL,
    CONF_POWER_SENSOR, CONF_SWITCH_ENTITY, CONF_TRIGGER_ENTITY,
    CONF_VACUUM_ENTITY, CONF_BATTERY_SENSOR,
    CONF_APPLIANCE_NAME, CONF_SLOT, CONF_PRESET, CONF_DEVICE_ICON,
    CONF_WORK_THRESHOLD_W, CONF_TRIGGER_DELAY_M, CONF_START_DELAY_S,
    CONF_CUSTOM_MESSAGE,
    CONF_NOTIFY_PUSH, CONF_NOTIFY_ALEXA, CONF_NOTIFY_GOOGLE,
    CONF_NOTIFY_WHATSAPP, CONF_NOTIFY_UPDATE,
    CONF_SCHEDULE_OVERRIDE, CONF_AUTO_ON_LOCAL, CONF_AUTO_OFF_LOCAL,
    CONF_INSTANCE_ID, CONF_SOURCE_UNIT, CONF_TOTAL_UNIT,
    WEEK_DAYS, EVENT_CYCLE_START, EVENT_CYCLE_END,
    SFX_NUM_SOGLIA, SFX_NUM_DELAY_OFF, SFX_NUM_DELAY_ON,
    SFX_TXT_NOME, SFX_TXT_MSG,
    SFX_TIME_AUTO_ON, SFX_TIME_AUTO_OFF,
    SFX_SW_NOTIFY_PUSH, SFX_SW_NOTIFY_ALEXA, SFX_SW_NOTIFY_GOOGLE,
    SFX_SW_NOTIFY_WHATSAPP, SFX_SW_NOTIFY_UPDATE,
    DEFAULT_THRESHOLD_W, DEFAULT_TRIGGER_DELAY_M, DEFAULT_START_DELAY_S,
    DEFAULT_SCHEDULE,
)
from .hub import get_hub_config
from .presets import get_preset
from .storage import ElettrodomesticoStorage

_LOGGER = logging.getLogger(__name__)

try:
    from .const import POWER_GROUPS_KEY
except ImportError:
    POWER_GROUPS_KEY = "power_groups"

# Safe imports for fields added in v4.40+
try:
    from .const import CONF_IMAGE_ON, CONF_IMAGE_OFF
except ImportError:
    CONF_IMAGE_ON  = "image_on"
    CONF_IMAGE_OFF = "image_off"

try:
    from .const import CONF_POWER_SENSOR_2
except ImportError:
    CONF_POWER_SENSOR_2 = "power_sensor_2"

# States considered "not active" for external trigger entities
_INACTIVE_STATES = {"off", "idle", "docked", "unavailable", "unknown", ""}


def _fmt(hours: float) -> str:
    if hours < 0: hours = 0.0
    total_m = int(round(hours * 60))
    days = total_m // 1440; rem = total_m % 1440
    h = rem // 60; m = rem % 60
    if days: return f"{days}d {h}h {m}m"
    if h:    return f"{h}h {m}m"
    return f"{m}min"


def _parse_time(t: str) -> tuple[int, int]:
    parts = (t or "").split(":")
    try: return int(parts[0]), int(parts[1])
    except (IndexError, ValueError): return 0, 0


def _enabled(t: str) -> bool:
    h, m = _parse_time(t)
    return not (h == 0 and m == 0)


def _entity_is_active(state_str: str, is_vacuum: bool = False) -> bool:
    """Return True if an external trigger entity should be considered active.
    
    For vacuum: uses inverse logic — active = anything NOT in VACUUM_INACTIVE_STATES.
    This handles all robot brands including Chinese robots with non-standard states
    like smart_cleaning, zone_cleaning, spot_cleaning, goto_target, etc.
    """
    if is_vacuum:
        return state_str.lower() not in VACUUM_INACTIVE_STATES
    return state_str.lower() not in _INACTIVE_STATES


class ElettrodomesticoCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry       = entry
        self.instance_id = self.config[CONF_INSTANCE_ID]
        self.slot        = str(self.config.get(CONF_SLOT, "1"))
        self.preset_id   = self.config.get(CONF_PRESET, "elettrodomestico")
        self.preset      = get_preset(self.preset_id)
        self.storage     = ElettrodomesticoStorage(hass, self.instance_id)

        self._trigger_entity: str = (self.config.get(CONF_TRIGGER_ENTITY) or "").strip()
        self._use_trigger_entity: bool = bool(self._trigger_entity)
        self._is_vacuum:  bool = (self.preset_id == "vacuum")
        self._is_clima:   bool = (self.preset_id == "clima")
        self._is_battery: bool = (self.preset_id == "batteria")
        _psensor = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        self._has_real_power: bool = bool(_psensor) and (_psensor != self._trigger_entity)

        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_{self.instance_id}",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )

        self._power_w:        float = 0.0
        self._power2_w:       float = 0.0
        self._shared_power:   float = 0.0   # written by master coordinator
        self._power_share:    float = 1.0   # kept for compatibility
        self._sensor_online:  bool  = True
        self._ac_state:       bool  = False
        self._ac_pending_on:  asyncio.TimerHandle | None = None
        self._ac_pending_off: asyncio.TimerHandle | None = None
        self._cycle_active:    bool  = False
        self._cycle_start_acc: float = 0.0
        self._cycle_start_ts:  float = 0.0
        self._acc_total  = 0.0
        self._e_today    = self._e_month = self._e_year = 0.0
        self._t_today    = self._t_month = self._t_year = 0.0
        self._c_today    = self._c_month = self._c_year = 0
        self._last_int_ts:    float | None = None
        self._last_int_power: float        = 0.0
        self._unsub:          list = []
        self._unsub_midnight: Any  = None
        self._unsub_auto_on:  Any  = None
        self._unsub_auto_off: Any  = None

    def _get_all_coordinators_same_sensor(self):
        """Return all coordinators that share the same power sensor."""
        all_coords = []
        for obj in self.hass.data.get(DOMAIN, {}).values():
            if hasattr(obj, "instance_id") and hasattr(obj, "config"):
                all_coords.append(obj)
        my_sensor = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        if not my_sensor:
            return [self]
        same = []
        for coord in all_coords:
            try:
                if (coord.config.get(CONF_POWER_SENSOR) or "").strip() == my_sensor:
                    same.append(coord)
            except Exception:
                continue
        return same if same else [self]

    def _is_device_active(self) -> bool:
        """Determine if this device is active."""
        trigger = (self.config.get(CONF_TRIGGER_ENTITY) or "").strip()
        if not trigger:
            return False
        st = self.hass.states.get(trigger)
        if not st:
            return False
        return _entity_is_active(st.state, self.config.get(CONF_PRESET) == "vacuum")

    @property
    def config(self) -> dict:
        return self.entry.data

    # ── Entity readers ────────────────────────────────────────────────────────

    def _num(self, sfx, default):
        st = self.hass.states.get(f"number.{sfx}_x{self.slot}")
        if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            try: return float(st.state)
            except: pass
        return default

    def _txt(self, sfx, default=""):
        st = self.hass.states.get(f"text.{sfx}_x{self.slot}")
        if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""): return st.state
        return default

    def _sw_on(self, sfx) -> bool:
        st = self.hass.states.get(f"switch.{sfx}_x{self.slot}")
        return st.state == "on" if st else False

    def _time_str(self, sfx) -> str:
        st = self.hass.states.get(f"time.{sfx}_x{self.slot}")
        if st and st.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return st.state
        return DEFAULT_SCHEDULE

    @property
    def _threshold(self):
        return self._num(SFX_NUM_SOGLIA, float(self.config.get(CONF_WORK_THRESHOLD_W, DEFAULT_THRESHOLD_W)))

    @property
    def _delay_off_s(self):
        return int(self._num(SFX_NUM_DELAY_OFF, float(self.config.get(CONF_TRIGGER_DELAY_M, DEFAULT_TRIGGER_DELAY_M))) * 60)

    @property
    def _delay_on_s(self):
        return int(self._num(SFX_NUM_DELAY_ON, float(self.config.get(CONF_START_DELAY_S, DEFAULT_START_DELAY_S))))

    @property
    def _display_name(self):
        return self._txt(SFX_TXT_NOME, self.config.get(CONF_APPLIANCE_NAME, "Elettrodomestico"))

    @property
    def _notify_message(self):
        return self._txt(SFX_TXT_MSG, self.config.get(CONF_CUSTOM_MESSAGE, ""))

    @property
    def _notify_push(self):    return self._sw_on(SFX_SW_NOTIFY_PUSH)
    @property
    def _notify_alexa(self):   return self._sw_on(SFX_SW_NOTIFY_ALEXA)
    @property
    def _notify_google(self):  return self._sw_on(SFX_SW_NOTIFY_GOOGLE)
    @property
    def _notify_whatsapp(self):return self._sw_on(SFX_SW_NOTIFY_WHATSAPP)

    def _get_cost(self, hub):
        key = self.preset.cost_key
        return hub.get(key, 0.0), hub.get(f"{key}_source", "fisso")

    @property
    def _cost_factor(self):
        src = self.config.get(CONF_SOURCE_UNIT, self.preset.source_unit)
        return 1.0 / 1000.0 if src in ("L/min","l/min") else 1.0

    def _resolve_schedule(self) -> tuple[str, str]:
        t_on  = self._time_str(SFX_TIME_AUTO_ON)
        t_off = self._time_str(SFX_TIME_AUTO_OFF)
        if _enabled(t_on) or _enabled(t_off):
            return t_on, t_off
        if self.config.get(CONF_SCHEDULE_OVERRIDE):
            return (self.config.get(CONF_AUTO_ON_LOCAL, DEFAULT_SCHEDULE),
                    self.config.get(CONF_AUTO_OFF_LOCAL, DEFAULT_SCHEDULE))
        h = get_hub_config(self.hass)
        return h.get("auto_on_time", DEFAULT_SCHEDULE), h.get("auto_off_time", DEFAULT_SCHEDULE)

    def _trigger_entity_active(self) -> bool:
        if not self._use_trigger_entity: return False
        st = self.hass.states.get(self._trigger_entity)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN): return False
        return _entity_is_active(st.state, self._is_vacuum)

    # ── Setup / Teardown ──────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        await self.storage.async_load()
        self._restore()
        self._register_power_group()

        _pwr = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        if _pwr and self._has_real_power:
            self._unsub.append(async_track_state_change_event(self.hass, [_pwr], self._on_power))

        _pwr2 = (self.config.get(CONF_POWER_SENSOR_2) or "").strip()
        if _pwr2:
            self._unsub.append(async_track_state_change_event(self.hass, [_pwr2], self._on_power2))

        if self._use_trigger_entity:
            self._unsub.append(async_track_state_change_event(
                self.hass, [self._trigger_entity], self._on_trigger_entity))
        else:
            sw = self.config.get(CONF_SWITCH_ENTITY)
            if sw:
                self._unsub.append(async_track_state_change_event(self.hass, [sw], self._on_switch))

        self._unsub.append(async_track_state_change_event(
            self.hass,
            [f"time.{SFX_TIME_AUTO_ON}_x{self.slot}", f"time.{SFX_TIME_AUTO_OFF}_x{self.slot}"],
            self._on_schedule_change,
        ))
        self._unsub_midnight = async_track_time_change(
            self.hass, self._on_midnight, hour=23, minute=59, second=59)
        self._sched_on(); self._sched_off()
        await self._read_power()

        if self._is_vacuum:
            vac = (self.config.get(CONF_VACUUM_ENTITY) or "").strip()
            if vac and vac != self._trigger_entity:
                self._unsub.append(async_track_state_change_event(
                    self.hass, [vac], self._on_trigger_entity))

        if self._use_trigger_entity:
            active = self._trigger_entity_active()
            if active and not self._ac_state: self._ac_on()
            elif not active and self._ac_state: self._ac_off()

    def _restore(self) -> None:
        d = self.storage.data
        self._cycle_active    = d.get("cycle_active",    False)
        self._cycle_start_acc = d.get("cycle_start_kwh", 0.0)
        self._cycle_start_ts  = d.get("cycle_start_ts",  0.0)
        self._acc_total = d.get("kwh_total_accum", 0.0)
        self._e_today   = d.get("energy_today",  0.0); self._e_month = d.get("energy_month", 0.0); self._e_year = d.get("energy_year", 0.0)
        self._t_today   = d.get("time_today",    0.0); self._t_month = d.get("time_month",   0.0); self._t_year = d.get("time_year",   0.0)
        self._c_today   = d.get("cycles_today",  0);   self._c_month = d.get("cycles_month", 0);   self._c_year = d.get("cycles_year", 0)
        self._ac_state  = self._cycle_active

    async def async_unload(self) -> None:
        psensor = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        if psensor:
            groups = self.hass.data.get(DOMAIN, {}).get(POWER_GROUPS_KEY, {})
            if psensor in groups:
                groups[psensor].pop(self.instance_id, None)
                if not groups[psensor]: del groups[psensor]
        for u in self._unsub: u()
        self._unsub.clear()
        for attr in ("_unsub_midnight","_unsub_auto_on","_unsub_auto_off"):
            cb = getattr(self, attr, None)
            if cb: cb(); setattr(self, attr, None)
        for attr in ("_ac_pending_on","_ac_pending_off"):
            cb = getattr(self, attr, None)
            if cb: cb(); setattr(self, attr, None)

    # ── Poll ──────────────────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        await self._read_power()
        self._integrate()
        self._tick_time()
        if self._use_trigger_entity:
            active = self._trigger_entity_active()
            if active and not self._ac_state: self._ac_on()
            elif not active and self._ac_state: self._ac_off()
        else:
            self._eval_ac()
        await self._persist()
        return self._build()

    # ── Power ─────────────────────────────────────────────────────────────────

    async def _read_power(self) -> None:
        psensor = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        if not psensor:
            self._sensor_online = False
            return
        st = self.hass.states.get(psensor)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, "", None):
            self._power_w = 0.0; self._sensor_online = False
            return
        try:
            raw_power = float(st.state)
            self._sensor_online = True
            group = self._get_all_coordinators_same_sensor()
            # Single device: use full power
            if len(group) <= 1:
                self._power_w = raw_power
                return
            # Master/slave: only the coordinator with the lowest instance_id computes
            master = sorted(group, key=lambda d: d.instance_id)[0]
            if self != master:
                self._power_w = self._shared_power
                return
            # Master computes distribution
            active_devices = [d for d in group if d._is_device_active()]
            active_count = len(active_devices)
            if active_count == 0:
                split = raw_power / len(group)
                for d in group:
                    d._shared_power = split
            else:
                split = raw_power / active_count
                for d in group:
                    d._shared_power = split if d in active_devices else 0.0
            self._power_w = self._shared_power
        except Exception as e:
            _LOGGER.error("[%s] Power read error: %s", self.instance_id, e)
            self._power_w = 0.0; self._sensor_online = False

    @callback
    def _on_power2(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in ("unavailable", "unknown"): return
        try:
            self._power2_w = float(new.state)
        except ValueError: return
        self.async_set_updated_data(self._build())

    @callback
    def _on_power(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._sensor_online = False
        else:
            self._sensor_online = True
        self.async_set_updated_data(self._build())

    @callback
    def _on_trigger_entity(self, event) -> None:
        new = event.data.get("new_state")
        if new is None: return
        # Save last non-off clima mode for restore on next turn_on
        if self._is_clima and new.state not in ("off", "unavailable", "unknown", ""):
            self.storage.set("last_clima_mode", new.state)
        active = _entity_is_active(new.state, self._is_vacuum)
        if active and not self._ac_state:
            if self._ac_pending_off: self._ac_pending_off(); self._ac_pending_off = None
            self._ac_on()
        elif not active and self._ac_state:
            if self._ac_pending_on: self._ac_pending_on(); self._ac_pending_on = None
            d = self._delay_off_s
            if self._ac_pending_off is None:
                if d: self._ac_pending_off = async_call_later(self.hass, d, lambda _: self._ac_off())
                else: self._ac_off()
        self.async_set_updated_data(self._build())

    # ── Integration ───────────────────────────────────────────────────────────

    def _integrate(self) -> None:
        if not self._has_real_power: return
        now = dt_util.utcnow().timestamp()
        if self._last_int_ts is None:
            self._last_int_ts, self._last_int_power = now, self._power_w; return
        dt_s = now - self._last_int_ts
        src = self.config.get(CONF_SOURCE_UNIT, self.preset.source_unit)
        if src == "W":               delta = self._last_int_power * dt_s / 3_600_000
        elif src in ("L/min","l/min"): delta = self._last_int_power * dt_s / 60
        elif src == "m³/h":          delta = self._last_int_power * dt_s / 3600
        else:                        delta = self._last_int_power * dt_s / 3_600_000
        if delta > 0:
            self._acc_total += delta; self._e_today += delta
            self._e_month   += delta; self._e_year  += delta
        self._last_int_ts = now; self._last_int_power = self._power_w

    def _tick_time(self) -> None:
        if not self._ac_state: return
        dh = COORDINATOR_UPDATE_INTERVAL / 3600.0
        self._t_today += dh; self._t_month += dh; self._t_year += dh

    # ── AC binary (threshold mode) ────────────────────────────────────────────

    def _eval_ac(self) -> None:
        above = self._power_w > self._threshold
        if above and not self._ac_state:
            if self._ac_pending_off: self._ac_pending_off(); self._ac_pending_off = None
            if self._ac_pending_on is None:
                d = self._delay_on_s
                if d: self._ac_pending_on = async_call_later(self.hass, d, lambda _: self._ac_on())
                else: self._ac_on()
        elif not above and self._ac_state:
            if self._ac_pending_on: self._ac_pending_on(); self._ac_pending_on = None
            if self._ac_pending_off is None:
                d = self._delay_off_s
                if d: self._ac_pending_off = async_call_later(self.hass, d, lambda _: self._ac_off())
                else: self._ac_off()
        elif above and self._ac_state:
            if self._ac_pending_off: self._ac_pending_off(); self._ac_pending_off = None
        else:
            if self._ac_pending_on: self._ac_pending_on(); self._ac_pending_on = None

    @callback
    def _ac_on(self) -> None:
        self._ac_pending_on = None
        if self._ac_state: return
        self._ac_state = True
        self.hass.add_job(self._cycle_start)

    @callback
    def _ac_off(self) -> None:
        self._ac_pending_off = None
        if not self._ac_state: return
        self._ac_state = False
        self.hass.add_job(self._cycle_end)

    # ── Cycle ─────────────────────────────────────────────────────────────────

    async def _cycle_start(self) -> None:
        self._cycle_active    = True
        self._cycle_start_acc = self._acc_total
        self._cycle_start_ts  = dt_util.utcnow().timestamp()
        self.storage.set("cycle_active",    True)
        self.storage.set("cycle_start_kwh", self._cycle_start_acc)
        self.storage.set("cycle_start_ts",  self._cycle_start_ts)
        await self.storage.async_save()
        self.hass.bus.async_fire(EVENT_CYCLE_START, {"instance_id": self.instance_id})
        self.async_set_updated_data(self._build())

    async def _cycle_end(self) -> None:
        now = dt_util.now(); now_ts = now.timestamp()
        elapsed_h   = max(0.0,(now_ts-self._cycle_start_ts)/3600.0) if self._cycle_start_ts else 0.0
        duration    = _fmt(elapsed_h)
        consumption = max(0.0, round(self._acc_total-self._cycle_start_acc, 3))
        hub         = get_hub_config(self.hass)
        cpp, csrc   = self._get_cost(hub)
        cost        = round(consumption * self._cost_factor * cpp, 2)
        end_str     = now.strftime("%d/%m/%Y %H:%M")
        self._cycle_active = False
        self.storage.set("cycle_active",           False)
        self.storage.set("cycle_last_duration",    duration)
        self.storage.set("cycle_last_consumption", consumption)
        self.storage.set("cycle_last_cost",        cost)
        self.storage.set("cycle_end_time",         end_str)
        self.storage.set("total_cycles",           self.storage.get("total_cycles",0)+1)
        self._c_today+=1; self._c_month+=1; self._c_year+=1
        self._t_today+=elapsed_h; self._t_month+=elapsed_h; self._t_year+=elapsed_h
        await self._persist()
        self.hass.bus.async_fire(EVENT_CYCLE_END, {
            "instance_id": self.instance_id, "duration": duration,
            "consumption": consumption, "cost": cost,
        })
        await self._notify(duration, consumption, cost)
        await asyncio.sleep(5)
        self._cycle_start_ts = self._cycle_start_acc = 0.0
        self.async_set_updated_data(self._build())

    # ── Notifications ─────────────────────────────────────────────────────────

    async def _notify(self, duration, consumption, cost):
        hub  = get_hub_config(self.hass)
        now  = dt_util.now()
        msg  = self._notify_message
        name = self._display_name
        unit = self.config.get(CONF_TOTAL_UNIT, self.preset.total_unit)
        sh,sm = _parse_time(hub["notify_start_time"])
        eh,em = _parse_time(hub["notify_end_time"])
        in_win = (now.replace(hour=sh,minute=sm,second=0,microsecond=0)
                  <= now <=
                  now.replace(hour=eh,minute=em,second=0,microsecond=0))
        cost_line = f"💰 {self.preset.label_costo}: {cost} €\n" if self.preset.show_cost else ""
        full_msg = f"📌 {msg}\n⏱ {duration}\n⚡️ {self.preset.label_consumo}: {consumption} {unit}\n{cost_line}".strip()

        if self._notify_push and hub["push_targets"]:
            for t in hub["push_targets"]:
                t = str(t).strip()
                sent = False
                try:
                    if self.hass.services.has_service("notify", "send_message"):
                        await self.hass.services.async_call(
                            "notify", "send_message",
                            {"entity_id": t, "message": full_msg, "title": name})
                        sent = True
                except Exception: pass
                if not sent:
                    svc_name = t.split(".", 1)[1] if "." in t else t
                    for svc in [svc_name, f"mobile_app_{svc_name}"]:
                        if self.hass.services.has_service("notify", svc):
                            try:
                                await self.hass.services.async_call(
                                    "notify", svc, {"title": name, "message": full_msg})
                                sent = True; break
                            except Exception as ex:
                                _LOGGER.warning("[%s] push notify.%s: %s", self.instance_id, svc, ex)
                if not sent:
                    _LOGGER.warning("[%s] push: impossibile inviare a '%s'", self.instance_id, t)

        if self._notify_whatsapp and hub.get("whatsapp_entity"):
            try: await self.hass.services.async_call("input_text","set_value",
                    {"entity_id": hub["whatsapp_entity"], "value": full_msg})
            except Exception as ex: _LOGGER.warning("[%s] whatsapp: %s", self.instance_id, ex)

        if in_win and self._notify_alexa and hub["alexa_targets"]:
            try: await self.hass.services.async_call("notify","alexa_media",
                    {"target": hub["alexa_targets"], "message": f"{msg} in {duration}",
                     "data": {"type":"announce","method":"spoken"}})
            except Exception as ex: _LOGGER.warning("[%s] alexa: %s", self.instance_id, ex)

        if in_win and self._notify_google and hub["google_targets"]:
            try: await self.hass.services.async_call("tts","google_translate_say",
                    {"entity_id": hub["google_targets"], "message": f"{msg} in {duration}"})
            except Exception as ex: _LOGGER.warning("[%s] google: %s", self.instance_id, ex)

    # ── Midnight ──────────────────────────────────────────────────────────────

    @callback
    def _on_midnight(self, now):
        self.hass.add_job(self._midnight, now)

    async def _midnight(self, now):
        today_it = WEEK_DAYS[now.weekday()]
        hub = get_hub_config(self.hass); cpp,_ = self._get_cost(hub)
        self.storage.set("energy_yesterday", self._e_today)
        self.storage.set("time_yesterday",   self._t_today)
        self.storage.set("cycles_yesterday", self._c_today)
        self.storage.set_weekly(today_it,"cicli",  str(self._c_today))
        self.storage.set_weekly(today_it,"tempo",  _fmt(self._t_today))
        self.storage.set_weekly(today_it,"consumo",round(self._e_today,3))
        self.storage.set_weekly(today_it,"costo",  round(self._e_today*self._cost_factor*cpp,2))
        self._e_today=self._t_today=0.0; self._c_today=0
        if now.day==1:
            self.storage.set("energy_last_month",self._e_month)
            self.storage.set("time_last_month",  self._t_month)
            self.storage.set("cycles_last_month",self._c_month)
            self._e_month=self._t_month=0.0; self._c_month=0
        if now.month==1 and now.day==1:
            self.storage.set("energy_last_year",self._e_year)
            self.storage.set("time_last_year",  self._t_year)
            self.storage.set("cycles_last_year",self._c_year)
            self._e_year=self._t_year=0.0; self._c_year=0
        await self._persist(); await self.storage.async_save()
        self.async_set_updated_data(self._build())

    # ── Schedule ──────────────────────────────────────────────────────────────

    @callback
    def _on_schedule_change(self, event): self._sched_on(); self._sched_off()

    def _next(self, h, m):
        now = dt_util.now()
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now: t += timedelta(days=1)
        return t

    def _sched_on(self):
        on,_ = self._resolve_schedule()
        if not _enabled(on):
            if self._unsub_auto_on: self._unsub_auto_on(); self._unsub_auto_on=None
            return
        h,m = _parse_time(on)
        if self._unsub_auto_on: self._unsub_auto_on()
        nxt = self._next(h, m)
        _LOGGER.info("[%s] Auto-ON scheduled: %02d:%02d (next: %s)",
                     self.instance_id, h, m, nxt.strftime("%H:%M %d/%m"))
        @callback
        def _fire(_now):
            _LOGGER.info("[%s] Auto-ON firing", self.instance_id)
            self.hass.add_job(self._sw, "turn_on")
            self._sched_on()
        self._unsub_auto_on = async_track_point_in_time(self.hass, _fire, nxt)

    def _sched_off(self):
        _,off = self._resolve_schedule()
        if not _enabled(off):
            if self._unsub_auto_off: self._unsub_auto_off(); self._unsub_auto_off=None
            return
        h,m = _parse_time(off)
        if self._unsub_auto_off: self._unsub_auto_off()
        nxt = self._next(h, m)
        _LOGGER.info("[%s] Auto-OFF scheduled: %02d:%02d (next: %s)",
                     self.instance_id, h, m, nxt.strftime("%H:%M %d/%m"))
        @callback
        def _fire(_now):
            _LOGGER.info("[%s] Auto-OFF firing", self.instance_id)
            self.hass.add_job(self._sw, "turn_off")
            self._sched_off()
        self._unsub_auto_off = async_track_point_in_time(self.hass, _fire, nxt)

    async def _sw(self, action: str) -> None:
        is_on = (action == "turn_on")

        if self._is_vacuum:
            vac = (self.config.get(CONF_VACUUM_ENTITY) or self._trigger_entity or "").strip()
            if not vac: return
            svc = "start" if is_on else "return_to_base"
            try: await self.hass.services.async_call("vacuum", svc, {"entity_id": vac})
            except Exception as ex: _LOGGER.warning("[%s] vacuum.%s failed: %s", self.instance_id, svc, ex)
            return

        if self._is_clima:
            eid = self._trigger_entity
            if not eid: return
            if is_on:
                # Read current mode: first try st.state, fallback to stored last mode
                st = self.hass.states.get(eid)
                current = st.state if st else "off"
                if current not in ("off", "unavailable", "unknown", ""):
                    mode = current
                else:
                    # Restore last known non-off mode from storage
                    mode = self.storage.get("last_clima_mode", "heat") or "heat"
                _LOGGER.info("[%s] Clima turn_on: mode=%s (current=%s, stored=%s)",
                             self.instance_id, mode, current,
                             self.storage.get("last_clima_mode", ""))
            else:
                mode = "off"
            _LOGGER.info("[%s] Clima: set_hvac_mode → %s (%s)", self.instance_id, mode, eid)
            try: await self.hass.services.async_call(
                    "climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": mode})
            except Exception as ex: _LOGGER.warning("[%s] climate.set_hvac_mode(%s) failed: %s", self.instance_id, mode, ex)
            return

        sw = (self.config.get(CONF_SWITCH_ENTITY) or "").strip()
        if sw:
            try: await self.hass.services.async_call("switch", action, {"entity_id": sw})
            except Exception as ex: _LOGGER.warning("[%s] switch.%s failed: %s", self.instance_id, action, ex)
            return

        if self._trigger_entity:
            try: await self.hass.services.async_call("homeassistant", action, {"entity_id": self._trigger_entity})
            except Exception as ex: _LOGGER.warning("[%s] homeassistant.%s failed: %s", self.instance_id, action, ex)

    @callback
    def _on_switch(self, event):
        self.async_set_updated_data(self._build())

    # ── Persistence ───────────────────────────────────────────────────────────

    async def _persist(self):
        s = self.storage
        s.set("kwh_total_accum",self._acc_total)
        s.set("energy_today",self._e_today); s.set("energy_month",self._e_month); s.set("energy_year",self._e_year)
        s.set("time_today",self._t_today);   s.set("time_month",self._t_month);   s.set("time_year",self._t_year)
        s.set("cycles_today",self._c_today); s.set("cycles_month",self._c_month); s.set("cycles_year",self._c_year)
        await s.async_save()

    # ── Public ────────────────────────────────────────────────────────────────

    async def async_reset_all(self):
        self._e_today=self._e_month=self._e_year=0.0
        self._t_today=self._t_month=self._t_year=0.0
        self._c_today=self._c_month=self._c_year=0
        self._acc_total=0.0; self._last_int_ts=None
        self._cycle_active=False; self._cycle_start_acc=self._cycle_start_ts=0.0
        await self.storage.async_reset()
        self.storage.set("reset_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        await self.storage.async_save()
        self.async_set_updated_data(self._build())

    async def async_set_maintenance(self):
        self.storage.set("maintenance_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        await self.storage.async_save()
        self.async_set_updated_data(self._build())

    # ── Data dict ─────────────────────────────────────────────────────────────

    def _build(self) -> dict[str, Any]:
        now=dt_util.now(); now_ts=now.timestamp()
        sd=self.storage.data
        hub=get_hub_config(self.hass)
        cpp,csrc=self._get_cost(hub); cf=self._cost_factor
        src_unit=self.config.get(CONF_SOURCE_UNIT,self.preset.source_unit)
        total_unit=self.config.get(CONF_TOTAL_UNIT,self.preset.total_unit)

        if self._cycle_active and self._cycle_start_ts>0:
            elapsed_h=(now_ts-self._cycle_start_ts)/3600.0
            tempo_ciclo=_fmt(elapsed_h); terminato="In funzione"
            consumo_ciclo=max(0.0,round(self._acc_total-self._cycle_start_acc,3))
        else:
            tempo_ciclo=sd.get("cycle_last_duration","")
            terminato=sd.get("cycle_end_time","")
            consumo_ciclo=sd.get("cycle_last_consumption",0.0)

        costo_ciclo=round(consumo_ciclo*cf*cpp,2) if self.preset.show_cost else 0.0

        weekly={}
        for day in WEEK_DAYS:
            w=sd.get("weekly",{}).get(day,{})
            val=float(w.get("consumo",0.0))
            weekly[day]={"cicli":w.get("cicli","0"),"tempo":w.get("tempo","0min"),
                         "consumo":round(val,3),
                         "costo":round(val*cf*cpp,2) if self.preset.show_cost else 0.0}

        on_t,off_t=self._resolve_schedule()
        t_on_val=self._time_str(SFX_TIME_AUTO_ON)
        t_off_val=self._time_str(SFX_TIME_AUTO_OFF)

        sw_entity=self.config.get(CONF_SWITCH_ENTITY)
        sw_state=None
        if sw_entity:
            st=self.hass.states.get(sw_entity); sw_state=st.state if st else None

        trigger_state=None
        if self._use_trigger_entity:
            st=self.hass.states.get(self._trigger_entity)
            trigger_state=st.state if st else None

        return {
            "power_w":self._power_w,"sensor_online":self._sensor_online,
            "acc_total":round(self._acc_total,3),
            "volume_m3":round(self._acc_total/1000.0,4) if self.preset.has_volume_m3 else None,
            "ac_state":self._ac_state,"cycle_active":self._cycle_active,
            "tempo_ciclo":tempo_ciclo,"terminato":terminato,
            "consumo_ciclo":consumo_ciclo,"costo_ciclo":costo_ciclo,
            "cycle_start_acc":self._cycle_start_acc,
            "energy_today":round(self._e_today,3),"energy_month":round(self._e_month,3),"energy_year":round(self._e_year,3),
            "energy_yesterday":round(sd.get("energy_yesterday",0.0),3),
            "energy_last_month":round(sd.get("energy_last_month",0.0),3),
            "energy_last_year":round(sd.get("energy_last_year",0.0),3),
            "time_today":self._t_today,"time_month":self._t_month,"time_year":self._t_year,
            "time_yesterday":sd.get("time_yesterday",0.0),"time_last_month":sd.get("time_last_month",0.0),"time_last_year":sd.get("time_last_year",0.0),
            "time_today_str":_fmt(self._t_today),"time_month_str":_fmt(self._t_month),"time_year_str":_fmt(self._t_year),
            "time_yesterday_str":_fmt(sd.get("time_yesterday",0.0)),
            "time_last_month_str":_fmt(sd.get("time_last_month",0.0)),
            "time_last_year_str":_fmt(sd.get("time_last_year",0.0)),
            "cycles_today":self._c_today,"cycles_month":self._c_month,"cycles_year":self._c_year,
            "cycles_yesterday":sd.get("cycles_yesterday",0),"cycles_last_month":sd.get("cycles_last_month",0),"cycles_last_year":sd.get("cycles_last_year",0),
            "total_cycles":sd.get("total_cycles",0),
            "costo_oggi":round(self._e_today*cf*cpp,2) if self.preset.show_cost else 0.0,
            "costo_mese":round(self._e_month*cf*cpp,2) if self.preset.show_cost else 0.0,
            "costo_anno":round(self._e_year*cf*cpp,2)  if self.preset.show_cost else 0.0,
            "costo_ieri":round(sd.get("energy_yesterday",0.0)*cf*cpp,2) if self.preset.show_cost else 0.0,
            "costo_mese_prec":round(sd.get("energy_last_month",0.0)*cf*cpp,2) if self.preset.show_cost else 0.0,
            "costo_anno_prec":round(sd.get("energy_last_year",0.0)*cf*cpp,2)  if self.preset.show_cost else 0.0,
            "cost_per_unit":cpp,"cost_source":csrc,"cost_factor":cf,
            "preset_id":self.preset_id,"source_unit":src_unit,"total_unit":total_unit,
            "label_consumo":self.preset.label_consumo,"label_costo":self.preset.label_costo,
            "show_cost":self.preset.show_cost,"inverted_cost":self.preset.inverted_cost,
            "schedule_auto_on":on_t,"schedule_auto_off":off_t,
            "schedule_source":"time_entity" if (_enabled(t_on_val) or _enabled(t_off_val)) else ("locale" if self.config.get(CONF_SCHEDULE_OVERRIDE) else "hub"),
            "time_auto_on":t_on_val,"time_auto_off":t_off_val,
            "switch_state":sw_state,
            "trigger_entity":self._trigger_entity,"trigger_state":trigger_state,
            "use_trigger_entity":self._use_trigger_entity,
            "notify_push":self._notify_push,"notify_alexa":self._notify_alexa,
            "notify_google":self._notify_google,"notify_whatsapp":self._notify_whatsapp,
            "threshold_w":self._threshold,"delay_off_m":self._delay_off_s/60,"delay_on_s":self._delay_on_s,
            "display_name":self._display_name,
            "maintenance_date":sd.get("maintenance_date",""),"reset_date":sd.get("reset_date",""),
            "version":VERSION,"appliance_name":self.config.get(CONF_APPLIANCE_NAME,""),
            "slot":self.slot,"device_icon":self.config.get(CONF_DEVICE_ICON,self.preset.default_icon),
            "weekly":weekly,
            "main_on":       self._get_main_on(),
            "image_on":      (self.config.get(CONF_IMAGE_ON)  or "").strip(),
            "image_off":     (self.config.get(CONF_IMAGE_OFF) or "").strip(),
            "power2_w":      self._power2_w,
            "power_sensor_2":(self.config.get(CONF_POWER_SENSOR_2) or "").strip(),
            "is_vacuum":     self._is_vacuum,
            "vacuum_battery":self._get_vacuum_battery(),
            "vacuum_state":  self._get_vacuum_state(),
            "is_battery":    self._is_battery,
            "device_battery":self._get_device_battery(),
        }

    def _register_power_group(self) -> None:
        psensor = (self.config.get(CONF_POWER_SENSOR) or "").strip()
        if not psensor: return
        groups = self.hass.data[DOMAIN].setdefault(POWER_GROUPS_KEY, {})
        if psensor not in groups:
            groups[psensor] = {}
        groups[psensor][self.instance_id] = False
        _LOGGER.debug("[%s] Registered in power group: %s (%d members)",
                      self.instance_id, psensor, len(groups[psensor]))

    def _update_power_share(self) -> None:
        """Legacy — kept for compatibility. Logic moved to _read_power."""
        pass

    def _get_main_on(self) -> bool:
        if self._is_vacuum:
            vac = (self.config.get(CONF_VACUUM_ENTITY) or self._trigger_entity or "").strip()
            if vac:
                st = self.hass.states.get(vac)
                if st: return st.state.lower() in VACUUM_ACTIVE_STATES
            return self._ac_state
        if self._is_clima:
            eid = self._trigger_entity
            if eid:
                st = self.hass.states.get(eid)
                if st: return st.state.lower() not in ("off", "unavailable", "unknown")
            return self._ac_state
        sw = (self.config.get(CONF_SWITCH_ENTITY) or "").strip()
        if sw:
            st = self.hass.states.get(sw)
            if st: return st.state == "on"
            return self._ac_state
        if self._use_trigger_entity and self._trigger_entity:
            return self._trigger_entity_active()
        return self._ac_state

    def _get_vacuum_battery(self) -> int | None:
        if not self._is_vacuum: return None
        bsensor = (self.config.get(CONF_BATTERY_SENSOR) or "").strip()
        if bsensor:
            st = self.hass.states.get(bsensor)
            if st and st.state not in ("unavailable", "unknown", ""):
                try: return int(float(st.state))
                except: pass
        for eid in ((self.config.get(CONF_VACUUM_ENTITY) or "").strip(), self._trigger_entity):
            if not eid: continue
            st = self.hass.states.get(eid)
            if st:
                for attr in ('battery_level', 'battery', 'battery_percentage'):
                    val = st.attributes.get(attr)
                    if val is not None:
                        try: return int(float(str(val)))
                        except: pass
        return None

    def _get_vacuum_state(self) -> str:
        vac = (self.config.get(CONF_VACUUM_ENTITY) or self._trigger_entity or "").strip()
        if not vac: return ""
        st = self.hass.states.get(vac)
        return st.state if st else ""

    def _get_device_battery(self) -> int | None:
        if not self._is_battery: return None
        bsensor = (self.config.get(CONF_BATTERY_SENSOR) or "").strip()
        if not bsensor: return None
        st = self.hass.states.get(bsensor)
        if st and st.state not in ("unavailable", "unknown", ""):
            try: return int(float(st.state))
            except: pass
        return None

    @property
    def ac_state(self): return self._ac_state
    @property
    def sensor_online(self): return self._sensor_online
