# ============================================================
# FILE:    binary_sensor.py
# VERSION: 5.0.4
# DESC:    Binary sensor platform — AC state sensor for appliances
# CHANGED: 2026-06-11
# ============================================================
"""Binary sensor platform for Elettrodomestico Monitor."""
from __future__ import annotations
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, CONF_APPLIANCE_NAME, CONF_INSTANCE_ID, CONF_SLOT, SFX_AC
from .coordinator import ElettrodomesticoCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: ElettrodomesticoCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    async_add_entities([_AC(coord, entry, name, slot)])


class _AC(CoordinatorEntity, BinarySensorEntity):
    """binary_sensor.ac_elettrodomestici_xN — ON when appliance is working."""

    def __init__(self, coord, entry, name, slot):
        super().__init__(coord)
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id    = f"{DOMAIN}_{iid}_{SFX_AC}_x{slot}"
        self.entity_id          = f"binary_sensor.{SFX_AC}_x{slot}"
        self._attr_name         = f"AC {name}"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon         = "mdi:state-machine"
        self._attr_device_info  = DeviceInfo(
            identifiers={(DOMAIN, iid)},
            name=name,
            manufacturer="Elettrodomestico Monitor",
            model="Centro Controllo Elettrodomestici",
            sw_version="4.6",
        )

    @property
    def is_on(self) -> bool:
        return (self.coordinator.data or {}).get("ac_state", False)

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "potenza_w":    d.get("power_w",      0.0),
            "ciclo_attivo": d.get("cycle_active", False),
            "ultimo_ciclo": d.get("terminato",    ""),
        }
