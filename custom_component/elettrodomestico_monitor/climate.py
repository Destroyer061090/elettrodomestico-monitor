# ============================================================
# FILE:    climate.py
# VERSION: 5.0.4
# DESC:    Climate platform — wrapper entity for clima preset devices
# CHANGED: 2026-06-11
# ============================================================
"""Climate platform for Elettrodomestico Monitor v26.

Creates climate.elettrodomestici_xN for clima preset devices.
Wraps the real climate entity (CONF_TRIGGER_ENTITY) exposing:
  - State: heating / cooling / idle / off
  - Temperature control
  - HVAC mode control
Follows external changes (telecomando, app) via state tracking.
"""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
    HVACAction,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    CONF_TRIGGER_ENTITY, CONF_PRESET,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
)
from .coordinator import ElettrodomesticoCoordinator

_LOGGER = logging.getLogger(__name__)

SFX_CLIMA = "elettrodomestici"

_HVAC_MODE_MAP = {
    "heat":      HVACMode.HEAT,
    "cool":      HVACMode.COOL,
    "heat_cool": HVACMode.HEAT_COOL,
    "auto":      HVACMode.AUTO,
    "dry":       HVACMode.DRY,
    "fan_only":  HVACMode.FAN_ONLY,
    "off":       HVACMode.OFF,
}

_HVAC_ACTION_MAP = {
    "heating": HVACAction.HEATING,
    "cooling": HVACAction.COOLING,
    "idle":    HVACAction.IDLE,
    "off":     HVACAction.OFF,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        return
    if entry.data.get(CONF_PRESET) != "clima":
        return
    clima_eid = (entry.data.get(CONF_TRIGGER_ENTITY) or "").strip()
    if not clima_eid:
        _LOGGER.warning("[EM] Clima preset but no trigger_entity configured — skipping climate entity")
        return

    coord: ElettrodomesticoCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_APPLIANCE_NAME, "Clima")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    async_add_entities([_ClimaEntity(coord, entry, name, slot, clima_eid)])


def _device(entry, name):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Clima",
        sw_version="4.26",
    )


class _ClimaEntity(CoordinatorEntity, ClimateEntity):
    """
    Climate entity that mirrors and controls the real climate device.
    entity_id: climate.elettrodomestici_xN
    Follows external changes automatically via state tracking.
    """

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coord, entry, name, slot, clima_eid):
        super().__init__(coord)
        self._entry     = entry
        self._clima_eid = clima_eid

        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id   = f"{DOMAIN}_{iid}_{SFX_CLIMA}_clima_x{slot}"
        self.entity_id         = f"climate.{SFX_CLIMA}_x{slot}"
        self._attr_name        = name
        self._attr_icon        = entry.data.get("device_icon", "mdi:thermostat")
        self._attr_device_info = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Track real climate changes for immediate UI sync
        if self._clima_eid:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._clima_eid], self._on_climate_change)
            )

    @callback
    def _on_climate_change(self, event) -> None:
        """Sync state when real climate changes (from remote, app, etc.)"""
        self.async_write_ha_state()

    def _real_state(self):
        """Get state object of the real climate entity."""
        return self.hass.states.get(self._clima_eid)

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def hvac_mode(self) -> HVACMode:
        st = self._real_state()
        if st is None: return HVACMode.OFF
        return _HVAC_MODE_MAP.get(st.state.lower(), HVACMode.OFF)

    @property
    def hvac_modes(self) -> list[HVACMode]:
        st = self._real_state()
        if st is None: return [HVACMode.OFF, HVACMode.HEAT]
        raw = st.attributes.get("hvac_modes", ["off", "heat"])
        return [_HVAC_MODE_MAP.get(m, HVACMode.OFF) for m in raw]

    @property
    def hvac_action(self) -> HVACAction | None:
        st = self._real_state()
        if st is None: return None
        action = st.attributes.get("hvac_action")
        return _HVAC_ACTION_MAP.get(action) if action else None

    @property
    def current_temperature(self) -> float | None:
        st = self._real_state()
        if st is None: return None
        return st.attributes.get("current_temperature")

    @property
    def target_temperature(self) -> float | None:
        st = self._real_state()
        if st is None: return None
        return st.attributes.get("temperature")

    @property
    def target_temperature_step(self) -> float:
        st = self._real_state()
        if st: return st.attributes.get("target_temp_step", 0.5)
        return 0.5

    @property
    def min_temp(self) -> float:
        st = self._real_state()
        if st: return st.attributes.get("min_temp", 5.0)
        return 5.0

    @property
    def max_temp(self) -> float:
        st = self._real_state()
        if st: return st.attributes.get("max_temp", 35.0)
        return 35.0

    @property
    def fan_mode(self) -> str | None:
        st = self._real_state()
        return st.attributes.get("fan_mode") if st else None

    @property
    def fan_modes(self) -> list[str] | None:
        st = self._real_state()
        return st.attributes.get("fan_modes") if st else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {"entita_clima": self._clima_eid}
        st = self._real_state()
        if st:
            for k in ("preset_mode", "preset_modes", "swing_mode",
                      "swing_modes", "aux_heat"):
                v = st.attributes.get(k)
                if v is not None: attrs[k] = v
        d = self.coordinator.data or {}
        attrs["cicli_oggi"]  = d.get("cycles_today", 0)
        attrs["tempo_oggi"]  = d.get("time_today_str", "0min")
        attrs["kwh_oggi"]    = d.get("energy_today", 0.0)
        return attrs

    # ── Actions ───────────────────────────────────────────────────────────────

    async def _call_climate(self, service: str, data: dict) -> None:
        data["entity_id"] = self._clima_eid
        try:
            await self.hass.services.async_call("climate", service, data)
        except Exception as ex:
            _LOGGER.error("[EM Clima] climate.%s failed: %s", service, ex)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._call_climate("set_hvac_mode", {"hvac_mode": hvac_mode})
        # Update coordinator state without calling _sw (which would overwrite the mode)
        coord = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        if coord:
            mode_str = hvac_mode.value if hasattr(hvac_mode, "value") else str(hvac_mode)
            if hvac_mode != HVACMode.OFF:
                # Save new mode to storage so next turn_on uses it
                coord.storage.set("last_clima_mode", mode_str)
                coord._ac_state = True
            else:
                coord._ac_state = False
            coord.async_set_updated_data(coord._build())

    async def async_set_temperature(self, **kwargs) -> None:
        data = {}
        if ATTR_TEMPERATURE in kwargs:
            data["temperature"] = kwargs[ATTR_TEMPERATURE]
        if "hvac_mode" in kwargs:
            data["hvac_mode"] = kwargs["hvac_mode"]
        await self._call_climate("set_temperature", data)

    async def async_turn_on(self) -> None:
        # Restore last mode or default to heat
        st = self._real_state()
        last = st.attributes.get("hvac_mode", "heat") if st else "heat"
        mode = last if last != "off" else "heat"
        await self.async_set_hvac_mode(mode)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
