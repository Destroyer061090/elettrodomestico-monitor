"""Test per custom_components/elettrodomestico_monitor/hub.py.

async_repair_push_targets() è nuova in questa passata (segnalazione utente
v7.0.3): prima, un push_target che puntava a un'entità notify non più
esistente (tipicamente l'app companion iOS/Android ri-registrata con un
nuovo entity_id dopo una reinstallazione) veniva perso in silenzio da
notify_helper.async_send_push — l'utente non riceveva più notifiche push e
non aveva alcun segnale che qualcosa non andasse.

CORREZIONE (segnalazione utente, 2026-10-21): la prima versione (v7.0.3)
tentava anche di auto-migrare un target mancante verso un'entità
"notify.mobile_app_<nome>" — ma quel nome è il SERVIZIO legacy (nessuno
stato associato), non un'entità: controllarlo con hass.states.get() non
funzionava mai nella pratica su una Home Assistant reale. Rimossa del
tutto: ora un target mancante produce sempre e solo una Repair issue, mai
un tentativo di indovinare il nome giusto. Questi test coprono i 3 casi
attuali: entità valida (nessuna modifica), entità mancante (issue di
riparazione), e l'issue che si auto-risolve quando l'utente corregge il
destinatario a mano.
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


async def test_missing_target_is_never_auto_migrated_to_the_legacy_service_name(hass, caplog):
    """CORREZIONE (segnalazione utente, 2026-10-21): notify.mobile_app_<nome>
    è il SERVIZIO legacy, non un'entità — anche se per qualche motivo
    un'entità con quel nome esatto esistesse, non deve mai essere scritta
    in CONF_PUSH_TARGETS come "migrazione automatica" (comportamento della
    v7.0.3, rimosso). L'entry non va mai modificata: solo la Repair issue."""
    caplog.set_level(logging.INFO)
    # notify.iphone_di_alessandro NON viene mai impostata: simula l'entità sparita.
    hass.states.async_set("notify.mobile_app_iphone_di_alessandro", "unknown")
    entry = _make_hub_entry(hass, ["notify.iphone_di_alessandro"])

    await async_repair_push_targets(hass, entry)

    assert entry.data[CONF_PUSH_TARGETS] == ["notify.iphone_di_alessandro"]  # invariato
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, _issue_id(entry)) is not None


async def test_missing_target_without_fallback_creates_repair_issue(hass, caplog):
    """Il target configurato non esiste come entità: l'entry NON viene
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
