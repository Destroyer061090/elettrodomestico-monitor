# ============================================================
# FILE:    number.py
# VERSION: 5.0.4
# DESC:    Number platform — configurable thresholds, zone durations
# CHANGED: 2026-06-11
# ============================================================
"""Number platform for Elettrodomestico Monitor v6.

Creates 3 number entities per device (modifiable at runtime from HA dashboard):
  number.soglia_lavoro_elettrodomestici_w_x1    ← detection threshold (W)
  number.tempo_innesco_elettrodomestici_m_x1    ← delay_off (minutes)
  number.avvio_ritardato_elettrodomestici_s_x1  ← delay_on  (seconds)
"""
from __future__ import annotations
import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    CONF_WORK_THRESHOLD_W, CONF_TRIGGER_DELAY_M, CONF_START_DELAY_S,
    SFX_NUM_SOGLIA, SFX_NUM_DELAY_OFF, SFX_NUM_DELAY_ON,
    DEFAULT_THRESHOLD_W, DEFAULT_TRIGGER_DELAY_M, DEFAULT_START_DELAY_S,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        return
    from .const import ENTRY_TYPE_IRRIGATION
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or        entry.data.get("entry_type") == "irrigation":
        coord = hass.data[DOMAIN][entry.entry_id]
        await _async_setup_irrigation_numbers(hass, entry, coord, async_add_entities)
        return
    from .const import ENTRY_TYPE_IRRIGATION
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or        entry.data.get("entry_type") == "irrigation":
        coord = hass.data[DOMAIN][entry.entry_id]
        await _async_setup_irrigation_numbers(hass, entry, coord, async_add_entities)
        return
    name = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    iid  = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))

    async_add_entities([
        _NumberEntity(
            entry, name, slot, iid,
            sfx       = SFX_NUM_SOGLIA,
            label     = f"Soglia Lavoro {name} W",
            min_val   = 0, max_val = 5000, step = 1.0,
            unit      = "W",
            icon      = "mdi:flash",
            conf_key  = CONF_WORK_THRESHOLD_W,
            default   = float(DEFAULT_THRESHOLD_W),
        ),
        _NumberEntity(
            entry, name, slot, iid,
            sfx       = SFX_NUM_DELAY_OFF,
            label     = f"Tempo Innesco {name} M",
            min_val   = 0, max_val = 60, step = 1.0,
            unit      = "min",
            icon      = "mdi:timer-off-outline",
            conf_key  = CONF_TRIGGER_DELAY_M,
            default   = float(DEFAULT_TRIGGER_DELAY_M),
        ),
        _NumberEntity(
            entry, name, slot, iid,
            sfx       = SFX_NUM_DELAY_ON,
            label     = f"Avvio Ritardato {name} S",
            min_val   = 0, max_val = 60, step = 1.0,
            unit      = "s",
            icon      = "mdi:timer-play-outline",
            conf_key  = CONF_START_DELAY_S,
            default   = float(DEFAULT_START_DELAY_S),
        ),
    ])


def _device(entry, name):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Elettrodomestici",
        sw_version="4.6",
    )


class _NumberEntity(NumberEntity, RestoreEntity):
    """A number entity that restores its value across restarts."""

    def __init__(self, entry, name, slot, iid, *, sfx, label, min_val,
                 max_val, step, unit, icon, conf_key, default):
        self._entry    = entry
        self._conf_key = conf_key
        self._default  = default
        self._current_value: float = default

        self._attr_unique_id   = f"{DOMAIN}_{iid}_{sfx}_x{slot}"
        self.entity_id         = f"number.{sfx}_x{slot}"
        self._attr_name        = label
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step  = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon         = icon
        self._attr_mode         = NumberMode.BOX
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info  = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        """Restore previous value or use config entry default."""
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            try:
                self._current_value = float(last.state)
                return
            except (ValueError, TypeError):
                pass
        # Fall back to config entry value
        self._current_value = float(self._entry.data.get(self._conf_key, self._default))

    @property
    def native_value(self) -> float:
        return self._current_value

    async def async_set_native_value(self, value: float) -> None:
        self._current_value = value
        self.async_write_ha_state()
        _LOGGER.debug("Number %s set to %s", self.entity_id, value)


async def _async_setup_irrigation_numbers(
    hass, entry, coord, async_add_entities
) -> None:
    """Create zone duration number entities for irrigation device."""
    from homeassistant.components.number import NumberMode
    from homeassistant.helpers.entity import DeviceInfo

    name  = entry.data.get("appliance_name", "Irrigazione")
    slot  = str(entry.data.get("slot", "1"))
    iid   = entry.data.get("instance_id", "irr")
    DOMAIN_LOCAL = "elettrodomestico_monitor"

    dev_info = DeviceInfo(
        identifiers={(DOMAIN_LOCAL, iid)},
        name=name, manufacturer="Elettrodomestico Monitor", model="Irrigazione",
    )

    class _ZoneDuration(NumberEntity):
        def __init__(self, zone_idx, zone):
            self._zone_idx = zone_idx
            self._val      = float(zone.get("duration_min", 10))
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_irr_dur_z{zone_idx}_x{slot}"
            self.entity_id         = f"number.irrigazione_z{zone_idx+1}_durata_x{slot}"
            self._attr_name        = f"Durata {zone.get('name', f'Zona {zone_idx+1}')} {name}"
            self._attr_icon        = "mdi:timer"
            self._attr_native_min_value = 1
            self._attr_native_max_value = 180
            self._attr_native_step  = 1
            self._attr_native_unit_of_measurement = "min"
            self._attr_mode        = NumberMode.SLIDER
            self._attr_device_info = dev_info
        @property
        def native_value(self): return self._val
        async def async_set_native_value(self, value: float) -> None:
            self._val = value
            self.async_write_ha_state()
            zones = list(coord.config.get("zones") or [])
            if self._zone_idx < len(zones):
                zones[self._zone_idx] = dict(zones[self._zone_idx])
                zones[self._zone_idx]["duration_min"] = value
                hass.config_entries.async_update_entry(
                    entry, data={**coord.config, "zones": zones})

    num_entities = [_ZoneDuration(i, zone) for i, zone in enumerate(coord.zones)]
    async_add_entities(num_entities)
