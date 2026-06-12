# ============================================================
# FILE:    select.py
# VERSION: 5.0.0
# DESC:    Select platform — climate mode selector
# CHANGED: 2026-06-11
# ============================================================
"""Select platform for Elettrodomestico Monitor — climate mode selector."""
from __future__ import annotations
import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, CONF_ENTRY_TYPE, ENTRY_TYPE_HUB, CONF_TRIGGER_ENTITY

_LOGGER = logging.getLogger(__name__)

CLIMA_MODES = ["cool", "heat", "heat_cool", "auto", "dry", "fan_only"]

try:
    from .const import ENTRY_TYPE_IRRIGATION
except ImportError:
    ENTRY_TYPE_IRRIGATION = "irrigation"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    # Skip hub and irrigation
    et = entry.data.get(CONF_ENTRY_TYPE) or entry.data.get("entry_type", "")
    if et in (ENTRY_TYPE_HUB, ENTRY_TYPE_IRRIGATION, "hub", "irrigation"):
        return

    # Only clima preset
    if entry.data.get("preset") != "clima":
        return

    coord = hass.data[DOMAIN].get(entry.entry_id)
    if not coord:
        _LOGGER.warning("[CLIMA SELECT] coord not found for entry %s", entry.entry_id)
        return

    name = entry.data.get("appliance_name", "Clima")
    slot = str(entry.data.get("slot", "1"))
    iid  = entry.data.get("instance_id", "x")
    eid  = (entry.data.get(CONF_TRIGGER_ENTITY) or "").strip()

    _LOGGER.warning("[CLIMA SELECT] Setting up for %s, trigger_entity=%s", name, eid)

    dev_info = DeviceInfo(
        identifiers={(DOMAIN, iid)},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Clima",
        configuration_url="https://github.com/Destroyer061090/elettrodomestico-monitor",
    )

    # Determine available modes from the actual climate entity
    def _get_modes():
        if not eid: return CLIMA_MODES
        st = hass.states.get(eid)
        if st:
            modes = st.attributes.get("hvac_modes", [])
            if modes:
                return [m for m in modes if m != "off"]
        return CLIMA_MODES

    class _ClimaModeSelect(SelectEntity):
        def __init__(self):
            self._attr_unique_id   = f"{DOMAIN}_{iid}_clima_mode_x{slot}"
            self.entity_id         = f"select.clima_modalita_x{slot}"
            self._attr_name        = f"Modalità {name}"
            self._attr_icon        = "mdi:thermostat"
            self._attr_device_info = dev_info
            # Initialize modes from actual climate entity (or default)
            self._attr_options     = _get_modes()
            # Initialize current mode from climate entity or storage
            self._attr_current_option = self._read_current()

        def _read_current(self) -> str:
            """Read current hvac_mode from real climate entity."""
            if eid:
                st = hass.states.get(eid)
                if st and st.state not in ("off", "unavailable", "unknown", ""):
                    return st.state
            return coord.storage.get("last_clima_mode", "heat") or "heat"

        async def async_added_to_hass(self) -> None:
            """Wire state tracking when entity is added."""
            if eid:
                self.async_on_remove(
                    async_track_state_change_event(
                        self.hass, [eid], self._on_climate_change))
                # Update modes from actual entity
                modes = _get_modes()
                if modes != self._attr_options:
                    self._attr_options = modes
                    self.async_write_ha_state()

        @callback
        def _on_climate_change(self, event) -> None:
            """Update select when real climate entity changes."""
            new = event.data.get("new_state")
            if new is None: return
            if new.state not in ("off", "unavailable", "unknown", ""):
                self._attr_current_option = new.state
                coord.storage.set("last_clima_mode", new.state)
                self.async_write_ha_state()

        async def async_select_option(self, option: str) -> None:
            _LOGGER.warning("[CLIMA SELECT] async_select_option called: %s → %s",
                            option, eid)
            # Save mode to storage
            coord.storage.set("last_clima_mode", option)
            self._attr_current_option = option
            self.async_write_ha_state()

            if not eid:
                _LOGGER.error("[CLIMA SELECT] No trigger_entity! Cannot set mode.")
                return

            # If climate is currently on → change mode immediately
            st = hass.states.get(eid)
            _LOGGER.warning("[CLIMA SELECT] Climate %s state: %s", eid,
                            st.state if st else "None")
            if st and st.state not in ("off", "unavailable", "unknown", ""):
                try:
                    await hass.services.async_call(
                        "climate", "set_hvac_mode",
                        {"entity_id": eid, "hvac_mode": option})
                    _LOGGER.warning("[CLIMA SELECT] ✅ set_hvac_mode(%s) sent to %s",
                                    option, eid)
                except Exception as ex:
                    _LOGGER.error("[CLIMA SELECT] ❌ set_hvac_mode failed: %s", ex)
            else:
                _LOGGER.warning("[CLIMA SELECT] Climate is OFF — mode %s saved for next on",
                                option)

    async_add_entities([_ClimaModeSelect()], update_before_add=True)
