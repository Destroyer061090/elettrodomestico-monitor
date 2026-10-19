"""Test per custom_components/elettrodomestico_monitor/hub.py.

async_repair_push_targets() è nuova in questa passata (segnalazione utente
v7.0.3): prima, un push_target che puntava a un'entità notify non più
esistente (tipicamente l'app companion iOS/Android ri-registrata con un
nuovo entity_id dopo una reinstallazione) veniva perso in silenzio da
notify_helper.async_send_push — l'utente non riceveva più notifiche push e
non aveva alcun segnale che qualcosa non andasse. Questi test coprono i
4 casi richiesti: entità valida (nessuna modifica), entità mancante con
fallback automatico a notify.mobile_app_<nome>, entità mancante senza
alcuna alternativa (issue di riparazione), e migrazione automatica
dell'entry.
"""
from __future__ import annotations

import logging

from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.helpers import issue_registry as ir

from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    CONF_PUSH_TARGETS,
    DOMAIN,
    ENTRY_TYPE_HUB,
)
from custom_components.elettrodomestico_monitor.hub import (
    async_repair_push_targets,
)


def _make_hub_entry(hass, push_targets, instance_id="hub_test") -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_HUB,
        "instance_id": instance_id,
        CONF_PUSH_TARGETS: push_targets,
    }, title="Hub")
    entry.add_to_hass(hass)
    return entry


def _issue_id(entry: MockConfigEntry) -> str:
    return f"missing_push_targets_{entry.entry_id}"


async def test_existing_target_is_left_untouched(hass):
    """Il caso comune: l'entità esiste ancora → nessuna modifica all'entry,
    nessuna issue di riparazione creata."""
    hass.states.async_set("notify.iphone_di_alessandro", "unknown")
    entry = _make_hub_entry(hass, ["notify.iphone_di_alessandro"])

    await async_repair_push_targets(hass, entry)

    assert entry.data[CONF_PUSH_TARGETS] == ["notify.iphone_di_alessandro"]
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is None


async def test_missing_target_is_migrated_to_mobile_app_entity(hass, caplog):
    """FIX (segnalazione utente v7.0.3): l'entità originale non esiste più,
    ma notify.mobile_app_<nome> sì (app companion ri-registrata) — l'entry
    deve essere aggiornata automaticamente al nuovo nome, con un log INFO,
    e nessuna issue deve comparire (il problema si è auto-risolto)."""
    caplog.set_level(logging.INFO)
    # notify.iphone_di_alessandro NON viene mai impostata: simula l'entità sparita.
    hass.states.async_set("notify.mobile_app_iphone_di_alessandro", "unknown")
    entry = _make_hub_entry(hass, ["notify.iphone_di_alessandro"])

    await async_repair_push_targets(hass, entry)

    assert entry.data[CONF_PUSH_TARGETS] == ["notify.mobile_app_iphone_di_alessandro"]
    assert "migrato automaticamente" in caplog.text
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is None


async def test_missing_target_without_fallback_creates_repair_issue(hass, caplog):
    """Nessuna entità né mobile_app_<nome> trovata: l'entry NON viene
    modificata (il valore configurato dall'utente non va perso in
    silenzio), compare un WARNING in log con prefisso [EM], e viene creata
    una issue di riparazione visibile in Impostazioni → Riparazioni."""
    entry = _make_hub_entry(hass, ["notify.destinatario_fantasma"])

    await async_repair_push_targets(hass, entry)

    assert entry.data[CONF_PUSH_TARGETS] == ["notify.destinatario_fantasma"]
    assert "[EM]" in caplog.text and "non trovato" in caplog.text
    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, _issue_id(entry))
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders["targets"] == "notify.destinatario_fantasma"


async def test_empty_push_targets_is_a_safe_noop(hass):
    """Nessun push_target configurato: non deve succedere nulla (né
    update_entry né issue), e soprattutto nessuna eccezione."""
    entry = _make_hub_entry(hass, [])

    await async_repair_push_targets(hass, entry)

    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is None


async def test_issue_is_cleared_once_target_becomes_valid_again(hass):
    """Un'issue creata in una esecuzione precedente deve sparire da sola
    quando, ad un'esecuzione successiva, il destinatario torna valido
    (es. l'utente lo ha corretto a mano dalle Opzioni)."""
    entry = _make_hub_entry(hass, ["notify.destinatario_fantasma"])
    await async_repair_push_targets(hass, entry)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is not None

    # L'utente corregge il destinatario dalle Opzioni.
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_PUSH_TARGETS: ["notify.destinatario_corretto"]})
    hass.states.async_set("notify.destinatario_corretto", "unknown")

    await async_repair_push_targets(hass, entry)

    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is None
