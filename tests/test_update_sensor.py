"""Test per _UpdateSensor in custom_components/elettrodomestico_monitor/sensor.py.

Richiesto dall'utente dopo aver visto, nel popup Info della card, la
dicitura generica "Aggiornamento: Aggiornamento disponibile" senza alcuna
indicazione di QUALE versione fosse disponibile — l'informazione (il tag
GitHub) era già letta e disponibile come attributo (`versione_disponibile`),
semplicemente non veniva mai inclusa nello STATO del sensore, che è ciò che
il popup Info mostra.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import DOMAIN
from custom_components.elettrodomestico_monitor.sensor import _UpdateSensor


class _FakeUpdateCoordinator:
    """Stand-in minimale: _UpdateSensor legge solo .data."""
    def __init__(self, data: dict):
        self.data = data


def test_no_update_shows_aggiornato(hass):
    """Nessun aggiornamento disponibile: stato invariato, 'Aggiornato'."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    coord = _FakeUpdateCoordinator({"update_available": False, "current_version": "6.2.5"})
    sensor = _UpdateSensor(coord, entry)
    assert sensor.native_value == "Aggiornato"


def test_update_available_includes_version_tag(hass):
    """FIX v6.2.6: lo stato deve includere il tag di versione trovato su
    GitHub (es. 'v6.2.6'), non più un testo generico senza indicazione di
    quale versione sia disponibile — questa è la stringa che il popup
    Info della card mostra direttamente all'utente."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    coord = _FakeUpdateCoordinator({"update_available": True, "latest_version": "6.2.6"})
    sensor = _UpdateSensor(coord, entry)
    assert sensor.native_value == "Aggiornamento disponibile v6.2.6"


def test_update_available_without_tag_falls_back_safely(hass):
    """Caso difensivo (non dovrebbe verificarsi in pratica, ma
    update_coordinator.py potrebbe teoricamente restituire
    update_available=True senza aver ancora popolato latest_version):
    nessun crash, testo generico invece di 'v' seguito dal nulla."""
    entry = MockConfigEntry(domain=DOMAIN, data={})
    coord = _FakeUpdateCoordinator({"update_available": True})
    sensor = _UpdateSensor(coord, entry)
    assert sensor.native_value == "Aggiornamento disponibile"
