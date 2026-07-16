# ============================================================
# FILE:    button.py
# VERSION: 5.7.22
# DESC:    Button platform — reset counters, set maintenance
# CHANGED: 2026-06-11
# ============================================================
"""Button platform for Elettrodomestico Monitor.

Buttons per device:
  button.manutenzione_elettrodomestici_x1   — registra data manutenzione
  button.reset_contatori_elettrodomestici_x1 — azzera tutti i contatori
"""
from __future__ import annotations
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN, CONF_APPLIANCE_NAME, CONF_INSTANCE_ID, CONF_SLOT,
    SFX_BTN_MAINT, SFX_BTN_RESET,
)
from .coordinator import ElettrodomesticoCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    from .const import ENTRY_TYPE_HUB, CONF_ENTRY_TYPE
    et = entry.data.get(CONF_ENTRY_TYPE) or entry.data.get("entry_type", "")
    if et in (ENTRY_TYPE_HUB, "hub"):
        # Hub gets global action buttons (reset-all, export, import-info).
        async_add_entities([
            _HubResetAllButton(hass, entry),
            _HubExportButton(hass, entry),
            _HubImportButton(hass, entry),
        ])
        return

    coord = hass.data[DOMAIN].get(entry.entry_id)
    if not coord:
        _LOGGER.warning("[EM] button setup: coord not found for entry %s", entry.entry_id)
        return
    name = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    iid  = entry.data.get(CONF_INSTANCE_ID, slot)
    is_irr = et in ("irrigation",)

    async_add_entities([
        _MaintenanceButton(coord, entry, name, slot, iid, is_irr),
        _ResetButton(coord, entry, name, slot, iid, is_irr),
    ])


def _device(entry, name, iid):
    """Build DeviceInfo — iid must be passed explicitly (not from outer scope)."""
    return DeviceInfo(
        identifiers={(DOMAIN, iid)},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Elettrodomestici",
        sw_version="5.0.1",
    )


def _device_irr(entry, name, iid):
    """DeviceInfo for irrigation entries (matches irrigation device identity)."""
    return DeviceInfo(
        identifiers={(DOMAIN, iid)},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Irrigazione",
    )


class _MaintenanceButton(ButtonEntity):
    """Registra data/ora dell'ultima manutenzione."""

    def __init__(self, coord, entry, name, slot, iid, is_irr=False):
        self._coord = coord
        self._attr_unique_id       = f"{DOMAIN}_{iid}_{SFX_BTN_MAINT}_x{slot}"
        self.entity_id             = f"button.{SFX_BTN_MAINT}_x{slot}"
        self._attr_name            = f"Manutenzione {name}"
        self._attr_icon            = "mdi:wrench-clock"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _device_irr(entry, name, iid) if is_irr else _device(entry, name, iid)

    async def async_press(self) -> None:
        _LOGGER.info("Manutenzione registrata per %s", self._coord.instance_id)
        await self._coord.async_set_maintenance()


class _ResetButton(ButtonEntity):
    """Azzera tutti i contatori statistici."""

    def __init__(self, coord, entry, name, slot, iid, is_irr=False):
        self._coord = coord
        self._attr_unique_id       = f"{DOMAIN}_{iid}_{SFX_BTN_RESET}_x{slot}"
        self.entity_id             = f"button.{SFX_BTN_RESET}_x{slot}"
        self._attr_name            = f"Reset Contatori {name}"
        self._attr_icon            = "mdi:restore"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _device_irr(entry, name, iid) if is_irr else _device(entry, name, iid)

    async def async_press(self) -> None:
        _LOGGER.info("Reset contatori per %s", self._coord.instance_id)
        await self._coord.async_reset_all()


# ── Hub-level global action buttons ──────────────────────────────────────────
def _hub_device_info():
    from homeassistant.helpers.entity import DeviceInfo
    return DeviceInfo(
        identifiers={(DOMAIN, "hub")},
        name="Elettrodomestico Monitor Hub",
        manufacturer="Elettrodomestico Monitor",
        model="Hub Globale",
    )


class _HubResetAllButton(ButtonEntity):
    """Azzera i contatori di TUTTI i dispositivi (hub escluso)."""
    def __init__(self, hass, entry):
        self._hass = hass
        self._attr_unique_id       = f"{DOMAIN}_hub_reset_all"
        self.entity_id             = "button.reset_tutti_statistiche_hub"
        self._attr_name            = "Reset Tutte le Statistiche"
        self._attr_icon            = "mdi:restore-alert"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _hub_device_info()

    async def async_press(self) -> None:
        _LOGGER.info("[EM Hub] Reset di tutti i dispositivi richiesto dal pulsante")
        await self._hass.services.async_call(DOMAIN, "reset_all_sensors", {})


class _HubExportButton(ButtonEntity):
    """Esporta la configurazione completa (hub + tutti i dispositivi)."""
    def __init__(self, hass, entry):
        self._hass = hass
        self._attr_unique_id       = f"{DOMAIN}_hub_export"
        self.entity_id             = "button.esporta_configurazione_hub"
        self._attr_name            = "Esporta Configurazione"
        self._attr_icon            = "mdi:export"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _hub_device_info()

    async def async_press(self) -> None:
        _LOGGER.info("[EM Hub] Export configurazione richiesto dal pulsante")
        await self._hass.services.async_call(DOMAIN, "export_config", {})


class _HubImportButton(ButtonEntity):
    """Importa la configurazione da /config/www/em_export.json."""
    def __init__(self, hass, entry):
        self._hass = hass
        self._attr_unique_id       = f"{DOMAIN}_hub_import"
        self.entity_id             = "button.importa_configurazione_hub"
        self._attr_name            = "Importa Configurazione"
        self._attr_icon            = "mdi:import"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _hub_device_info()

    async def async_press(self) -> None:
        _LOGGER.info("[EM Hub] Import configurazione richiesto dal pulsante")
        await self._hass.services.async_call(DOMAIN, "import_config", {})
