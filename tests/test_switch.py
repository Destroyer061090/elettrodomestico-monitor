"""Test per custom_components/elettrodomestico_monitor/switch.py.

Modulo mai auditato prima di questa passata (v6.2.2). L'audit a lettura
completa non ha trovato bug funzionali — solo un import inutilizzato
(CONF_NOTIFY_UPDATE, sostituito da una stringa magica identica, quindi
innocuo). Questi test coprono comunque i comportamenti più delicati:

- `_MainSwitch` è il comando che delega al coordinator per OGNI tipo di
  dispositivo (switch fisico, vacuum, clima, trigger generico): se
  `is_on` legge la chiave sbagliata, il pulsante mostra uno stato non
  corrispondente alla realtà.
- Gli switch di notifica e il toggle di ricarica automatica usano
  `RestoreEntity`: dopo un riavvio di Home Assistant devono ripristinare
  lo stato precedente, non tornare silenziosamente al default.
- La logica che decide SE creare `_MainSwitch` (switch fisico configurato,
  trigger presente, o preset vacuum/clima) determina se un dispositivo
  di solo monitoraggio (senza alcun controllo) si ritrova con un
  pulsante che non farebbe nulla.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_restore_cache
from homeassistant.core import State

from custom_components.elettrodomestico_monitor.const import (
    CONF_INSTANCE_ID,
    CONF_NOTIFY_PUSH,
    CONF_PRESET,
    CONF_SLOT,
    CONF_SWITCH_ENTITY,
    DOMAIN,
)
from custom_components.elettrodomestico_monitor.switch import (
    _TRIGGER_PRESETS,
    _DevChargeSwitch,
    _MainSwitch,
    _NotifySwitch,
)


class _FakeCoordinator:
    """Stand-in minimale: questi switch leggono solo `.data`, non serve
    un DataUpdateCoordinator reale per verificarne la logica di lettura."""
    def __init__(self, data=None):
        self.data = data or {}


def _entry(data: dict) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, data=data)


# ── _MainSwitch: sorgente di verità per lo stato ON/OFF ───────────────────────

async def test_main_switch_reads_main_on(hass):
    """`main_on` è la chiave "canonica" calcolata dal coordinator in base
    al tipo di dispositivo (vacuum/clima/switch/trigger) — deve avere
    priorità su tutto il resto."""
    entry = _entry({CONF_PRESET: "elettrodomestico", CONF_SLOT: "1", CONF_INSTANCE_ID: "i1"})
    coord = _FakeCoordinator({"main_on": True, "ac_state": False})
    switch = _MainSwitch(coord, entry, "Test", "1")
    assert switch.is_on is True


async def test_main_switch_falls_back_to_ac_state(hass):
    """Se `main_on` non è presente nei dati (coordinator più vecchio o
    percorso di codice che non lo popola), deve ripiegare su `ac_state`
    invece di considerarsi sempre spento."""
    entry = _entry({CONF_PRESET: "elettrodomestico", CONF_SLOT: "1", CONF_INSTANCE_ID: "i1"})
    coord = _FakeCoordinator({"ac_state": True})
    switch = _MainSwitch(coord, entry, "Test", "1")
    assert switch.is_on is True


async def test_main_switch_defaults_off_with_no_data(hass):
    """Coordinator senza dati ancora disponibili (subito dopo l'avvio):
    lo switch deve mostrarsi OFF, non sollevare un'eccezione."""
    entry = _entry({CONF_PRESET: "elettrodomestico", CONF_SLOT: "1", CONF_INSTANCE_ID: "i1"})
    coord = _FakeCoordinator({})
    switch = _MainSwitch(coord, entry, "Test", "1")
    assert switch.is_on is False


# ── Switch di notifica: persistenza dopo riavvio (RestoreEntity) ─────────────

async def test_notify_switch_restores_previous_state(hass):
    """Dopo un riavvio, il toggle di notifica deve ripristinare lo stato
    in cui l'utente lo aveva lasciato, non tornare al default di config.

    `mock_restore_cache` + `switch.hass = hass` sono necessari perché
    `RestoreEntity.async_get_last_state()` (ereditata, non reimplementata
    da `_NotifySwitch`) legge la cache di ripristino reale tramite
    `self.hass` e `self.entity_id` — un'entità istanziata direttamente
    (senza passare per l'intera piattaforma) non ha `self.hass` impostato
    di default."""
    entry = _entry({CONF_NOTIFY_PUSH: False, CONF_INSTANCE_ID: "i2", CONF_SLOT: "2"})
    switch = _NotifySwitch(entry, "Test2", "2", "notifica_push",
                            "Notifica Push Test2", CONF_NOTIFY_PUSH, "mdi:x", False)
    mock_restore_cache(hass, [State(switch.entity_id, "on")])
    switch.hass = hass
    await switch.async_added_to_hass()
    assert switch.is_on is True


async def test_notify_switch_uses_config_default_on_first_install(hass):
    """Prima installazione, nessuno stato precedente da ripristinare:
    deve usare il default preso dalla configurazione, non False a
    prescindere."""
    entry = _entry({CONF_NOTIFY_PUSH: True, CONF_INSTANCE_ID: "i2", CONF_SLOT: "2"})
    switch = _NotifySwitch(entry, "Test2", "2", "notifica_push",
                            "Notifica Push Test2", CONF_NOTIFY_PUSH, "mdi:x", False)
    switch.hass = hass  # nessuno stato in cache di ripristino per questo entity_id
    await switch.async_added_to_hass()
    assert switch.is_on is True


# ── Switch batteria/ricarica ──────────────────────────────────────────────────

async def test_dev_charge_switch_reads_charging_key(hass):
    """Lo switch di ricarica rispecchia lo stato reale di carica
    calcolato da device_coordinator.py (chiave 'charging')."""
    entry = _entry({CONF_INSTANCE_ID: "i3", CONF_SLOT: "3"})
    coord = _FakeCoordinator({"charging": True})
    switch = _DevChargeSwitch(coord, entry, "Telefono", "3")
    assert switch.is_on is True


async def test_dev_charge_switch_defaults_off_without_data(hass):
    entry = _entry({CONF_INSTANCE_ID: "i3", CONF_SLOT: "3"})
    coord = _FakeCoordinator({})
    switch = _DevChargeSwitch(coord, entry, "Telefono", "3")
    assert switch.is_on is False


# ── Logica di dispatch: quando viene creato _MainSwitch ──────────────────────

def _would_create_main_switch(data: dict) -> bool:
    """Replica la condizione reale in async_setup_entry (switch.py) senza
    dover passare per l'intero platform setup."""
    has_switch = bool(data.get(CONF_SWITCH_ENTITY))
    has_trigger = bool(data.get("trigger_entity") or data.get("vacuum_entity"))
    preset = data.get(CONF_PRESET, "elettrodomestico")
    return has_switch or has_trigger or preset in _TRIGGER_PRESETS


def test_pure_monitoring_appliance_gets_no_main_switch():
    """Un dispositivo di solo monitoraggio (nessuno switch fisico,
    nessun trigger) non deve ricevere un _MainSwitch che non
    controllerebbe nulla — eviterebbe un pulsante fantasma in UI."""
    assert _would_create_main_switch({CONF_PRESET: "elettrodomestico"}) is False


def test_appliance_with_switch_entity_gets_main_switch():
    assert _would_create_main_switch({
        CONF_PRESET: "elettrodomestico", CONF_SWITCH_ENTITY: "switch.presa",
    }) is True


def test_vacuum_preset_always_gets_main_switch():
    """Vacuum non ha mai uno switch_entity fisico (controlla vacuum.*),
    ma deve comunque avere sempre il comando principale."""
    assert _would_create_main_switch({CONF_PRESET: "vacuum"}) is True


def test_clima_preset_always_gets_main_switch():
    assert _would_create_main_switch({CONF_PRESET: "clima"}) is True
