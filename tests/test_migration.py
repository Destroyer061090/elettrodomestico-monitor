"""Test per custom_components/elettrodomestico_monitor/migration.py.

`async_migrate_entry()` gira ad ogni avvio di Home Assistant per OGNI
config entry dell'integrazione, in modo silenzioso (nessuna interazione
utente). È il punto più delicato dell'integrazione perché:
  - un bug qui può corrompere silenziosamente la configurazione salvata;
  - un'eccezione non gestita qui può impedire l'avvio dell'intera
    integrazione (o peggio, di Home Assistant) per TUTTI gli utenti che
    aggiornano;
  - è però anche il modulo più facile da testare in isolamento: nessuna
    dipendenza da sensori, entità reali o hardware — solo un ConfigEntry
    mockato.

Filosofia della migrazione (vedi anche il docstring del modulo): non deve
MAI perdere dati né forzare una riconfigurazione. Questi test verificano
esattamente quella garanzia.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import (
    CONF_APPLIANCE_NAME,
    CONF_BATTERY_SENSOR,
    CONF_ENTRY_TYPE,
    CONF_POWER_SENSOR,
    CONF_PRESET,
    CONF_SLOT,
    CONF_SWITCH_ENTITY,
    CONF_TRIGGER_ENTITY,
    CONF_VACUUM_ENTITY,
    DOMAIN,
    ENTRY_TYPE_APPLIANCE,
    ENTRY_TYPE_HUB,
)
from custom_components.elettrodomestico_monitor.migration import (
    _APPLIANCE_DEFAULTS,
    _SCHEMA_KEY,
    _SCHEMA_VERSION,
    async_migrate_entry,
)
from custom_components.elettrodomestico_monitor.presets import (
    PRESET_CLIMA,
    PRESET_VACUUM,
)


def _make_entry(hass, data: dict, title: str = "Test Appliance") -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=title)
    entry.add_to_hass(hass)
    return entry


async def test_hub_entry_is_never_touched(hass):
    """Un entry Hub non ha logica preset: deve tornare True senza modifiche."""
    entry = _make_entry(hass, {CONF_ENTRY_TYPE: ENTRY_TYPE_HUB})
    original_data = dict(entry.data)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert dict(entry.data) == original_data  # nessuna modifica, nemmeno un update_entry


async def test_missing_keys_are_filled_with_defaults(hass):
    """Un entry appliance 'vecchio' (creato prima di nuove chiavi) deve
    ricevere tutte le chiavi mancanti con i default, senza toccare quelle
    già presenti."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Lavatrice",
        CONF_SLOT: "1",
        CONF_PRESET: "elettrodomestico",
        CONF_POWER_SENSOR: "sensor.lavatrice_potenza",  # valore custom da preservare
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    # la chiave già presente NON deve essere sovrascritta
    assert entry.data[CONF_POWER_SENSOR] == "sensor.lavatrice_potenza"
    # tutte le chiavi di default devono ora esistere
    for key in _APPLIANCE_DEFAULTS:
        assert key in entry.data


async def test_complete_entry_is_not_updated(hass):
    """Se l'entry ha già tutte le chiavi E il marcatore di schema è già
    alla versione corrente, async_update_entry non deve essere chiamato
    (nessuna scrittura inutile su disco ad ogni riavvio)."""
    complete_data = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Lavatrice",
        CONF_SLOT: "1",
        CONF_PRESET: "elettrodomestico",
        **_APPLIANCE_DEFAULTS,
        _SCHEMA_KEY: _SCHEMA_VERSION,
    }
    entry = _make_entry(hass, complete_data)

    calls = []
    hass.config_entries.async_update_entry = lambda e, **kw: calls.append(kw)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert calls == []  # nessun update_entry chiamato: niente era cambiato


