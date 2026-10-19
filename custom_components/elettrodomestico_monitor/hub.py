# ============================================================
# FILE:    hub.py
# VERSION: 5.9.0
# DESC:    Hub config reader — global settings (costs, notify, schedule)
# CHANGED: 2026-06-11
# ============================================================
"""Hub helper — reads global configuration and resolves costs live."""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
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

_LOGGER = logging.getLogger(__name__)
_ISSUE_MISSING_PUSH = "missing_push_targets"

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


async def async_repair_push_targets(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Auto-heal push_targets that reference a notify entity which no
    longer exists (e.g. the iOS/Android companion app re-registered under a
    new entity_id after a reinstall) — migrate to notify.mobile_app_<name>
    if that entity now exists, otherwise raise a Repair issue so the user
    knows a target is silently undeliverable instead of discovering it only
    when a notification never arrives.

    FIX (segnalazione utente v7.0.3): un push_target non più valido veniva
    perso in silenzio da notify_helper.async_send_push (vedi quel modulo)
    senza che l'utente venisse mai avvisato che quel destinatario non
    arriva più a destinazione. Chiamata una volta ad ogni avvio/reload
    dell'Hub — economica e idempotente, non va ripetuta ad ogni poll.
    """
    targets = [str(t).strip() for t in (entry.data.get(CONF_PUSH_TARGETS) or []) if str(t).strip()]
    issue_id = f"{_ISSUE_MISSING_PUSH}_{entry.entry_id}"

    if not targets:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return

    fixed: list[str] = []
    missing: list[str] = []
    changed = False

    for t in targets:
        if hass.states.get(t) is not None:
            fixed.append(t)
            continue
        svc_name = t.split(".", 1)[1] if "." in t else t
        candidate = f"notify.mobile_app_{svc_name}"
        if candidate != t and hass.states.get(candidate) is not None:
            fixed.append(candidate)
            changed = True
            _LOGGER.info(
                "[EM] Hub: push_target '%s' non trovato — migrato automaticamente a '%s'",
                t, candidate)
        else:
            fixed.append(t)  # keep the stale value — never silently drop user config
            missing.append(t)

    if changed:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_PUSH_TARGETS: fixed})

    if missing:
        _LOGGER.warning(
            "[EM] Hub: push_target non trovato e senza alternativa automatica: %s",
            ", ".join(missing))
        ir.async_create_issue(
            hass, DOMAIN, issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=_ISSUE_MISSING_PUSH,
            translation_placeholders={"targets": ", ".join(missing)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
