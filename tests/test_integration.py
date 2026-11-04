"""Test di integrazione end-to-end per Elettrodomestico Monitor.

A differenza degli altri file di test (che esercitano la logica interna
di UN modulo in isolamento, con stub leggeri), questo verifica il
"cablaggio" reale tra i moduli: che un setup completo di un config entry
Hub + un config entry Appliance produca davvero le entità attese in
Home Assistant, con gli attributi corretti — esattamente il percorso che
un utente reale attraversa installando l'integrazione.

**Nota di trasparenza**: a differenza di TUTTI gli altri test in questo
progetto, questo file non è stato eseguito con successo in un harness
leggero locale prima della consegna — il sandbox usato per gli altri
moduli stubava solo i pezzi di Home Assistant necessari per istanziare
le singole classi (coordinator, config_flow, ecc.), non l'intera
macchina di forwarding delle piattaforme
(`hass.config_entries.async_forward_entry_setups`, il component loader,
l'entity registry) che questo test esercita per davvero. Riprodurre
quella macchina in uno stub sarebbe equivalso a reimplementare gran
parte del core di Home Assistant. Questo test segue il pattern standard
raccomandato da pytest-homeassistant-custom-component, ma è, onestamente,
l'unico di questa sessione che va verificato per la prima volta in un
ambiente reale (`pytest tests/test_integration.py -v`) prima di fidarsene
quanto gli altri.
"""
from __future__ import annotations

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import (
    CONF_APPLIANCE_NAME,
    CONF_ENTRY_TYPE,
    CONF_INSTANCE_ID,
    CONF_POWER_SENSOR,
    CONF_PRESET,
    CONF_PUSH_TARGETS,
    CONF_SLOT,
    DOMAIN,
    ENTRY_TYPE_HUB,
    SFX_SW_SWITCH,
)


async def test_hub_and_appliance_setup_creates_expected_entities(hass, enable_custom_integrations):
    """Setup completo: Hub globale + un elettrodomestico standard con
    switch fisico e sensore di potenza. Verifica che:
    - il setup di entrambe le entry vada a buon fine (nessuna eccezione);
    - lo switch principale del dispositivo venga creato con l'entity_id
      atteso e risulti disponibile;
    - il coordinator del dispositivo sia effettivamente registrato in
      hass.data, punto di aggancio usato da tutte le piattaforme.
    """
    hub_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB},
        title="Hub Globale",
    )
    hub_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.lavatrice_potenza", "0")
    hass.states.async_set("switch.presa_lavatrice", "off")

    appliance_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_INSTANCE_ID: "lavatrice1",
            CONF_SLOT: "1",
            CONF_APPLIANCE_NAME: "Lavatrice",
            CONF_PRESET: "elettrodomestico",
            CONF_POWER_SENSOR: "sensor.lavatrice_potenza",
            "switch_entity": "switch.presa_lavatrice",
        },
        title="Lavatrice",
    )
    appliance_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(appliance_entry.entry_id)
    await hass.async_block_till_done()

    # Il coordinator deve essere registrato — è il punto da cui tutte le
    # piattaforme (sensor, switch, binary_sensor, ...) leggono i dati.
    # NOTA: registrato per entry.entry_id (un ULID generato da HA), non per
    # instance_id — bug del test corretto dopo la prima esecuzione reale
    # della CI (vedi CHANGELOG.md).
    assert appliance_entry.entry_id in hass.data[DOMAIN]

    # Lo switch principale deve esistere con l'entity_id atteso (costruito
    # da switch.py: f"switch.{SFX_SW_SWITCH}_x{slot}") ed essere disponibile.
    main_switch = hass.states.get(f"switch.{SFX_SW_SWITCH}_x1")
    assert main_switch is not None
    assert main_switch.state in ("on", "off")


async def test_appliance_without_control_entity_gets_no_main_switch(hass, enable_custom_integrations):
    """Un dispositivo di solo monitoraggio (nessuno switch_entity, nessun
    trigger) non deve ricevere un _MainSwitch — verifica end-to-end della
    logica di dispatch già coperta a livello unitario in test_switch.py."""
    hub_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}, title="Hub Globale")
    hub_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_entry.entry_id)
    await hass.async_block_till_done()

    hass.states.async_set("sensor.frigo_potenza", "80")

    appliance_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_INSTANCE_ID: "frigo1",
            CONF_SLOT: "2",
            CONF_APPLIANCE_NAME: "Frigo",
            CONF_PRESET: "elettrodomestico",
            CONF_POWER_SENSOR: "sensor.frigo_potenza",
        },
        title="Frigo",
    )
    appliance_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(appliance_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(f"switch.{SFX_SW_SWITCH}_x2") is None


# ── Riparazione push_targets: falso positivo al riavvio (v7.0.6) ─────────────
#
# FIX (segnalazione utente v7.0.6): async_repair_push_targets (hub.py)
# girava SINCRONA dentro async_setup_entry dell'Hub. mobile_app crea le
# proprie entità notify.* da config entry INDIPENDENTI, senza alcun
# ordinamento garantito rispetto all'Hub di EM — "notify" in
# after_dependencies (manifest.json) ordina solo il componente "notify",
# non le entità create da "mobile_app". Un push_target perfettamente
# valido risultava quindi "mancante" ad ogni riavvio di HA, con tanto di
# Repair issue creata e mai più ripulita.

async def test_push_repair_is_deferred_until_ha_finishes_starting(hass, enable_custom_integrations):
    """Simula il caso peggiore: l'Hub si avvia PRIMA che l'entità notify
    esista (mobile_app non ha ancora finito il proprio setup). Il
    controllo non deve scattare subito (altrimenti la segnalerebbe
    erroneamente mancante) — deve aspettare EVENT_HOMEASSISTANT_STARTED,
    a quel punto trova il target (apparso nel frattempo) e NON crea
    alcuna issue."""
    hass.set_state(CoreState.not_running)

    hub_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PUSH_TARGETS: ["notify.iphone_di_alessandro"]},
        title="Hub Globale",
    )
    hub_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue_id = f"missing_push_targets_{hub_entry.entry_id}"
    assert registry.async_get_issue(DOMAIN, issue_id) is None

    # mobile_app finisce di avviarsi: l'entità compare prima che HA segnali
    # EVENT_HOMEASSISTANT_STARTED.
    hass.states.async_set("notify.iphone_di_alessandro", "unknown")
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_push_repair_runs_immediately_when_ha_already_running(hass, enable_custom_integrations):
    """Non-regressione: a HA già avviato (es. un reload manuale dell'Hub
    dalle Opzioni), il controllo resta immediato come prima — non ha senso
    aspettare EVENT_HOMEASSISTANT_STARTED, che a quel punto non scatta più."""
    hass.set_state(CoreState.running)

    hub_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, CONF_PUSH_TARGETS: ["notify.destinatario_fantasma"]},
        title="Hub Globale",
    )
    hub_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_entry.entry_id)
    await hass.async_block_till_done()

    registry = ir.async_get(hass)
    issue_id = f"missing_push_targets_{hub_entry.entry_id}"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None