async def test_schema_marker_is_written_once_for_pre_marker_entries(hass):
    """FIX (audit v7.0.0, medio): un'entry creata prima dell'introduzione
    del marcatore di schema (_SCHEMA_KEY) non ce l'ha — la prima
    migrazione dopo l'aggiornamento deve scriverlo esattamente una volta
    (anche se l'entry ha già tutte le altre chiavi), non ad ogni riavvio."""
    complete_data_no_marker = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Lavatrice",
        CONF_SLOT: "1",
        CONF_PRESET: "elettrodomestico",
        **_APPLIANCE_DEFAULTS,
    }
    entry = _make_entry(hass, complete_data_no_marker)

    result = await async_migrate_entry(hass, entry)
    assert result is True
    assert entry.data[_SCHEMA_KEY] == _SCHEMA_VERSION

    # Una seconda migrazione (riavvio successivo) non deve scrivere di nuovo.
    calls = []
    hass.config_entries.async_update_entry = lambda e, **kw: calls.append(kw)
    result = await async_migrate_entry(hass, entry)
    assert result is True
    assert calls == []


async def test_vacuum_entity_autopopulated_from_trigger(hass):
    """Preset vacuum + trigger_entity=vacuum.* ma vacuum_entity vuoto:
    deve essere auto-popolato dal trigger (bug storico coperto da questa
    logica, vedi punto 4 di migration.py)."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Robot Cucina",
        CONF_SLOT: "2",
        CONF_PRESET: PRESET_VACUUM,
        CONF_TRIGGER_ENTITY: "vacuum.robot_cucina",
        CONF_VACUUM_ENTITY: "",
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.data[CONF_VACUUM_ENTITY] == "vacuum.robot_cucina"


async def test_vacuum_preset_mismatch_only_warns_never_raises(hass, caplog):
    """Trigger vacuum.* con preset sbagliato: deve solo loggare un
    warning, mai sollevare un'eccezione o bloccare l'avvio."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Configurato Male",
        CONF_SLOT: "3",
        CONF_PRESET: "elettrodomestico",  # sbagliato: dovrebbe essere PRESET_VACUUM
        CONF_TRIGGER_ENTITY: "vacuum.robot_salotto",
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert "vacuum" in caplog.text.lower()


async def test_clima_preset_mismatch_only_warns_never_raises(hass, caplog):
    """Stesso caso ma per il preset clima (punto 3 della migrazione)."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Clima Configurato Male",
        CONF_SLOT: "4",
        CONF_PRESET: "elettrodomestico",  # sbagliato: dovrebbe essere PRESET_CLIMA
        CONF_TRIGGER_ENTITY: "climate.soggiorno",
    })

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert "climate" in caplog.text.lower()


async def test_unexpected_exception_never_blocks_startup(hass, monkeypatch):
    """Garanzia più importante del modulo: qualunque eccezione interna
    NON deve propagarsi e NON deve impedire l'avvio dell'integrazione.
    async_migrate_entry deve sempre tornare True."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Entry Che Esplode",
        CONF_SLOT: "5",
        CONF_PRESET: "elettrodomestico",
    })

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure inside migration")

    monkeypatch.setattr(hass.config_entries, "async_update_entry", _boom)

    result = await async_migrate_entry(hass, entry)

    assert result is True  # non deve propagare l'eccezione


async def test_battery_sensor_default_preserved_when_present(hass):
    """Chiave già valorizzata dall'utente: la migrazione non deve mai
    sovrascriverla, nemmeno con un default 'sensato'."""
    entry = _make_entry(hass, {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_APPLIANCE_NAME: "Aspirapolvere",
        CONF_SLOT: "6",
        CONF_PRESET: PRESET_VACUUM,
        CONF_BATTERY_SENSOR: "sensor.custom_battery",
        CONF_SWITCH_ENTITY: "switch.custom",
    })

    await async_migrate_entry(hass, entry)

    assert entry.data[CONF_BATTERY_SENSOR] == "sensor.custom_battery"
    assert entry.data[CONF_SWITCH_ENTITY] == "switch.custom"
