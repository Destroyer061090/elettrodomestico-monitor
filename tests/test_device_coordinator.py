"""Test per custom_components/elettrodomestico_monitor/device_coordinator.py.

Modulo mai testato prima di questa passata (v6.2.3). Gestisce la ricarica
automatica di dispositivi a batteria (telefoni/tablet) tramite isteresi
su due soglie percentuali — non traccia energia/costo (per design: il
preset "dispositivo" selezionabile in UI instrada qui, non al coordinator
standard con PresetConfig/cost tracking).

L'audit ha trovato un bug reale: nessuna validazione impedisce di
impostare la soglia di avvio maggiore o uguale a quella di stop (sia in
config_flow che modificando i number entity dinamici in dashboard).
Confermato con esecuzione reale che questo causa un toggling continuo
ON/OFF ad ogni aggiornamento — questi test bloccano sia lo scenario
corretto sia quello che ha rivelato il bug.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import (
    CONF_DEV_BATTERY_SENSOR,
    CONF_DEV_CHARGE_SWITCH,
    CONF_DEV_START_PCT,
    CONF_DEV_STOP_PCT,
    CONF_INSTANCE_ID,
    CONF_SLOT,
    DOMAIN,
)
from custom_components.elettrodomestico_monitor.device_coordinator import (
    DeviceCoordinator,
)


def _make_coordinator(hass, start_pct, stop_pct, instance_id="dev_test") -> DeviceCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_INSTANCE_ID: instance_id,
        CONF_SLOT: "1",
        CONF_DEV_BATTERY_SENSOR: f"sensor.batt_{instance_id}",
        CONF_DEV_CHARGE_SWITCH: f"switch.charge_{instance_id}",
        CONF_DEV_START_PCT: start_pct,
        CONF_DEV_STOP_PCT: stop_pct,
    })
    entry.add_to_hass(hass)
    return DeviceCoordinator(hass, entry)


async def test_charging_starts_below_start_threshold(hass):
    """Batteria sotto la soglia di avvio: la carica deve attivarsi e il
    ciclo deve essere contato UNA volta."""
    coord = _make_coordinator(hass, start_pct=20, stop_pct=80)
    await coord.async_init()
    hass.states.async_set("switch.ricarica_auto_dispositivo_x1", "on")
    hass.states.async_set(f"sensor.batt_dev_test", "15")
    hass.states.async_set(f"switch.charge_dev_test", "off")

    await coord._async_update_data()

    assert coord._charging is True
    assert coord._c_today == 1


async def test_charging_does_not_double_count_while_below_threshold(hass):
    """Restare sotto la soglia per più aggiornamenti consecutivi non deve
    incrementare il contatore cicli ad ogni tick — solo la transizione
    conta, non lo stato sostenuto."""
    coord = _make_coordinator(hass, start_pct=20, stop_pct=80)
    await coord.async_init()
    hass.states.async_set("switch.ricarica_auto_dispositivo_x1", "on")
    hass.states.async_set("sensor.batt_dev_test", "15")
    hass.states.async_set("switch.charge_dev_test", "off")

    for _ in range(4):
        await coord._async_update_data()

    assert coord._c_today == 1


async def test_charging_stops_above_stop_threshold(hass):
    """Batteria sopra la soglia di stop: la carica deve fermarsi."""
    coord = _make_coordinator(hass, start_pct=20, stop_pct=80)
    await coord.async_init()
    hass.states.async_set("switch.ricarica_auto_dispositivo_x1", "on")
    hass.states.async_set("sensor.batt_dev_test", "15")
    hass.states.async_set("switch.charge_dev_test", "off")
    await coord._async_update_data()
    assert coord._charging is True

    hass.states.async_set("sensor.batt_dev_test", "85")
    await coord._async_update_data()

    assert coord._charging is False


async def test_inverted_thresholds_are_rejected_not_toggled(hass, caplog):
    """FIX v6.2.3: soglie invertite (avvio >= stop) — configurabili sia in
    config_flow che dai number entity dinamici in dashboard, nessuno dei
    due valida la coppia — causavano un toggling ON/OFF continuo ad ogni
    aggiornamento (confermato con esecuzione reale: 6 cambi su 6 update).
    Ora il controllo automatico si sospende con un warning invece di
    comportarsi in modo imprevedibile."""
    coord = _make_coordinator(hass, start_pct=80, stop_pct=20, instance_id="dev_inverted")
    await coord.async_init()
    hass.states.async_set("switch.ricarica_auto_dispositivo_x1", "on")
    hass.states.async_set("sensor.batt_dev_inverted", "50")
    hass.states.async_set("switch.charge_dev_inverted", "off")

    toggles = 0
    for _ in range(6):
        before = coord._charging
        await coord._async_update_data()
        if coord._charging != before:
            toggles += 1

    assert toggles == 0
    assert coord._c_today == 0
    assert "soglia avvio" in caplog.text.lower()


async def test_equal_thresholds_are_also_rejected(hass):
    """Caso limite: soglie identiche (non solo invertite) devono essere
    trattate allo stesso modo — non hanno senso quanto quelle invertite."""
    coord = _make_coordinator(hass, start_pct=50, stop_pct=50, instance_id="dev_equal")
    await coord.async_init()
    hass.states.async_set("switch.ricarica_auto_dispositivo_x1", "on")
    hass.states.async_set("sensor.batt_dev_equal", "50")
    hass.states.async_set("switch.charge_dev_equal", "off")

    await coord._async_update_data()

    assert coord._charging is False
    assert coord._c_today == 0
