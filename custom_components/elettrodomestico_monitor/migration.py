# ============================================================
# FILE:    migration.py
# VERSION: 5.1.0
# DESC:    Migration — config entry version upgrades
# CHANGED: 2026-07-20 (v6.1.0: rimosso blocco duplicato/irraggiungibile dopo il
#          return della funzione — vedi CHANGELOG.md)
# ============================================================
"""
Migration helpers for Elettrodomestico Monitor.

Runs automatically at startup to:
1. Detect config entries that need schema updates (missing keys)
2. Log warnings for devices that might benefit from a preset change
3. Auto-fill missing keys with safe defaults (non-destructive)

Philosophy: NEVER lose data, NEVER force reconfiguration.
Changes are logged clearly so the user knows what happened.
"""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN, ENTRY_TYPE_HUB, ENTRY_TYPE_APPLIANCE, CONF_ENTRY_TYPE,
    CONF_PRESET, CONF_POWER_SENSOR, CONF_TRIGGER_ENTITY,
    CONF_VACUUM_ENTITY, CONF_BATTERY_SENSOR,
    CONF_WORK_THRESHOLD_W, CONF_TRIGGER_DELAY_M, CONF_START_DELAY_S,
    CONF_NOTIFY_PUSH, CONF_NOTIFY_ALEXA, CONF_NOTIFY_GOOGLE, CONF_NOTIFY_WHATSAPP,
    CONF_SCHEDULE_OVERRIDE, CONF_AUTO_ON_LOCAL, CONF_AUTO_OFF_LOCAL,
    CONF_CUSTOM_MESSAGE, CONF_APPLIANCE_NAME, CONF_SLOT, CONF_DEVICE_ICON,
    CONF_SOURCE_UNIT, CONF_TOTAL_UNIT, CONF_SWITCH_ENTITY,
    DEFAULT_THRESHOLD_W, DEFAULT_TRIGGER_DELAY_M, DEFAULT_START_DELAY_S,
    DEFAULT_SCHEDULE,
)
from .presets import get_preset, PRESET_VACUUM, PRESET_CLIMA

_LOGGER = logging.getLogger(__name__)

# Safe imports for fields added in newer versions
try:
    from .const import CONF_IMAGE_ON, CONF_IMAGE_OFF
except ImportError:
    CONF_IMAGE_ON  = "image_on"
    CONF_IMAGE_OFF = "image_off"

try:
    from .const import CONF_POWER_SENSOR_2
except ImportError:
    CONF_POWER_SENSOR_2 = "power_sensor_2"

try:
    from .const import CONF_POWER_SHARE
except ImportError:
    CONF_POWER_SHARE = "power_share"

# Keys with their default values — used to fill missing keys in old entries
_APPLIANCE_DEFAULTS = {
    CONF_PRESET:            "elettrodomestico",
    CONF_DEVICE_ICON:       "mdi:washing-machine",
    CONF_POWER_SENSOR:      "",
    CONF_SWITCH_ENTITY:     "",
    CONF_TRIGGER_ENTITY:    "",
    CONF_VACUUM_ENTITY:     "",
    CONF_BATTERY_SENSOR:    "",
    CONF_SOURCE_UNIT:       "W",
    CONF_TOTAL_UNIT:        "kWh",
    CONF_WORK_THRESHOLD_W:  DEFAULT_THRESHOLD_W,
    CONF_TRIGGER_DELAY_M:   DEFAULT_TRIGGER_DELAY_M,
    CONF_START_DELAY_S:     DEFAULT_START_DELAY_S,
    CONF_CUSTOM_MESSAGE:    "",
    CONF_NOTIFY_PUSH:       False,
    CONF_NOTIFY_ALEXA:      False,
    CONF_NOTIFY_GOOGLE:     False,
    CONF_NOTIFY_WHATSAPP:   False,
    CONF_SCHEDULE_OVERRIDE: False,
    CONF_AUTO_ON_LOCAL:     DEFAULT_SCHEDULE,
    CONF_AUTO_OFF_LOCAL:    DEFAULT_SCHEDULE,
    CONF_IMAGE_ON:          "",
    CONF_IMAGE_OFF:         "",
    CONF_POWER_SENSOR_2:    "",
    CONF_POWER_SHARE:       1.0,
}


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """
    Called at startup for every config entry.
    Returns True = entry is OK (possibly updated), False = entry is broken.
    Non-destructive: only adds missing keys, never removes or changes existing ones.
    """
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        return True

    try:
        data    = dict(entry.data)
        changed = False
        name    = data.get(CONF_APPLIANCE_NAME, entry.title)
        slot    = data.get(CONF_SLOT, "?")
        preset  = data.get(CONF_PRESET, "elettrodomestico")

        # ── 1. Fill missing keys with defaults ─────────────────────────────
        for key, default in _APPLIANCE_DEFAULTS.items():
            if key not in data:
                data[key] = default
                changed = True
                _LOGGER.info(
                    "[EM Migration] '%s' (x%s): added missing key '%s' = %r",
                    name, slot, key, default
                )

        # ── 2. Detect vacuum misconfiguration ──────────────────────────────
        trigger = (data.get(CONF_TRIGGER_ENTITY) or "").strip()
        if trigger.startswith("vacuum.") and preset != PRESET_VACUUM:
            _LOGGER.warning(
                "[EM Migration] '%s' (x%s): trigger entity '%s' is a vacuum "
                "but preset is '%s'. Consider reconfiguring as 'vacuum' preset "
                "for correct start/stop/return_to_base behaviour.",
                name, slot, trigger, preset
            )

        # ── 3. Detect clima misconfiguration ────────────────────────────────
        if trigger.startswith("climate.") and preset != PRESET_CLIMA:
            _LOGGER.warning(
                "[EM Migration] '%s' (x%s): trigger entity '%s' is a climate "
                "but preset is '%s'. Consider reconfiguring as 'clima' preset "
                "for correct hvac_mode control.",
                name, slot, trigger, preset
            )

        # ── 4. Vacuum: auto-populate vacuum_entity from trigger_entity ─────
        if preset == PRESET_VACUUM and not data.get(CONF_VACUUM_ENTITY):
            if trigger.startswith("vacuum."):
                data[CONF_VACUUM_ENTITY] = trigger
                changed = True
                _LOGGER.info(
                    "[EM Migration] '%s' (x%s): vacuum_entity auto-set to '%s'",
                    name, slot, trigger
                )

        # ── 5. Apply changes if needed ──────────────────────────────────────
        if changed:
            hass.config_entries.async_update_entry(entry, data=data)
            _LOGGER.info(
                "[EM Migration] '%s' (x%s): config updated (non-destructive)",
                name, slot
            )

        return True

    except Exception as ex:
        _LOGGER.error("[EM Migration] Unexpected error for '%s': %s", entry.title, ex)
        return True  # Never block setup due to migration error

