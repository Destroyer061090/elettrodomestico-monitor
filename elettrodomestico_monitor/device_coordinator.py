# VERSION: 5.7.1
# CHANGED: 2026-07-23 (v6.2.3: guardia contro soglie avvio/stop invertite o
#          coincidenti — causavano toggling continuo, confermato con
#          esecuzione reale. Vedi CHANGELOG.md)
# DESC: Device (battery charge manager) coordinator — monitors % battery,
#       auto charge control with hysteresis, cycle + time tracking, notifications.

from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_SLOT, CONF_APPLIANCE_NAME,
    COORDINATOR_UPDATE_INTERVAL,
    CONF_DEV_BATTERY_SENSOR, CONF_DEV_CHARGE_SWITCH,
    CONF_DEV_START_PCT, CONF_DEV_STOP_PCT,
    DEFAULT_DEV_START_PCT, DEFAULT_DEV_STOP_PCT,
    SFX_SW_NOTIFY_PUSH, SFX_SW_NOTIFY_ALEXA,
    SFX_SW_NOTIFY_GOOGLE, SFX_SW_NOTIFY_WHATSAPP,
)
from .storage import ElettrodomesticoStorage
from .hub import get_hub_config
from .notify_helper import async_send_notification

_LOGGER = logging.getLogger(__name__)

WEEK_DAYS = ["lunedi","martedi","mercoledi","giovedi","venerdi","sabato","domenica"]


def _parse_time(s: str) -> tuple[int, int]:
    try:
        p = str(s).split(":")
        return int(p[0]), int(p[1])
    except (ValueError, IndexError):
        return 0, 0


def _fmt_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, _ = divmod(rem, 60)
    if d > 0: return f"{d}d {h}h {m}m"
    if h > 0: return f"{h}h {m}m"
    return f"{m} min"


