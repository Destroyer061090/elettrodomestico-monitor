# ============================================================
# FILE:    text.py
# VERSION: 5.4.0
# DESC:    Text platform — device name entities
# CHANGED: 2026-06-11
# ============================================================
"""Text platform for Elettrodomestico Monitor v6.

Creates 2 text entities per device (modifiable at runtime from HA dashboard):
  text.nome_elettrodomestico_x1    ← display name (used in notifications)
  text.messaggio_elettrodomestico_x1 ← notification message
"""
from __future__ import annotations
import logging
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    CONF_CUSTOM_MESSAGE, SFX_TXT_NOME, SFX_TXT_MSG,
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
            await _async_setup_irrigation_text(hass, entry, coord, async_add_entities)
            return
    except (ImportError, KeyError):
        pass
    try:
        from .const import ENTRY_TYPE_DEVICE
        if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or
                entry.data.get("entry_type") == "device"):
            name = entry.data.get(CONF_APPLIANCE_NAME, "Dispositivo")
            slot = str(entry.data.get(CONF_SLOT, "1"))
            iid  = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
            async_add_entities([
                _TextEntity(entry, name, slot, iid, sfx="nome_dispositivo",
                            label=f"Nome {name}", icon="mdi:label-outline",
                            conf_key=CONF_APPLIANCE_NAME, default=name, max_len=50),
            ])
            return
    except (ImportError, KeyError):
        pass

    name = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    iid  = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))

    async_add_entities([
        _TextEntity(
            entry, name, slot, iid,
            sfx      = SFX_TXT_NOME,
            label    = f"Nome {name}",
            icon     = "mdi:label-outline",
            conf_key = CONF_APPLIANCE_NAME,
            default  = name,
            max_len  = 50,
        ),
        _TextEntity(
            entry, name, slot, iid,
            sfx      = SFX_TXT_MSG,
            label    = f"Messaggio Notifica {name}",
            icon     = "mdi:message-text-outline",
            conf_key = CONF_CUSTOM_MESSAGE,
            default  = entry.data.get(CONF_CUSTOM_MESSAGE, ""),
            max_len  = 255,
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


class _TextEntity(TextEntity, RestoreEntity):
    """A text entity that persists its value across restarts."""

    def __init__(self, entry, name, slot, iid, *, sfx, label, icon,
                 conf_key, default, max_len=255):
        self._entry    = entry
        self._conf_key = conf_key
        self._default  = default
        self._current: str = default

        self._attr_unique_id   = f"{DOMAIN}_{iid}_{sfx}_x{slot}"
        self.entity_id         = f"text.{sfx}_x{slot}"
        self._attr_name        = label
        self._attr_icon        = icon
        self._attr_native_max  = max_len
        self._attr_native_min  = 0
        self._attr_pattern     = None
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state not in (None, "", "unknown", "unavailable"):
            self._current = last.state
            return
        self._current = str(self._entry.data.get(self._conf_key, self._default))

    @property
    def native_value(self) -> str:
        return self._current

    async def async_set_value(self, value: str) -> None:
        self._current = value
        self.async_write_ha_state()


async def _async_setup_irrigation_text(
    hass, entry, coord, async_add_entities
) -> None:
    """Create text entity for irrigation device name (used by JS card)."""
    from homeassistant.components.text import TextEntity
    from homeassistant.helpers.entity import DeviceInfo

    name  = entry.data.get("appliance_name", "Irrigazione")
    slot  = str(entry.data.get("slot", "1"))
    iid   = entry.data.get("instance_id", "irr")
    DOMAIN_LOCAL = "elettrodomestico_monitor"

    dev_info = DeviceInfo(
        identifiers={(DOMAIN_LOCAL, iid)},
        name=name, manufacturer="Elettrodomestico Monitor", model="Irrigazione",
    )

    class _IrrNameText(TextEntity):
        def __init__(self):
            self._val = name
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_nome_irr_x{slot}"
            self.entity_id         = f"text.nome_irrigazione_x{slot}"
            self._attr_name        = f"Nome {name}"
            self._attr_icon        = "mdi:rename"
            self._attr_device_info = dev_info
            self._attr_native_min  = 1
            self._attr_native_max  = 50
        @property
        def native_value(self): return self._val
        async def async_set_value(self, value: str) -> None:
            self._val = value
            self.async_write_ha_state()

    async_add_entities([_IrrNameText()])
