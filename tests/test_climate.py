"""Test per custom_components/elettrodomestico_monitor/climate.py.

FIX (segnalazione utente, 2026-10-21): _call_climate — il punto unico da
cui passano TUTTI i comandi verso il climate reale (set_hvac_mode,
set_temperature, ecc.) — non controllava la disponibilità dell'entità
prima di inoltrare il comando. Stesso identico problema già corretto per
il vacuum (segnalazione utente v7.0.3): con un climate unavailable (es. un
Daikin WiFi scollegato), HA scriveva solo un warning generico senza alcun
riferimento a EM.
"""
from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    CONF_INSTANCE_ID,
    CONF_PRESET,
    CONF_SLOT,
    CONF_TRIGGER_ENTITY,
    DOMAIN,
    ENTRY_TYPE_APPLIANCE,
)
from custom_components.elettrodomestico_monitor.coordinator import (
    ElettrodomesticoCoordinator,
)
from custom_components.elettrodomestico_monitor.climate import _ClimaEntity


def _make_clima_entity(hass, *, clima_eid="climate.daikin_big", instance_id="clima_test", slot="1"):
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_INSTANCE_ID: instance_id,
        CONF_SLOT: slot,
        CONF_PRESET: "clima",
        CONF_TRIGGER_ENTITY: clima_eid,
    }, title=instance_id)
    entry.add_to_hass(hass)
    coord = ElettrodomesticoCoordinator(hass, entry)
    ent = _ClimaEntity(coord, entry, "Clima Big", slot, clima_eid)
    ent.hass = hass  # normalmente assegnato dalla entity platform di HA
    return ent


async def test_call_climate_delivers_when_entity_available(hass):
    """Caso base: il climate reale è disponibile → il comando viene
    inoltrato normalmente."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("climate.daikin_big", "heat")
    ent = _make_clima_entity(hass)

    await ent._call_climate("set_hvac_mode", {"hvac_mode": "cool"})

    assert len(calls) == 1
    assert calls[0].data.get("entity_id") == "climate.daikin_big"
    assert calls[0].data.get("hvac_mode") == "cool"


async def test_call_climate_skipped_when_entity_unavailable(hass, caplog):
    """FIX (segnalazione utente, 2026-10-21): il climate reale
    'unavailable' (es. un Daikin WiFi scollegato) non deve ricevere
    comandi — solo un log INFO con prefisso [EM x<slot>], mai il warning
    generico di HA su un'entità mancante."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    hass.states.async_set("climate.daikin_big", "unavailable")
    ent = _make_clima_entity(hass, slot="7")

    await ent._call_climate("set_hvac_mode", {"hvac_mode": "cool"})

    assert calls == []
    assert "[EM x7]" in caplog.text and "non disponibile" in caplog.text


async def test_call_climate_skipped_when_entity_does_not_exist(hass):
    """L'entità climate configurata non esiste affatto in hass.states —
    stesso comportamento sicuro di 'unavailable'."""
    calls = async_mock_service(hass, "climate", "set_hvac_mode")
    ent = _make_clima_entity(hass)  # climate.daikin_big non viene mai impostata

    await ent._call_climate("set_hvac_mode", {"hvac_mode": "cool"})

    assert calls == []