class DeviceCoordinator(DataUpdateCoordinator):
    """Manages a battery device: reads %, controls charging plug, tracks cycles/time."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_dev_{entry.data.get(CONF_INSTANCE_ID, 'x')}",
            update_interval=timedelta(seconds=COORDINATOR_UPDATE_INTERVAL),
        )
        self.entry       = entry
        self.config      = entry.data
        self.instance_id = entry.data.get(CONF_INSTANCE_ID, "dev")
        self.slot        = str(entry.data.get(CONF_SLOT, "1"))
        self.storage     = ElettrodomesticoStorage(hass, self.instance_id)

        self._battery_sensor = entry.data.get(CONF_DEV_BATTERY_SENSOR, "")
        self._charge_switch  = entry.data.get(CONF_DEV_CHARGE_SWITCH, "")

        # Runtime
        self._battery_pct: float | None = None
        self._charging: bool = False
        self._last_change_ts: float = dt_util.utcnow().timestamp()
        self._last_midnight_day = dt_util.now().day

        # Counters
        self._c_today = self._c_month = self._c_year = 0
        self._c_total = 0

    async def async_init(self):
        await self.storage.async_load()
        d = self.storage.data
        self._c_today = d.get("dev_c_today", 0)
        self._c_month = d.get("dev_c_month", 0)
        self._c_year  = d.get("dev_c_year", 0)
        self._c_total = d.get("dev_c_total", 0)
        self._last_change_ts = d.get("dev_last_change_ts", dt_util.utcnow().timestamp())

    # ── helpers ───────────────────────────────────────────────────────────────
    def _start_pct(self) -> float:
        eid = f"number.{ 'soglia_avvio_carica' }_x{self.slot}"
        st = self.hass.states.get(eid)
        if st and st.state not in ("unknown","unavailable",""):
            try: return float(st.state)
            except ValueError: pass
        return float(self.config.get(CONF_DEV_START_PCT, DEFAULT_DEV_START_PCT))

    def _stop_pct(self) -> float:
        eid = f"number.{ 'soglia_stop_carica' }_x{self.slot}"
        st = self.hass.states.get(eid)
        if st and st.state not in ("unknown","unavailable",""):
            try: return float(st.state)
            except ValueError: pass
        return float(self.config.get(CONF_DEV_STOP_PCT, DEFAULT_DEV_STOP_PCT))

    def _auto_on(self) -> bool:
        st = self.hass.states.get(f"switch.ricarica_auto_dispositivo_x{self.slot}")
        return bool(st and st.state == "on")

    def _read_battery(self) -> float | None:
        if not self._battery_sensor: return None
        st = self.hass.states.get(self._battery_sensor)
        if not st or st.state in ("unknown","unavailable",""): return None
        try: return float(st.state)
        except (ValueError, TypeError): return None

    def _read_charging(self) -> bool:
        if not self._charge_switch: return False
        st = self.hass.states.get(self._charge_switch)
        return bool(st and st.state == "on")

    async def _set_charge(self, on: bool):
        if not self._charge_switch: return
        svc = "turn_on" if on else "turn_off"
        try:
            await self.hass.services.async_call(
                "homeassistant", svc, {"entity_id": self._charge_switch})
        except Exception as ex:
            _LOGGER.error("[DEV %s] charge %s failed: %s", self.instance_id, svc, ex)

    # ── notifications (multi-channel, same pattern as irrigation) ──────────────
    def _notify_sw_on(self, sfx: str) -> bool:
        st = self.hass.states.get(f"switch.{sfx}_x{self.slot}")
        return bool(st and st.state == "on")

    async def _notify(self, message: str, title: str, speak: str | None = None):
        hub = get_hub_config(self.hass)
        await async_send_notification(
            self.hass, hub,
            message=message, title=title, speak=speak,
            push=self._notify_sw_on(SFX_SW_NOTIFY_PUSH),
            whatsapp=self._notify_sw_on(SFX_SW_NOTIFY_WHATSAPP),
            alexa=self._notify_sw_on(SFX_SW_NOTIFY_ALEXA),
            google=self._notify_sw_on(SFX_SW_NOTIFY_GOOGLE),
            log_id=f"DEV x{self.slot}")

    def _device_name(self) -> str:
        st = self.hass.states.get(f"text.nome_dispositivo_x{self.slot}")
        if st and st.state not in ("unknown","unavailable",""):
            return st.state
        return self.config.get(CONF_APPLIANCE_NAME, "Dispositivo")

    # ── main update ────────────────────────────────────────────────────────────
    async def _async_update_data(self) -> dict[str, Any]:
        # Midnight rollover
        now = dt_util.now()
        if now.day != self._last_midnight_day:
            await self._rollover(now)
            self._last_midnight_day = now.day

        prev_charging = self._charging
        self._battery_pct = self._read_battery()
        # On the very first update, sync the logical state from the plug so we
        # don't desync if charging was already in progress before startup.
        if not getattr(self, "_charge_synced", False):
            self._charging = self._read_charging()
            self._charge_synced = True
        # When auto-control is OFF, the logical state follows the plug reading.
        # When auto is ON, the logical state is driven by the hysteresis block
        # below (not the raw plug), to avoid notification loops on a slow switch.
        elif not self._auto_on():
            self._charging = self._read_charging()

        # Track time on state change
        if self._charging != prev_charging:
            self.storage.set("dev_last_change_ts", dt_util.utcnow().timestamp())
            self._last_change_ts = dt_util.utcnow().timestamp()
            await self.storage.async_save()

        # Auto charge control with hysteresis.
        # Use a LOGICAL charge state (decided by thresholds), not the raw plug
        # reading, so a slow/desynced switch can't retrigger notifications.
        if self._auto_on() and self._battery_pct is not None:
            start = self._start_pct(); stop = self._stop_pct()
            # FIX (audit v6.2.3): se le soglie sono invertite o coincidenti
            # (start >= stop — configurabile sia in config_flow che dai
            # number entity in dashboard, nessuno dei due valida la coppia),
            # la logica sotto toggla carica ON/OFF ad ogni singolo update
            # (confermato con esecuzione reale: 6 cambi su 6 update),
            # gonfiando il conteggio cicli e spammando notifiche. Se la
            # configurazione non ha senso, non fare nulla invece di
            # comportarsi in modo imprevedibile.
            if start >= stop:
                _LOGGER.warning(
                    "[EM Device] '%s': soglia avvio (%.0f%%) >= soglia stop "
                    "(%.0f%%) — controllo automatico sospeso finché non "
                    "vengono corrette.", self._device_name(), start, stop)
            elif not self._charging and self._battery_pct <= start:
                # Only act on a real transition (was not charging → start)
                self._charging = True
                await self._set_charge(True)
                self._c_today += 1; self._c_month += 1; self._c_year += 1; self._c_total += 1
                self.storage.set("dev_last_change_ts", dt_util.utcnow().timestamp())
                await self._persist()
                name = self._device_name()
                await self._notify(
                    f"{name} con batteria scarica. Ricarica automatica in corso! 🔌",
                    "🔌 Batteria Scarica 🔌", f"{name} in ricarica")
            elif self._charging and self._battery_pct >= stop:
                self._charging = False
                await self._set_charge(False)
                self.storage.set("dev_last_change_ts", dt_util.utcnow().timestamp())
                await self._persist()
                name = self._device_name()
                dur = _fmt_duration(dt_util.utcnow().timestamp() - self._last_change_ts)
                await self._notify(
                    f"Ricarica {name} completata in ⌛️ {dur}",
                    "🔋 Ricarica Completata 🔋", f"Ricarica {name} completata")

        return self._build()

    async def _rollover(self, now):
        d = self.storage
        d.set("dev_c_yesterday", self._c_today)
        d.set("dev_c_today", 0); self._c_today = 0
        if now.day == 1:
            d.set("dev_c_last_month", self._c_month); self._c_month = 0
        if now.month == 1 and now.day == 1:
            d.set("dev_c_last_year", self._c_year); self._c_year = 0
        await self._persist(); await self.storage.async_save()

    async def _persist(self):
        d = self.storage
        d.set("dev_c_today", self._c_today)
        d.set("dev_c_month", self._c_month)
        d.set("dev_c_year", self._c_year)
        d.set("dev_c_total", self._c_total)
        await self.storage.async_save()

    async def async_reset_counters(self):
        self._c_today = self._c_month = self._c_year = self._c_total = 0
        self.storage.set("dev_reset_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        await self._persist()
        self.async_set_updated_data(self._build())

    async def async_reset_all(self):
        await self.async_reset_counters()

    async def async_set_maintenance(self, note: str = ""):
        self.storage.set("dev_maintenance_date", dt_util.now().strftime("%d/%m/%Y %H:%M"))
        await self.storage.async_save()
        self.async_set_updated_data(self._build())

    def _build(self) -> dict[str, Any]:
        sd = self.storage.data
        elapsed = dt_util.utcnow().timestamp() - self._last_change_ts
        stato = ("In ricarica" if self._charging
                 else "A batteria" if self._battery_pct is not None
                 else "Non disponibile")
        return {
            "battery_pct":    self._battery_pct if self._battery_pct is not None else 0,
            "charging":       self._charging,
            "stato_carica":   stato,
            "tempo_in_carica": _fmt_duration(elapsed) if self._charging else "A Batteria",
            "tempo_a_batteria": _fmt_duration(elapsed) if not self._charging else "In Ricarica",
            "ricariche_oggi":  self._c_today,
            "ricariche_mese":  self._c_month,
            "ricariche_anno":  self._c_year,
            "ricariche_totali": self._c_total,
            "ricariche_ieri":  sd.get("dev_c_yesterday", 0),
            "ricariche_mese_prec": sd.get("dev_c_last_month", 0),
            "ricariche_anno_prec": sd.get("dev_c_last_year", 0),
            "soglia_avvio":    self._start_pct(),
            "soglia_stop":     self._stop_pct(),
            "auto_attivo":     self._auto_on(),
            "charge_switch_eid": self._charge_switch,
            "battery_sensor_eid": self._battery_sensor,
            "maintenance_date": sd.get("dev_maintenance_date", ""),
            "reset_date":      sd.get("dev_reset_date", ""),
            "nome":            self._device_name(),
            "image_on":        self.config.get("image_on", ""),
            "image_off":       self.config.get("image_off", ""),
            "version":         "5.4.0",
        }
