# ============================================================
# FILE:    time.py
# VERSION: 5.0.4
# DESC:    Time platform — auto on/off schedules, irrigation schedule times
# CHANGED: 2026-06-11
# ============================================================
"""Time platform for Elettrodomestico Monitor v8.

Creates 2 time-only entities per device (no date, just HH:MM:SS):
  time.orario_accensione_elettrodomestici_x1
  time.orario_spegnimento_elettrodomestici_x1

00:00:00 = disabled.
"""
from __future__ import annotations
import logging
from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    SFX_TIME_AUTO_ON, SFX_TIME_AUTO_OFF,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        return
    try:
        from .const import ENTRY_TYPE_IRRIGATION
        if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or
                entry.data.get("entry_type") == "irrigation"):
            coord = hass.data[DOMAIN][entry.entry_id]
            await _async_setup_irrigation_time(hass, entry, coord, async_add_entities)
            return
    except (ImportError, KeyError):
        pass
    name = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    iid  = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
    async_add_entities([
        _TimeEntity(entry, name, slot, iid,
                    sfx=SFX_TIME_AUTO_ON,  label=f"Accensione Automatica {name}", icon="mdi:clock-start"),
        _TimeEntity(entry, name, slot, iid,
                    sfx=SFX_TIME_AUTO_OFF, label=f"Spegnimento Automatico {name}", icon="mdi:clock-end"),
    ])


def _device(entry, name):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name, manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo", sw_version="4.8",
    )


class _TimeEntity(TimeEntity, RestoreEntity):
    """Time-only entity for schedule. 00:00:00 = disabled."""

    def __init__(self, entry, name, slot, iid, *, sfx, label, icon):
        self._entry = entry
        self._current: time = time(0, 0, 0)
        self._attr_unique_id       = f"{DOMAIN}_{iid}_{sfx}_x{slot}"
        self.entity_id             = f"time.{sfx}_x{slot}"
        self._attr_name            = label
        self._attr_icon            = icon
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            try:
                parts = last.state.split(":")
                self._current = time(int(parts[0]), int(parts[1]),
                                     int(parts[2]) if len(parts) > 2 else 0)
            except (ValueError, IndexError):
                pass

    @property
    def native_value(self) -> time:
        return self._current

    async def async_set_value(self, value: time) -> None:
        self._current = value
        self.async_write_ha_state()

    @property
    def time_str(self) -> str:
        return self._current.strftime("%H:%M:%S")

    @property
    def is_disabled_schedule(self) -> bool:
        return self._current.hour == 0 and self._current.minute == 0 and self._current.second == 0


async def _async_setup_irrigation_time(
    hass, entry, coord, async_add_entities
) -> None:
    """Create time entities for irrigation schedule slots."""
    from homeassistant.components.time import TimeEntity
    from homeassistant.helpers.entity import DeviceInfo
    from datetime import time as dt_time

    name  = entry.data.get("appliance_name", "Irrigazione")
    slot  = str(entry.data.get("slot", "1"))
    iid   = entry.data.get("instance_id", "irr")
    DOMAIN_LOCAL = "elettrodomestico_monitor"

    dev_info = DeviceInfo(
        identifiers={(DOMAIN_LOCAL, iid)},
        name=name, manufacturer="Elettrodomestico Monitor", model="Irrigazione",
    )

    class _SchedTime(TimeEntity):
        """Editable time entity for one irrigation schedule slot."""
        def __init__(self, sched_num: int, conf_key: str):
            self._sched_num   = sched_num
            self._conf_key    = conf_key
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_irr_s{sched_num}_time_x{slot}"
            self.entity_id         = f"time.irrigazione_s{sched_num}_orario_x{slot}"
            self._attr_name        = f"Programma {sched_num} Orario {name}"
            self._attr_icon        = "mdi:clock-start"
            self._attr_device_info = dev_info

        @property
        def native_value(self) -> dt_time | None:
            sched = coord.config.get(self._conf_key) or {}
            t = sched.get("time", "00:00:00")
            try:
                parts = str(t).split(":")
                return dt_time(int(parts[0]), int(parts[1]))
            except Exception:
                return dt_time(0, 0)

        async def async_set_value(self, value: dt_time) -> None:
            conf = dict(coord.config)
            sched = dict(conf.get(self._conf_key) or {})
            sched["time"] = f"{value.hour:02d}:{value.minute:02d}:00"
            if not sched.get("days"):   sched["days"] = []
            if not sched.get("mode"):   sched["mode"] = "fixed"
            conf[self._conf_key] = sched
            hass.config_entries.async_update_entry(entry, data=conf)
            # Rewire schedules with small debounce to avoid UI refresh during typing
            async def _delayed_wire():
                import asyncio
                await asyncio.sleep(3.0)
                try:
                    coord._wire_schedules()
                except Exception:
                    pass
            hass.async_create_task(_delayed_wire())
            self.async_write_ha_state()

    time_entities = [
        _SchedTime(1, "irr_schedule_1"),
        _SchedTime(2, "irr_schedule_2"),
        _SchedTime(3, "irr_schedule_3"),
    ]
    async_add_entities(time_entities)
