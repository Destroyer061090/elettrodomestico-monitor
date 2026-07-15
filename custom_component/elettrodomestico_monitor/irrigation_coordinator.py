# ============================================================
# FILE:    irrigation_coordinator.py
# VERSION: 5.8.11
# DESC:    Irrigation coordinator — zone cycling, scheduling, stats, countdown
# CHANGED: 2026-06-11
# ============================================================
"""
Irrigation Coordinator for Elettrodomestico Monitor.

Manages a single irrigation system with:
- Up to 8 zones (name, switch entity, duration)
- Sequential cycle execution
- 3 independent schedules (time + weekdays + mode)
- Global weather skip condition
- Flow + pump power tracking
- Full statistics (L, kWh, cycles, time)
"""
from __future__ import annotations
import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_sunrise,
    async_track_sunset,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, VERSION, COORDINATOR_UPDATE_INTERVAL,
    CONF_APPLIANCE_NAME, CONF_SLOT, CONF_INSTANCE_ID,
    CONF_ZONES, CONF_ZONE_ORDER,
    CONF_FLOW_SENSOR, CONF_PUMP_SENSOR, CONF_METEO_ENTITY,
    CONF_IMAGE_ON, CONF_IMAGE_OFF,
    CONF_IRR_SCHEDULE_1, CONF_IRR_SCHEDULE_2, CONF_IRR_SCHEDULE_3,
    ENTRY_TYPE_IRRIGATION,
    WEEK_DAYS,
)
from .hub import get_hub_config
from .notify_helper import async_send_notification
from .storage import ElettrodomesticoStorage

_LOGGER = logging.getLogger(__name__)

SCHEDULE_KEYS = [CONF_IRR_SCHEDULE_1, CONF_IRR_SCHEDULE_2, CONF_IRR_SCHEDULE_3]


def _parse_time(t: str) -> tuple[int, int]:
    parts = str(t or "00:00:00").split(":")
    return int(parts[0]), int(parts[1])


def _enabled(t: str) -> bool:
    h, m = _parse_time(t)
    return h != 0 or m != 0


def _fmt(h: float) -> str:
    total_s = int(h * 3600)
    d, rem = divmod(total_s, 86400)
    hh, rem = divmod(rem, 3600)
    mm = rem // 60
    if d: return f"{d}d {hh}h {mm}m"
    if hh: return f"{hh}h {mm}m"
    return f"{mm}min"


class IrrigationCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_irr_{entry.data.get(CONF_INSTANCE_ID, 'x')}",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )
        self.entry        = entry
        self.instance_id  = entry.data.get(CONF_INSTANCE_ID, "irr")
        self.slot         = str(entry.data.get(CONF_SLOT, "1"))
        self.storage      = ElettrodomesticoStorage(hass, self.instance_id)

        # Runtime state
        self._cycle_active    = False
        self._cycle_task      = None
        self._stop_requested  = False
        # Timestamp of the last time EM itself turned a zone off. The zone-switch
        # callback ignores OFF events within a short window after this, so EM's
        # own shutdowns aren't misreported as "external".
        self._em_off_ts       = 0.0
        self._active_zone_idx = -1   # real zone index (into self.zones), -1 = idle
        self._countdown_s     = 0
        self._countdown_unsub = None

        # Accumulators
        self._flow_w:    float = 0.0   # L/min current
        self._pump_w:    float = 0.0   # W current
        self._l_total:   float = 0.0
        self._kwh_total: float = 0.0
        self._l_today:   float = 0.0
        self._l_month:   float = 0.0
        self._l_year:    float = 0.0
        self._kwh_today: float = 0.0
        self._kwh_month: float = 0.0
        self._kwh_year:  float = 0.0
        # FV pump energy split (grid vs solar)
        self._eg_today = self._eg_month = self._eg_year = 0.0
        self._es_today = self._es_month = self._es_year = 0.0
        self._t_today:   float = 0.0
        self._t_month:   float = 0.0
        self._t_year:    float = 0.0
        self._c_today:   int   = 0
        self._c_month:   int   = 0
        self._c_year:    int   = 0
        self._last_int_ts: float | None = None

        # Schedule unsub
        self._sched_unsubs: list = []
        self._sched_unsub_by_key: dict = {}

        # Unsub list
        self._unsub: list = []

    @property
    def config(self) -> dict:
        return self.entry.data

    @property
    def zones(self) -> list[dict]:
        """List of zone dicts: {name, switch, duration_min}"""
        return self.config.get(CONF_ZONES) or []

    @property
    def zone_order(self) -> list[int]:
        """Ordered list of zone indices (0-based)."""
        order = self.config.get(CONF_ZONE_ORDER)
        if order:
            return order
        return list(range(len(self.zones)))

    @property
    def active_zone(self) -> dict | None:
        # _active_zone_idx holds the real zone index (into self.zones), not the
        # sequence position — so it works for both full cycles and single-zone runs.
        if self._active_zone_idx < 0: return None
        zones = self.zones
        if self._active_zone_idx >= len(zones): return None
        return zones[self._active_zone_idx]

    async def async_setup(self):
        """Load storage and wire tracking."""
        await self.storage.async_load()
        d = self.storage.data

        self._l_total   = d.get("l_total",   0.0)
        self._kwh_total = d.get("kwh_total",  0.0)
        self._l_today   = d.get("l_today",    0.0)
        self._l_month   = d.get("l_month",    0.0)
        self._l_year    = d.get("l_year",     0.0)
        self._kwh_today = d.get("kwh_today",  0.0)
        self._kwh_month = d.get("kwh_month",  0.0)
        self._kwh_year  = d.get("kwh_year",   0.0)
        self._eg_today = d.get("irr_eg_today",0.0); self._eg_month = d.get("irr_eg_month",0.0); self._eg_year = d.get("irr_eg_year",0.0)
        self._es_today = d.get("irr_es_today",0.0); self._es_month = d.get("irr_es_month",0.0); self._es_year = d.get("irr_es_year",0.0)
        self._t_today   = d.get("t_today",    0.0)
        self._t_month   = d.get("t_month",    0.0)
        self._t_year    = d.get("t_year",     0.0)
        self._c_today   = d.get("c_today",    0)
        self._c_month   = d.get("c_month",    0)
        self._c_year    = d.get("c_year",     0)

        # Track flow sensor
        flow_eid = (self.config.get(CONF_FLOW_SENSOR) or "").strip()
        if flow_eid:
            self._unsub.append(async_track_state_change_event(
                self.hass, [flow_eid], self._on_flow))

        # Track real zone switch changes (external control via Alexa, HA UI, etc.)
        zone_switch_eids = [
            z.get("switch", "").strip()
            for z in self.zones
            if z.get("switch", "").strip()
        ]
        if zone_switch_eids:
            self._unsub.append(async_track_state_change_event(
                self.hass, zone_switch_eids, self._on_zone_switch))

        # Track pump sensor
        pump_eid = (self.config.get(CONF_PUMP_SENSOR) or "").strip()
        if pump_eid:
            self._unsub.append(async_track_state_change_event(
                self.hass, [pump_eid], self._on_pump))

        # Schedule midnight reset
        self._unsub.append(async_track_point_in_time(
            self.hass, self._on_midnight,
            dt_util.now().replace(hour=0, minute=0, second=1, microsecond=0) + timedelta(days=1)
        ))

        # Wire schedules
        self._wire_schedules()

        _LOGGER.info("[IRR %s] Setup complete — %d zones", self.instance_id, len(self.zones))

    def _wire_schedules(self):
        """Wire all 3 schedule slots."""
        for unsub in self._sched_unsubs:
            try: unsub()
            except Exception: pass
        self._sched_unsubs = []
        self._sched_unsub_by_key = {}

        # Deduplicate schedules with same time+mode to avoid concurrent cycles
        seen_schedules: set = set()

        for key in SCHEDULE_KEYS:
            sched = self.config.get(key)
            if not sched: continue
            time_str = sched.get("time", "00:00:00")
            days     = sched.get("days", [])
            mode     = sched.get("mode", "fixed")  # fixed | sunrise | sunset

            if not days: continue

            # Skip disabled schedules (00:00:00)
            if not _enabled(time_str):
                continue

            # Skip duplicate schedule (same time + mode — not disabled ones)
            sched_key = (time_str, mode)
            if sched_key in seen_schedules:
                _LOGGER.warning("[IRR %s] Duplicate schedule skipped: %s %s",
                                self.instance_id, mode, time_str)
                continue
            seen_schedules.add(sched_key)

            if mode == "sunrise":
                offset_min = int(sched.get("offset_min", 0))
                unsub = async_track_sunrise(
                    self.hass,
                    lambda _, d=days, o=offset_min: self.hass.add_job(
                        self._on_schedule_fire, d, o),
                    offset=timedelta(minutes=offset_min)
                )
                self._sched_unsubs.append(unsub)
            elif mode == "sunset":
                offset_min = int(sched.get("offset_min", 0))
                unsub = async_track_sunset(
                    self.hass,
                    lambda _, d=days, o=offset_min: self.hass.add_job(
                        self._on_schedule_fire, d, o),
                    offset=timedelta(minutes=offset_min)
                )
                self._sched_unsubs.append(unsub)
            else:
                # Fixed time — use point_in_time recurring
                self._schedule_fixed(time_str, days, key)

    def _schedule_fixed(self, time_str: str, days: list, key: str):
        """Schedule a fixed-time recurring trigger. Days are read fresh at fire time."""
        h, m = _parse_time(time_str)
        if h == 0 and m == 0: return

        now = dt_util.now()
        nxt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)

        @callback
        def _fire(_now, k=key, ts=time_str):
            # Read days FRESH from config at fire time (not stale from wire time)
            sched = self.config.get(k) or {}
            current_days = sched.get("days", [])
            self.hass.add_job(self._on_schedule_fire, current_days, 0)
            # Re-schedule for tomorrow using fresh config
            new_t = sched.get("time", ts)
            self._schedule_fixed(new_t, current_days, k)

        # Replace any previous (consumed) unsub for this key to avoid accumulation
        prev = self._sched_unsub_by_key.get(key)
        if prev in self._sched_unsubs:
            try: self._sched_unsubs.remove(prev)
            except ValueError: pass
        unsub = async_track_point_in_time(self.hass, _fire, nxt)
        self._sched_unsubs.append(unsub)
        self._sched_unsub_by_key[key] = unsub
        _LOGGER.info("[IRR %s] Schedule %s: %02d:%02d next=%s (days checked at fire time)",
                     self.instance_id, key, h, m, nxt.strftime("%H:%M %d/%m"))

    async def _on_schedule_fire(self, days: list, offset_min: int):
        """Called when a schedule fires. Check enabled, day and meteo, then start cycle."""
        # Check if scheduling is enabled (None/missing → enabled by default)
        _sched_enabled = self.config.get("irr_sched_enabled")
        if _sched_enabled is False:
            _LOGGER.info("[IRR %s] Schedule skipped: scheduling disabled", self.instance_id)
            return

        now = dt_util.now()
        today = WEEK_DAYS[now.weekday()]
        if today not in days:
            _LOGGER.debug("[IRR %s] Schedule fired but today (%s) not in days %s",
                         self.instance_id, today, days)
            return

        # Check meteo
        if self._check_meteo_skip():
            hub = get_hub_config(self.hass)
            meteo = hub.get("meteo_entity") or self.config.get(CONF_METEO_ENTITY) or ""
            _LOGGER.info("[IRR %s] Schedule skipped: meteo entity %s is ON", self.instance_id, meteo)
            await self._notify_skip_meteo()
            return

        if self._cycle_active:
            _LOGGER.info("[IRR %s] Schedule fired but cycle already active", self.instance_id)
            return

        _LOGGER.info("[IRR %s] Schedule firing — starting cycle", self.instance_id)
        await self.start_cycle()

    def _check_meteo_skip(self) -> bool:
        """Return True if meteo condition says to skip."""
        hub = get_hub_config(self.hass)
        meteo_eid = hub.get("meteo_entity") or self.config.get(CONF_METEO_ENTITY) or ""
        if not meteo_eid: return False
        st = self.hass.states.get(meteo_eid)
        return st is not None and st.state == "on"

    async def start_cycle(self, zone_idx: int | None = None, manual: bool = False):
        """Start irrigation cycle. If zone_idx given, run only that zone.
        manual=True means the zone switch is already ON (user toggled it), so we
        track/count without re-toggling it, but still stop it at end of duration."""
        if self._cycle_active:
            _LOGGER.warning("[IRR %s] Cycle already active", self.instance_id)
            return

        self._stop_requested = False
        self._cycle_active = True
        self.async_set_updated_data(self._build())

        if zone_idx is not None:
            zones_to_run = [zone_idx]
        else:
            zones_to_run = self.zone_order

        self._cycle_task = self.hass.async_create_task(
            self._run_cycle(zones_to_run, manual=manual))

    async def _run_cycle(self, zone_indices: list[int], manual: bool = False):
        """Execute irrigation zones sequentially."""
        cycle_start = dt_util.now()
        total_l_start = self._l_total
        total_kwh_start = self._kwh_total

        try:
            for seq_idx, zone_idx in enumerate(zone_indices):
                if self._stop_requested: break
                zones = self.zones
                if zone_idx >= len(zones): continue
                zone = zones[zone_idx]
                self._active_zone_idx = zone_idx  # real zone index (into self.zones)
                # Remember the last irrigated zone (for "Zona Ultima" display at rest)
                self.storage.set("last_zone_name", zone.get("name", ""))
                self.storage.set("last_zone_time", dt_util.now().strftime("%d/%m/%Y %H:%M"))
                duration_s = max(10, int(float(zone.get("duration_min", 5)) * 60))  # min 10s

                _LOGGER.info("[IRR %s] Starting zone %d: %s (%ds)",
                             self.instance_id, zone_idx, zone.get("name"), duration_s)

                # Activate zone switch (skip if manual: user already turned it on)
                sw = zone.get("switch", "")
                if sw and not manual:
                    try:
                        await self.hass.services.async_call(
                            "homeassistant", "turn_on", {"entity_id": sw})
                    except Exception as ex:
                        _LOGGER.warning("[IRR %s] Zone switch error: %s", self.instance_id, ex)
                elif sw and manual:
                    _LOGGER.info("[IRR %s] Zona %s gia' ON (avvio manuale) — non ri-attivo",
                                 self.instance_id, sw)

                # Start countdown
                self._countdown_s = duration_s
                self._start_countdown()
                self.async_set_updated_data(self._build())

                # Wait for duration (checking stop every 1s for responsiveness)
                elapsed = 0
                while elapsed < duration_s and not self._stop_requested:
                    sleep_time = min(1, duration_s - elapsed)
                    await asyncio.sleep(sleep_time)
                    elapsed += sleep_time

                # Deactivate zone — always called, even on stop
                self._stop_countdown()
                self._countdown_s = 0
                if sw:
                    try:
                        self._em_off_ts = dt_util.utcnow().timestamp()
                        await self.hass.services.async_call(
                            "homeassistant", "turn_off", {"entity_id": sw})
                        _LOGGER.info("[IRR %s] Zone %d OFF: %s", self.instance_id, zone_idx, sw)
                    except Exception as ex:
                        _LOGGER.error("[IRR %s] Zone %d turn_off FAILED: %s — %s",
                                      self.instance_id, zone_idx, sw, ex)
                else:
                    _LOGGER.warning("[IRR %s] Zone %d has no switch configured", self.instance_id, zone_idx)

                _LOGGER.info("[IRR %s] Zone %d complete", self.instance_id, zone_idx)
                # 10s pause between zones (not after the last one)
                if seq_idx < len(zone_indices) - 1 and not self._stop_requested:
                    await asyncio.sleep(10)

        finally:
            # Capture whether the cycle was interrupted BEFORE resetting the flag
            was_stopped = self._stop_requested
            # Safety: ensure ALL zone switches are off regardless
            self._em_off_ts = dt_util.utcnow().timestamp()
            for zone in self.zones:
                sw_f = zone.get("switch", "")
                if sw_f:
                    try:
                        await self.hass.services.async_call(
                            "homeassistant", "turn_off", {"entity_id": sw_f})
                    except Exception:
                        pass
            self._active_zone_idx = -1
            self._cycle_active = False
            self._stop_requested = False
            self._stop_countdown()

            # Update stats
            elapsed_h = (dt_util.now() - cycle_start).total_seconds() / 3600
            l_consumed = round(self._l_total - total_l_start, 2)
            kwh_consumed = round(self._kwh_total - total_kwh_start, 4)
            duration_str = _fmt(elapsed_h)

            # Count the cycle and notify ONLY if it ran to completion (not interrupted)
            if not was_stopped:
                self._c_today += 1; self._c_month += 1; self._c_year += 1
                self._t_today += elapsed_h; self._t_month += elapsed_h; self._t_year += elapsed_h
                await self._persist()
                hub = get_hub_config(self.hass)
                await self._notify_complete(duration_str, l_consumed, kwh_consumed, hub)
            else:
                # Still accumulate elapsed time, but don't count as a completed cycle
                self._t_today += elapsed_h; self._t_month += elapsed_h; self._t_year += elapsed_h
                await self._persist()
                _LOGGER.info("[IRR %s] Cycle interrupted — not counted", self.instance_id)

            self.async_set_updated_data(self._build())
            _LOGGER.info("[IRR %s] Cycle complete: %s, %.1fL, %.3fkWh",
                         self.instance_id, duration_str, l_consumed, kwh_consumed)

    async def stop_cycle(self, external: bool = False):
        """Stop running cycle immediately.

        external=True means the user already turned the zone switch off by hand,
        so we don't need to (and shouldn't re-)drive the switches; we just wind
        the cycle down. external=False is the normal EM-initiated stop."""
        if not self._cycle_active: return
        self._stop_requested = True
        if not external:
            # EM-initiated stop: turn off all zone switches.
            self._em_off_ts = dt_util.utcnow().timestamp()
            for zone in self.zones:
                sw = zone.get("switch", "")
                if sw:
                    try:
                        await self.hass.services.async_call(
                            "homeassistant", "turn_off", {"entity_id": sw})
                    except Exception: pass
        _LOGGER.info("[IRR %s] Cycle stopped (%s)", self.instance_id,
                     "external" if external else "user")

    # ── Countdown ─────────────────────────────────────────────────────────────

    def _start_countdown(self):
        self._stop_countdown()

        @callback
        def _tick(_now):
            # Integrate flow (L) and pump (kWh) every second while a cycle runs,
            # so totals accrue over time even if the sensors don't emit changes.
            if self._cycle_active:
                self._integrate()
            if self._countdown_s > 0:
                self._countdown_s = max(0, self._countdown_s - 1)
                self.async_set_updated_data(self._build())
            if self._countdown_s > 0 and self._cycle_active:
                self._start_countdown()

        self._countdown_unsub = async_call_later(self.hass, 1, _tick)

    def _stop_countdown(self):
        if self._countdown_unsub:
            self._countdown_unsub()
            self._countdown_unsub = None

    # ── Sensor callbacks ──────────────────────────────────────────────────────

    @callback
    def _on_flow(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in ("unavailable", "unknown"): return
        # Integrate the interval up to now (reads sensors live), then refresh UI.
        self._integrate()
        self.async_set_updated_data(self._build())

    @callback
    def _on_zone_switch(self, event) -> None:
        """External zone switch change.
        - OFF→ON while idle: user started a zone manually → start a managed cycle
          (counts, duration timer) WITHOUT re-toggling the already-on switch.
        - ON→OFF during our cycle: external stop → log for diagnostics."""
        try:
            new = event.data.get("new_state")
            old = event.data.get("old_state")
            eid = event.data.get("entity_id", "")
            # Manual ON while no cycle running → start managed cycle for this zone
            if (not self._cycle_active and old and new
                    and old.state == "off" and new.state == "on"):
                zidx = next((i for i, z in enumerate(self.zones)
                             if z.get("switch", "").strip() == eid), None)
                if zidx is not None:
                    _LOGGER.info("[IRR %s] Avvio MANUALE rilevato su zona %s → avvio ciclo gestito",
                                 self.instance_id, eid)
                    self.hass.async_create_task(
                        self.start_cycle(zone_idx=zidx, manual=True))
                    return
            # External OFF during our cycle.
            if (self._cycle_active and old and new
                    and old.state == "on" and new.state == "off"):
                active_sw = ""
                if 0 <= self._active_zone_idx < len(self.zones):
                    active_sw = self.zones[self._active_zone_idx].get("switch", "")
                # Ignore OFF events within 30s of an EM-initiated turn-off.
                # The switch state-change event can arrive late (slow relay,
                # cloud switch, or HA under load), so a narrow window produced
                # false "external OFF" warnings at the very end of a cycle.
                recently_em = (dt_util.utcnow().timestamp() - self._em_off_ts) < 30.0
                if eid == active_sw and not self._stop_requested and not recently_em:
                    # The user turned the active zone OFF by hand. Treat this as a
                    # stop request: end the cycle cleanly instead of leaving it
                    # "active" (which made the countdown keep running and the
                    # switch flip back ON). This is intended user action, so it's
                    # an info message, not a warning.
                    _LOGGER.info(
                        "[IRR %s] Zona %s spenta manualmente durante il ciclo → "
                        "interpreto come STOP del ciclo.",
                        self.instance_id, eid)
                    self._stop_requested = True
                    self.hass.async_create_task(self.stop_cycle(external=True))
        except Exception:
            pass
        self.async_set_updated_data(self._build())

    @callback
    def _on_pump(self, event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in ("unavailable", "unknown"): return
        # Integrate the interval up to now (reads sensors live), then refresh UI.
        self._integrate()
        self.async_set_updated_data(self._build())

    def _read_flow_now(self) -> float:
        """Read the flow sensor's current value (L/min). 0 if missing/invalid."""
        eid = (self.config.get(CONF_FLOW_SENSOR) or "").strip()
        if not eid: return 0.0
        st = self.hass.states.get(eid)
        if not st or st.state in ("unknown", "unavailable", ""): return 0.0
        try: return max(0.0, float(st.state))
        except (ValueError, TypeError): return 0.0

    def _read_pump_now(self) -> float:
        """Read the pump sensor's current power (W). 0 if missing/invalid."""
        eid = (self.config.get(CONF_PUMP_SENSOR) or "").strip()
        if not eid: return 0.0
        st = self.hass.states.get(eid)
        if not st or st.state in ("unknown", "unavailable", ""): return 0.0
        try: return max(0.0, float(st.state))
        except (ValueError, TypeError): return 0.0

    def _integrate(self):
        """Integrate flow (L) and pump (kWh) over the elapsed interval, using a
        single shared timestamp so both accrue correctly. Reads the sensors LIVE
        so totals accrue even when the sensors don't emit state-change events."""
        if not self._cycle_active: return
        now = dt_util.utcnow().timestamp()
        if self._last_int_ts is None:
            self._last_int_ts = now; return
        dt_s = now - self._last_int_ts
        if dt_s <= 0:
            return
        # Read sensors live (not cached) so values are current every tick
        self._flow_w = self._read_flow_now()
        self._pump_w = self._read_pump_now()
        # Flow → litres
        delta_l = self._flow_w * dt_s / 60  # L/min × s / 60
        if delta_l > 0:
            self._l_total += delta_l; self._l_today += delta_l
            self._l_month += delta_l; self._l_year  += delta_l
        # Pump → kWh (+ FV split)
        delta_kwh = self._pump_w * dt_s / 3_600_000
        if delta_kwh > 0:
            self._kwh_total += delta_kwh; self._kwh_today += delta_kwh
            self._kwh_month += delta_kwh; self._kwh_year  += delta_kwh
            gf = self._fv_grid_fraction()
            if gf is not None:
                eg = delta_kwh * gf; es = delta_kwh - eg
                self._eg_today += eg; self._eg_month += eg; self._eg_year += eg
                self._es_today += es; self._es_month += es; self._es_year += es
        self._last_int_ts = now

    def _integrate_flow(self):
        self._integrate()

    def _integrate_pump(self):
        pass  # handled by _integrate (kept for compatibility)

    def _fv_grid_fraction(self):
        """Fraction (0..1) of current pump power drawn from the grid. None if FV off."""
        hub = get_hub_config(self.hass)
        if not hub.get("fv_enabled"): return None
        gs = hub.get("fv_grid_sensor")
        if not gs: return None
        st = self.hass.states.get(gs)
        if not st or st.state in ("unknown","unavailable",""): return None
        try: grid_w = float(st.state)
        except (ValueError, TypeError): return None
        if hub.get("fv_invert"):
            grid_w = -grid_w
        thr = hub.get("fv_threshold_w", 0.0)
        dev_w = self._pump_w
        if dev_w <= 0:
            return 1.0 if grid_w > thr else 0.0
        grid_draw = min(dev_w, max(0.0, grid_w))
        return max(0.0, min(1.0, grid_draw / dev_w))

    # ── Midnight reset ────────────────────────────────────────────────────────

    @callback
    def _on_midnight(self, now):
        self.hass.add_job(self._midnight, now)

    async def _midnight(self, now):
        today_it = WEEK_DAYS[now.weekday()]
        d = self.storage
        d.set("l_yesterday",    self._l_today)
        d.set("kwh_yesterday",  self._kwh_today)
        d.set("t_yesterday",    self._t_today)
        d.set("c_yesterday",    self._c_today)
        d.set_weekly(today_it, "cicli",  str(self._c_today))
        d.set_weekly(today_it, "tempo",  _fmt(self._t_today))
        d.set_weekly(today_it, "litri",  round(self._l_today, 1))
        d.set_weekly(today_it, "kwh",    round(self._kwh_today, 3))
        d.set("irr_eg_yesterday", self._eg_today)
        d.set("irr_es_yesterday", self._es_today)
        self._l_today = self._t_today = self._kwh_today = 0.0
        self._c_today = 0
        self._eg_today = self._es_today = 0.0
        if now.day == 1:
            d.set("l_last_month",   self._l_month)
            d.set("kwh_last_month", self._kwh_month)
            d.set("t_last_month",   self._t_month)
            d.set("c_last_month",   self._c_month)
            d.set("irr_eg_last_month", self._eg_month)
            d.set("irr_es_last_month", self._es_month)
            self._l_month = self._t_month = self._kwh_month = 0.0
            self._c_month = 0
            self._eg_month = self._es_month = 0.0
        if now.month == 1 and now.day == 1:
            d.set("l_last_year",   self._l_year)
            d.set("kwh_last_year", self._kwh_year)
            d.set("t_last_year",   self._t_year)
            d.set("c_last_year",   self._c_year)
            d.set("irr_eg_last_year", self._eg_year)
            d.set("irr_es_last_year", self._es_year)
            self._l_year = self._t_year = self._kwh_year = 0.0
            self._c_year = 0
            self._eg_year = self._es_year = 0.0
        await self._persist()
        # Re-schedule midnight
        nxt = now.replace(hour=0, minute=0, second=1) + timedelta(days=1)
        self._unsub.append(async_track_point_in_time(self.hass, self._on_midnight, nxt))
        self.async_set_updated_data(self._build())

    # ── Notifications ─────────────────────────────────────────────────────────

    async def _notify_complete(self, duration, l_consumed, kwh_consumed, hub):
        name = self.config.get(CONF_APPLIANCE_NAME, "Irrigazione")
        # Costs for the message
        cpp_kwh   = float(hub.get("costo_kwh", 0.0))
        cpp_acqua = float(hub.get("costo_acqua_m3", 0.0))
        costo_acqua = l_consumed / 1000.0 * cpp_acqua
        costo_pompa = kwh_consumed * cpp_kwh
        costo_tot   = round(costo_acqua + costo_pompa, 2)
        msg = (f"💧 {name} completata\n"
               f"⏱ {duration}\n"
               f"🚿 {l_consumed} L consumati\n"
               f"⚡ {kwh_consumed} kWh pompa\n"
               f"💰 Totale: {costo_tot} €")
        # FV split if enabled (read from a freshly-built snapshot, not self._d
        # which doesn't exist on this coordinator)
        snap = self._build()
        if hub.get("fv_enabled") and snap.get("costo_rete_oggi") is not None:
            rete = round(float(snap.get("costo_rete_oggi", 0.0)), 2)
            sole = round(float(snap.get("risparmio_sole_oggi", 0.0)), 2)
            msg += f"\n🔌 Rete: {rete} €  ☀️ Sole: {sole} €"
        speak = f"{name} completata in {duration}"
        await self._push_notify(hub, msg, f"💧 {name}", speak)

    async def _notify_skip_meteo(self):
        hub = get_hub_config(self.hass)
        name = self.config.get(CONF_APPLIANCE_NAME, "Irrigazione")
        msg = f"🌧️ {name}: ciclo saltato per previsione pioggia"
        await self._push_notify(hub, msg, f"💧 {name}", f"{name}: ciclo saltato per pioggia")

    def _slot_str(self) -> str:
        return str(self.config.get(CONF_SLOT, "1"))

    def _notify_sw_on(self, sfx: str) -> bool:
        """Read a per-device notification toggle switch state."""
        eid = f"switch.{sfx}_x{self._slot_str()}"
        st = self.hass.states.get(eid)
        return bool(st and st.state == "on")

    async def _push_notify(self, hub, message, title, speak_msg=None):
        """Send notification across enabled channels via the shared helper.
        Per-device toggles are read from the switch entities (single source)."""
        from .const import (
            SFX_SW_NOTIFY_PUSH, SFX_SW_NOTIFY_ALEXA,
            SFX_SW_NOTIFY_GOOGLE, SFX_SW_NOTIFY_WHATSAPP,
        )
        await async_send_notification(
            self.hass, hub,
            message=message, title=title, speak=speak_msg,
            push=self._notify_sw_on(SFX_SW_NOTIFY_PUSH),
            whatsapp=self._notify_sw_on(SFX_SW_NOTIFY_WHATSAPP),
            alexa=self._notify_sw_on(SFX_SW_NOTIFY_ALEXA),
            google=self._notify_sw_on(SFX_SW_NOTIFY_GOOGLE),
            log_id=f"IRR {self.instance_id}")

    async def _persist(self):
        s = self.storage
        s.set("l_total",    self._l_total);    s.set("kwh_total",  self._kwh_total)
        s.set("l_today",    self._l_today);    s.set("l_month",    self._l_month);    s.set("l_year",    self._l_year)
        s.set("kwh_today",  self._kwh_today);  s.set("kwh_month",  self._kwh_month);  s.set("kwh_year",  self._kwh_year)
        s.set("t_today",    self._t_today);    s.set("t_month",    self._t_month);    s.set("t_year",    self._t_year)
        s.set("c_today",    self._c_today);    s.set("c_month",    self._c_month);    s.set("c_year",    self._c_year)
        s.set("irr_eg_today", self._eg_today); s.set("irr_eg_month", self._eg_month); s.set("irr_eg_year", self._eg_year)
        s.set("irr_es_today", self._es_today); s.set("irr_es_month", self._es_month); s.set("irr_es_year", self._es_year)
        await s.async_save()

    async def async_set_maintenance(self, note: str = ""):
        """Register maintenance date/time (mirrors appliance coordinator)."""
        self.storage.set("maintenance_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        if note:
            self.storage.set("maintenance_note", note)
        await self._persist()
        self.async_set_updated_data(self._build())

    async def async_reset_all(self):
        """Alias for button compatibility."""
        await self.async_reset_counters()

    async def async_reset_counters(self):
        self._l_today   = self._l_month   = self._l_year   = 0.0
        self._kwh_today = self._kwh_month = self._kwh_year = 0.0
        self._t_today   = self._t_month   = self._t_year   = 0.0
        self._c_today   = self._c_month   = self._c_year   = 0
        # NOTE: _l_total / _kwh_total are intentionally NOT reset. They feed the
        # TOTAL_INCREASING sensors used by HA's Energy dashboard, which expects a
        # monotonic counter — zeroing it would corrupt the long-term graphs and
        # cost tracking. HA derives per-period figures from the running total.
        self._eg_today  = self._eg_month  = self._eg_year  = 0.0
        self._es_today  = self._es_month  = self._es_year  = 0.0
        self.storage.set("reset_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        await self._persist()
        self.async_set_updated_data(self._build())

    # ── Build data dict ───────────────────────────────────────────────────────


    def _build(self) -> dict[str, Any]:
        sd = self.storage.data
        az = self.active_zone

        # Hub cost rates for cost calculations
        hub       = get_hub_config(self.hass)
        cpp_kwh   = float(hub.get("costo_kwh",      0.0))
        cpp_acqua = float(hub.get("costo_acqua_m3", 0.0))

        # Weekly stats (with per-day costs: water €/m³, pump €/kWh)
        weekly = {}
        for day in WEEK_DAYS:
            w = sd.get("weekly", {}).get(day, {})
            _l = float(w.get("litri", 0.0))
            _k = float(w.get("kwh", 0.0))
            weekly[day] = {
                "cicli":  w.get("cicli", "0"),
                "tempo":  w.get("tempo", "0min"),
                "litri":  _l,
                "kwh":    _k,
                "costo_acqua": round(_l / 1000.0 * cpp_acqua, 2),
                "costo_kwh":   round(_k * cpp_kwh, 2),
            }

        return {
            "cycle_active":    self._cycle_active,
            "image_on":        (self.config.get(CONF_IMAGE_ON)  or "").strip(),
            "image_off":       (self.config.get(CONF_IMAGE_OFF) or "").strip(),
            "maintenance_date": sd.get("maintenance_date", ""),
            "reset_date":      sd.get("reset_date", ""),
            "notify_window_start": hub.get("notify_start_time", "08:00:00"),
            "notify_window_end":   hub.get("notify_end_time",   "22:00:00"),
            "active_zone_idx": self._active_zone_idx,
            "active_zone_name": az.get("name", "") if az else "",
            "last_zone_name":  sd.get("last_zone_name", ""),
            "last_zone_time":  sd.get("last_zone_time", ""),
            "active_zone_switch": az.get("switch", "") if az else "",
            "active_zone_duration_s": int(float(az.get("duration_min", 0)) * 60) if az else 0,
            "countdown_s":     self._countdown_s,
            "flow_lmin":       round(self._read_flow_now(), 2),
            "pump_w":          round(self._read_pump_now(), 1),
            "l_total":         round(self._l_total, 1),
            "kwh_total":       round(self._kwh_total, 3),
            "l_today":         round(self._l_today, 1),
            "l_month":         round(self._l_month, 1),
            "l_year":          round(self._l_year, 1),
            "l_yesterday":     round(sd.get("l_yesterday", 0.0), 1),
            "t_yesterday":     round(sd.get("t_yesterday", 0.0), 3),
            "c_yesterday":     int(sd.get("c_yesterday", 0)),
            "l_last_month":    round(sd.get("l_last_month", 0.0), 1),
            "l_last_year":     round(sd.get("l_last_year", 0.0), 1),
            "kwh_last_year":   round(sd.get("kwh_last_year", 0.0), 3),
            "t_last_month":    round(sd.get("t_last_month", 0.0), 3),
            "t_last_year":     round(sd.get("t_last_year", 0.0), 3),
            "c_last_month":    int(sd.get("c_last_month", 0)),
            "c_last_year":     int(sd.get("c_last_year", 0)),
            "t_yesterday_str":  _fmt(sd.get("t_yesterday", 0.0)),
            "t_last_month_str": _fmt(sd.get("t_last_month", 0.0)),
            "t_last_year_str":  _fmt(sd.get("t_last_year", 0.0)),
            "costo_acqua_ieri":      round(sd.get("l_yesterday", 0.0)  / 1000.0 * cpp_acqua, 3),
            "costo_kwh_ieri":        round(sd.get("kwh_yesterday", 0.0) * cpp_kwh, 3),
            "costo_acqua_mese_prec": round(sd.get("l_last_month", 0.0) / 1000.0 * cpp_acqua, 3),
            "costo_kwh_mese_prec":   round(sd.get("kwh_last_month", 0.0) * cpp_kwh, 3),
            "costo_acqua_anno_prec": round(sd.get("l_last_year", 0.0)  / 1000.0 * cpp_acqua, 3),
            "costo_kwh_anno_prec":   round(sd.get("kwh_last_year", 0.0) * cpp_kwh, 3),
            "kwh_today":       round(self._kwh_today, 3),
            "kwh_month":       round(self._kwh_month, 3),
            "kwh_year":        round(self._kwh_year, 3),
            "kwh_yesterday":   round(sd.get("kwh_yesterday", 0.0), 3),
            "kwh_last_month":  round(sd.get("kwh_last_month", 0.0), 3),
            "t_today":         self._t_today,
            "t_month":         self._t_month,
            "t_year":          self._t_year,
            "t_today_str":     _fmt(self._t_today),
            "c_today":         self._c_today,
            "c_month":         self._c_month,
            "c_year":          self._c_year,
            "zones":           self.zones,
            "zone_order":      self.zone_order,
            "version":         VERSION,
            "weekly":          weekly,
            "t_month_str":     _fmt(self._t_month),
            "t_year_str":      _fmt(self._t_year),
            # Aliases for JS card compatibility
            "ciclo_attivo":    self._cycle_active,
            "zona_attiva":     az.get("name", "") if az else "",
            "litri_oggi":      round(self._l_today, 1),
            "litri_mese":      round(self._l_month, 1),
            "litri_anno":      round(self._l_year, 1),
            "appliance_name":  self.config.get("appliance_name", "Irrigazione"),
            # Real zone switch entity_ids for online/offline detection in JS
            "real_zone_switches": [z.get("switch", "") for z in self.zones if z.get("switch")],
            "flow_sensor_eid":    (self.config.get(CONF_FLOW_SENSOR) or "").strip(),
            "pump_sensor_eid":    (self.config.get(CONF_PUMP_SENSOR) or "").strip(),
            # Cost calculations using hub prices
            "costo_kwh_oggi":   round(self._kwh_today * cpp_kwh, 3),
            "costo_kwh_mese":   round(self._kwh_month * cpp_kwh, 3),
            "costo_kwh_anno":   round(self._kwh_year  * cpp_kwh, 3),
            "fv_enabled":       bool(hub.get("fv_enabled")),
            "costo_rete_oggi":  round(self._eg_today * cpp_kwh, 3),
            "costo_rete_mese":  round(self._eg_month * cpp_kwh, 3),
            "costo_rete_anno":  round(self._eg_year  * cpp_kwh, 3),
            "risparmio_sole_oggi": round(self._es_today * cpp_kwh, 3),
            "risparmio_sole_mese": round(self._es_month * cpp_kwh, 3),
            "risparmio_sole_anno": round(self._es_year  * cpp_kwh, 3),
            "costo_rete_ieri":      round(sd.get("irr_eg_yesterday",0.0) * cpp_kwh, 3),
            "costo_rete_mese_prec": round(sd.get("irr_eg_last_month",0.0) * cpp_kwh, 3),
            "costo_rete_anno_prec": round(sd.get("irr_eg_last_year",0.0)  * cpp_kwh, 3),
            "risparmio_sole_ieri":      round(sd.get("irr_es_yesterday",0.0) * cpp_kwh, 3),
            "risparmio_sole_mese_prec": round(sd.get("irr_es_last_month",0.0) * cpp_kwh, 3),
            "risparmio_sole_anno_prec": round(sd.get("irr_es_last_year",0.0)  * cpp_kwh, 3),
            "costo_acqua_oggi": round(self._l_today  / 1000.0 * cpp_acqua, 3),
            "costo_acqua_mese": round(self._l_month  / 1000.0 * cpp_acqua, 3),
            "costo_acqua_anno": round(self._l_year   / 1000.0 * cpp_acqua, 3),
            "costo_tot_oggi": round(self._l_today / 1000.0 * cpp_acqua + self._kwh_today * cpp_kwh, 3),
            "costo_tot_mese": round(self._l_month / 1000.0 * cpp_acqua + self._kwh_month * cpp_kwh, 3),
            "costo_tot_anno": round(self._l_year  / 1000.0 * cpp_acqua + self._kwh_year  * cpp_kwh, 3),
        }

    # ── Coordinator update ────────────────────────────────────────────────────

    async def _async_update_data(self) -> dict[str, Any]:
        if self._cycle_active:
            dh = COORDINATOR_UPDATE_INTERVAL / 3600.0
            self._t_today += dh; self._t_month += dh; self._t_year += dh
        data = self._build()
        # Skip no-op re-renders to avoid flooding the WebSocket (irrigation
        # exposes many sensors; pushing identical data every poll caused the
        # 'pending messages' warning).
        last = getattr(self, "_last_pushed", None)
        if data == last:
            return last
        self._last_pushed = data
        return data

    async def async_unload(self):
        for unsub in self._unsub + self._sched_unsubs:
            try: unsub()
            except Exception: pass
        self._stop_countdown()
        if self._cycle_task and not self._cycle_task.done():
            self._stop_requested = True
