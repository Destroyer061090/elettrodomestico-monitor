"""Test per custom_components/elettrodomestico_monitor/config_flow.py.

Ogni possibile errore di configurazione dell'utente passa da qui. Due
categorie di bug coperte in questo file (trovate durante l'audit fase 2):

1. Lo step di irrigazione non verificava che `flow_sensor` (campo
   obbligatorio) corrispondesse a un'entità realmente esistente —
   incoerente con gli step vacuum/dispositivo, che quella verifica
   la fanno già.
2. Nessuno step verificava se un'entità di CONTROLLO (vacuum_entity,
   trigger_entity, dev_battery_sensor, dev_charge_switch) fosse già
   assegnata a un'altra config entry — solo lo slot numerico veniva
   controllato. Assegnare la stessa entità a due dispositivi diversi fa
   sì che due coordinator indipendenti reagiscano allo stesso evento
   (doppio conteggio cicli, doppie notifiche, comandi in conflitto).

Il sensore di potenza (`power_sensor`) è l'eccezione intenzionale: la sua
condivisione tra più dispositivi è una feature (vedi la logica
master/slave in coordinator.py) e NON deve mai generare un errore — da
qui il test di non-regressione dedicato.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import (
    CONF_APPLIANCE_NAME,
    CONF_DEV_BATTERY_SENSOR,
    CONF_DEV_CHARGE_SWITCH,
    CONF_FLOW_SENSOR,
    CONF_POWER_SENSOR,
    CONF_SLOT,
    CONF_TRIGGER_ENTITY,
    CONF_VACUUM_ENTITY,
    DOMAIN,
)
from custom_components.elettrodomestico_monitor.config_flow import (
    ElettrodomesticoConfigFlow,
    VacuumOptionsFlow,
)


def _make_flow(hass) -> ElettrodomesticoConfigFlow:
    flow = ElettrodomesticoConfigFlow()
    flow.hass = hass
    flow._appl = {}
    flow._preset_id = "elettrodomestico"
    flow._hub = {}
    flow._need_hub = False
    return flow


def _add_entry(hass, data: dict) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    return entry


# ── Validazione flow_sensor (irrigazione) ─────────────────────────────────────

async def test_irrigation_rejects_empty_flow_sensor(hass):
    """flow_sensor è obbligatorio: vuoto deve bloccare lo step, non
    passare silenziosamente con una entity_id vuota salvata."""
    flow = _make_flow(hass)
    result = await flow.async_step_irrigation({
        CONF_SLOT: 1, CONF_APPLIANCE_NAME: "Giardino",
        CONF_FLOW_SENSOR: "", "_num_zones": 1,
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_FLOW_SENSOR) == "entity_not_found"


async def test_irrigation_rejects_nonexistent_flow_sensor(hass):
    """Prima di questo fix, un'entity_id inesistente per flow_sensor
    veniva accettata senza controllo (a differenza di vacuum/dispositivo,
    che verificano sempre con hass.states.get())."""
    flow = _make_flow(hass)
    result = await flow.async_step_irrigation({
        CONF_SLOT: 1, CONF_APPLIANCE_NAME: "Giardino",
        CONF_FLOW_SENSOR: "sensor.non_esiste", "_num_zones": 1,
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_FLOW_SENSOR) == "entity_not_found"


async def test_irrigation_accepts_valid_flow_sensor(hass):
    """Un flow_sensor valido deve proseguire normalmente allo step
    successivo (nessuna regressione introdotta dal fix)."""
    hass.states.async_set("sensor.flusso_reale", "12.5")
    flow = _make_flow(hass)
    result = await flow.async_step_irrigation({
        CONF_SLOT: 1, CONF_APPLIANCE_NAME: "Giardino",
        CONF_FLOW_SENSOR: "sensor.flusso_reale", "_num_zones": 1,
    })
    assert result["type"] != "form" or not result["errors"]
    assert flow._appl.get(CONF_FLOW_SENSOR) == "sensor.flusso_reale"


# ── Controllo duplicati: entità di controllo già in uso ──────────────────────

async def test_vacuum_entity_already_used_is_rejected(hass):
    """Due config entry vacuum che puntano allo stesso vacuum.* farebbero
    reagire due coordinator indipendenti allo stesso evento fisico
    (doppio conteggio cicli, doppie notifiche)."""
    hass.states.async_set("vacuum.robot", "docked")
    _add_entry(hass, {CONF_TRIGGER_ENTITY: "vacuum.robot", CONF_SLOT: 1})

    flow = _make_flow(hass)
    result = await flow.async_step_vacuum({
        CONF_SLOT: 2, CONF_APPLIANCE_NAME: "Robot Duplicato",
        CONF_VACUUM_ENTITY: "vacuum.robot",
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_VACUUM_ENTITY) == "entity_in_use"


async def test_vacuum_entity_not_used_elsewhere_is_accepted(hass):
    """Caso base: nessun conflitto, il flusso deve proseguire."""
    hass.states.async_set("vacuum.robot2", "docked")
    flow = _make_flow(hass)
    result = await flow.async_step_vacuum({
        CONF_SLOT: 2, CONF_APPLIANCE_NAME: "Robot 2",
        CONF_VACUUM_ENTITY: "vacuum.robot2",
    })
    assert result["type"] != "form" or not result["errors"]


async def test_vacuum_options_flow_editing_self_is_not_a_false_positive(hass):
    """Aprire le opzioni di UNA entry e risalvare lo stesso vacuum_entity
    non deve auto-segnalarsi come duplicato — l'entry corrente va esclusa
    dal controllo."""
    hass.states.async_set("vacuum.robot3", "docked")
    entry = _add_entry(hass, {
        CONF_TRIGGER_ENTITY: "vacuum.robot3", CONF_SLOT: 3,
        CONF_APPLIANCE_NAME: "Robot 3",
    })
    options = VacuumOptionsFlow(entry)
    options.hass = hass
    result = await options.async_step_init({
        CONF_APPLIANCE_NAME: "Robot 3", CONF_VACUUM_ENTITY: "vacuum.robot3",
    })
    assert result["type"] != "form" or not result["errors"]


async def test_vacuum_options_flow_stealing_another_entrys_vacuum_is_rejected(hass):
    """Dalle opzioni di UNA entry, provare ad assegnarle il vacuum_entity
    di un'ALTRA entry esistente deve essere bloccato."""
    hass.states.async_set("vacuum.robotA", "docked")
    _add_entry(hass, {CONF_TRIGGER_ENTITY: "vacuum.robotA", CONF_SLOT: 1})
    entry_b = _add_entry(hass, {CONF_TRIGGER_ENTITY: "vacuum.robotB", CONF_SLOT: 2})

    options = VacuumOptionsFlow(entry_b)
    options.hass = hass
    result = await options.async_step_init({
        CONF_APPLIANCE_NAME: "Robot B", CONF_VACUUM_ENTITY: "vacuum.robotA",
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_VACUUM_ENTITY) == "entity_in_use"


async def test_trigger_entity_already_used_is_rejected(hass):
    """Stesso principio ma per il preset climate/generico: due appliance
    che condividono lo stesso trigger_entity (es. climate.soggiorno)."""
    hass.states.async_set("climate.soggiorno", "heat")
    _add_entry(hass, {CONF_TRIGGER_ENTITY: "climate.soggiorno", CONF_SLOT: 1})

    flow = _make_flow(hass)
    result = await flow.async_step_appliance({
        CONF_SLOT: 2, CONF_APPLIANCE_NAME: "Clima Duplicato",
        CONF_TRIGGER_ENTITY: "climate.soggiorno", CONF_POWER_SENSOR: "",
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_TRIGGER_ENTITY) == "entity_in_use"


async def test_power_sensor_sharing_is_not_flagged_as_duplicate(hass):
    """NON-REGRESSIONE, il test più importante di questo file: la
    condivisione di un sensore di potenza fisico tra due dispositivi è
    una feature intenzionale (logica master/slave in coordinator.py) e
    NON deve mai generare un errore di 'entità già in uso'."""
    hass.states.async_set("sensor.potenza_condivisa", "500")
    _add_entry(hass, {CONF_POWER_SENSOR: "sensor.potenza_condivisa", CONF_SLOT: 1})

    flow = _make_flow(hass)
    result = await flow.async_step_appliance({
        CONF_SLOT: 2, CONF_APPLIANCE_NAME: "Altro Dispositivo Stesso Sensore",
        CONF_POWER_SENSOR: "sensor.potenza_condivisa", CONF_TRIGGER_ENTITY: "",
    })
    assert result["type"] != "form" or not result["errors"]


async def test_device_battery_sensor_already_used_is_rejected(hass):
    """Preset 'dispositivo': due battery-manager sullo stesso sensore di
    batteria creerebbero due logiche di ricarica indipendenti sullo
    stesso dispositivo fisico."""
    hass.states.async_set("sensor.batteria_telefono", "80")
    _add_entry(hass, {CONF_DEV_BATTERY_SENSOR: "sensor.batteria_telefono", CONF_SLOT: 1})

    flow = _make_flow(hass)
    result = await flow.async_step_device({
        CONF_SLOT: 2, CONF_APPLIANCE_NAME: "Altro Telefono",
        CONF_DEV_BATTERY_SENSOR: "sensor.batteria_telefono", CONF_DEV_CHARGE_SWITCH: "",
    })
    assert result["type"] == "form"
    assert result["errors"].get(CONF_DEV_BATTERY_SENSOR) == "entity_in_use"
