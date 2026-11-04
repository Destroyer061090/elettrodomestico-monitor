# ============================================================
# FILE:    entity_call.py
# VERSION: 7.0.7
# DESC:    Shared helper — call a service against an external entity only
#          if it's actually available, with a clear EM-tagged log instead
#          of HA's generic unreferenced warning.
# CHANGED: 2026-10-21
# ============================================================
"""Centralized availability-gated service call.

FIX (segnalazione utente, 2026-10-21): EM comanda entità esterne
configurate dall'utente (switch, climate, vacuum, ...) che possono essere
permanentemente o temporaneamente offline (es. uno smart plug Zigbee/WiFi
scollegato). Prima di questo fix, solo vacuum.py._call_vacuum e il ramo
vacuum di coordinator.py._sw() controllavano la disponibilità prima di
comandare l'entità reale (segnalazione utente v7.0.3) — ogni altro punto
(switch principale, clima, dispositivi a batteria, zone di irrigazione)
chiamava il servizio incondizionatamente, lasciando che Home Assistant
scrivesse solo un WARNING generico e senza alcun riferimento a EM:

    Referenced entities switch.100118d6db_1 are missing or not currently
    available

rendendo impossibile capire, leggendo il solo log, quale device EM lo
avesse causato. Centralizzato qui lo stesso controllo già validato per il
vacuum, cosi' ogni chiamante eredita lo stesso comportamento.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = ("unavailable", "unknown")


async def async_call_if_available(
    hass: HomeAssistant,
    domain: str,
    service: str,
    entity_id: str,
    data: dict[str, Any] | None = None,
    *,
    log_id: str,
) -> bool:
    """Call `domain.service` against `entity_id`, but only if that entity
    currently exists and isn't unavailable/unknown.

    Returns True if the call was actually attempted — not that it
    necessarily succeeded: a failure from the external entity is logged,
    never raised, so a misbehaving device can't crash EM's own logic.
    `log_id` is a ready-made tag (es. "EM x3", "IRR irr_test") so each
    caller keeps its own established log prefix convention.
    """
    if not entity_id:
        return False
    st = hass.states.get(entity_id)
    if st is None or st.state in _UNAVAILABLE_STATES:
        _LOGGER.info("[%s] %s.%s ignorato: %s non disponibile",
                     log_id, domain, service, entity_id)
        return False
    try:
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id, **(data or {})})
        return True
    except Exception as ex:  # noqa: BLE001 - un'entità esterna non deve mai far cadere EM
        _LOGGER.warning("[%s] %s.%s(%s) failed: %s",
                         log_id, domain, service, entity_id, ex)
        return False
