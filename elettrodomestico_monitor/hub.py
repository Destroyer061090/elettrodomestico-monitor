# ============================================================
# FILE:    hub.py
# VERSION: 5.8.6
# DESC:    Hub config reader — global settings (costs, notify, schedule)
# CHANGED: 2026-06-11
# ============================================================
"""Hub helper — reads global configuration and resolves costs live."""
from __future__ import annotations
from typing import Any
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from .const import (
    DOMAIN, ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
    CONF_COSTO_KWH,   CONF_COSTO_KWH_SENSOR,
    CONF_COSTO_ACQUA, CONF_COSTO_ACQUA_SENSOR,
    CONF_COSTO_GAS,   CONF_COSTO_GAS_SENSOR,
    CONF_VENDITA_KWH, CONF_VENDITA_KWH_SENSOR,
    CONF_NOTIFY_START_TIME, CONF_NOTIFY_END_TIME,
    CONF_PUSH_TARGETS, CONF_ALEXA_TARGETS, CONF_GOOGLE_TARGETS,
    CONF_WHATSAPP_ENTITY, CONF_AUTO_ON_TIME, CONF_AUTO_OFF_TIME,
    DEFAULT_COST, DEFAULT_NOTIFY_START, DEFAULT_NOTIFY_END, DEFAULT_SCHEDULE,
)
from .presets import COST_KEY_KWH, COST_KEY_ACQUA, COST_KEY_GAS, COST_KEY_VENDITA

_BAD = {STATE_UNAVAILABLE, STATE_UNKNOWN, None, "", "unknown", "unavailable"}

# Remember the last valid reading per cost sensor. When a price sensor briefly
# goes unavailable (e.g. a cloud energy-price sensor while internet is down),
# we keep the last good value instead of flipping to the fixed fallback. That
# flip changed costo_eur/fonte_costo on every energy sensor of every device and
# flooded the WebSocket ('4096 pending messages').
_LAST_GOOD_COST: dict[str, float] = {}


def _resolve(hass: HomeAssistant, hub_data: dict,
             fixed_key: str, sensor_key: str,
             default: float = 0.0) -> tuple[float, str]:
    """Resolve cost: sensor (if valid) > last good sensor value > fixed."""
    fixed = float(hub_data.get(fixed_key) or default)
    sid   = hub_data.get(sensor_key) or ""   # guard against None
    sid   = sid.strip()
    if sid:
        st = hass.states.get(sid)
        if st and st.state not in _BAD:
            try:
                val = float(st.state)
                _LAST_GOOD_COST[sid] = val
                return val, "sensore"
            except (ValueError, TypeError):
                pass
        # Sensor temporarily unavailable: reuse the last good value if we have
        # one, so the cost (and every dependent attribute) stays stable.
        if sid in _LAST_GOOD_COST:
            return _LAST_GOOD_COST[sid], "sensore"
        return fixed, "fisso (fallback)"
    return fixed, "fisso"


def get_hub_config(hass: HomeAssistant) -> dict[str, Any]:
    """Return fully resolved hub configuration."""
    hub_data: dict[str, Any] = {}
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
            hub_data = entry.data
            break

    costo_kwh,   src_kwh   = _resolve(hass, hub_data, CONF_COSTO_KWH,   CONF_COSTO_KWH_SENSOR)
    costo_acqua, src_acqua = _resolve(hass, hub_data, CONF_COSTO_ACQUA, CONF_COSTO_ACQUA_SENSOR)
    costo_gas,   src_gas   = _resolve(hass, hub_data, CONF_COSTO_GAS,   CONF_COSTO_GAS_SENSOR)
    vendita_kwh, src_vend  = _resolve(hass, hub_data, CONF_VENDITA_KWH, CONF_VENDITA_KWH_SENSOR)

    return {
        COST_KEY_KWH:     costo_kwh,
        COST_KEY_ACQUA:   costo_acqua,
        COST_KEY_GAS:     costo_gas,
        COST_KEY_VENDITA: vendita_kwh,
        f"{COST_KEY_KWH}_source":     src_kwh,
        f"{COST_KEY_ACQUA}_source":   src_acqua,
        f"{COST_KEY_GAS}_source":     src_gas,
        f"{COST_KEY_VENDITA}_source": src_vend,
        "notify_start_time": hub_data.get(CONF_NOTIFY_START_TIME, DEFAULT_NOTIFY_START),
        "notify_end_time":   hub_data.get(CONF_NOTIFY_END_TIME,   DEFAULT_NOTIFY_END),
        "push_targets":      hub_data.get(CONF_PUSH_TARGETS,  []) or [],
        "alexa_targets":     hub_data.get(CONF_ALEXA_TARGETS, []) or [],
        "google_targets":    hub_data.get(CONF_GOOGLE_TARGETS,[]) or [],
        "whatsapp_entity":   (hub_data.get(CONF_WHATSAPP_ENTITY) or "").strip(),
        "fv_enabled":     bool(hub_data.get("fv_enabled", False)),
        "fv_invert":      bool(hub_data.get("fv_invert", False)),
        "fv_grid_sensor": (hub_data.get("fv_grid_sensor") or "").strip(),
        "fv_threshold_w": float(hub_data.get("fv_threshold_w", 0.0) or 0.0),
        "auto_on_time":  hub_data.get(CONF_AUTO_ON_TIME,  DEFAULT_SCHEDULE) or DEFAULT_SCHEDULE,
        "auto_off_time": hub_data.get(CONF_AUTO_OFF_TIME, DEFAULT_SCHEDULE) or DEFAULT_SCHEDULE,
        "meteo_entity":  hub_data.get("meteo_entity", "") or "",
    }
