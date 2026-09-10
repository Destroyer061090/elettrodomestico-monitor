"""Test per custom_components/elettrodomestico_monitor/irrigation_coordinator.py.

Letto per intero durante l'audit fase 2 (nessun bug bloccante trovato,
logica di sequenza solida). Questi test coprono i comportamenti più
delicati e un'osservazione emersa scrivendoli con esecuzione reale
(vedi `test_zone_turn_off_is_called_twice_but_harmlessly`).

`asyncio.sleep` viene monkeypatchato a zero: il ciclo reale impone un
minimo di 10s per zona (`max(10, ...)`) più 10s di pausa tra zone, che
renderebbero i test troppo lenti per l'esecuzione automatica — patchare
il tempo di attesa esercita esattamente la stessa logica di sequenza
senza aspettare i secondi reali.
"""
from __future__ import annotations

import asyncio

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.elettrodomestico_monitor import irrigation_coordinator as irr_mod
from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    CONF_FLOW_SENSOR,
    CONF_INSTANCE_ID,
    CONF_SLOT,
    CONF_ZONE_ORDER,
    CONF_ZONES,
    DOMAIN,
    ENTRY_TYPE_HUB,
)
from custom_components.elettrodomestico_monitor.irrigation_coordinator import (
    IrrigationCoordinator,
)


@pytest.fixture(autouse=True)
def _fast_sleep(monkeypatch):
    """Azzera asyncio.sleep SOLO dentro il modulo irrigation_coordinator,
    cosi' i 10s minimi per zona e i 10s di pausa tra zone non rallentano
    la suite di test — la sequenza/logica eseguita e' la stessa."""
    orig_sleep = irr_mod.asyncio.sleep
    monkeypatch.setattr(irr_mod.asyncio, "sleep", lambda t: orig_sleep(0))
    yield


def _make_coordinator(hass, zones, zone_order=None, instance_id="irr_test", **extra_config) -> IrrigationCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_INSTANCE_ID: instance_id,
        CONF_SLOT: "1",
        CONF_ZONES: zones,
        CONF_ZONE_ORDER: zone_order if zone_order is not None else list(range(len(zones))),
        **extra_config,
    })
    entry.add_to_hass(hass)
    return IrrigationCoordinator(hass, entry)


async def test_start_cycle_rejects_when_already_active(hass):
    """Garanzia più importante del modulo: non devono mai poter girare
    due cicli in parallelo sullo stesso impianto (doppio consumo,
    zone che si accavallano)."""
    coord = _make_coordinator(hass, [{"name": "Prato", "switch": "switch.z1", "duration_min": 0.01}])
    await coord.storage.async_load()
    coord._cycle_active = True

    await coord.start_cycle()

    assert coord._cycle_task is None  # nessun nuovo ciclo avviato


async def test_zones_activate_in_configured_order(hass):
    """Le zone devono attivarsi nell'ordine di zone_order, una alla
    volta — non in parallelo e non nell'ordine di definizione se
    zone_order lo sovrascrive."""
    coord = _make_coordinator(hass, [
        {"name": "Prato", "switch": "switch.z1", "duration_min": 0.01},
        {"name": "Siepe", "switch": "switch.z2", "duration_min": 0.01},
    ], zone_order=[1, 0])  # ordine invertito rispetto alla definizione
    await coord.storage.async_load()

    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")

    await coord.start_cycle()
    await coord._cycle_task

    turn_on_order = [c.data.get("entity_id") for c in turn_on_calls]
    assert turn_on_order == ["switch.z2", "switch.z1"]  # rispetta zone_order, non l'ordine di definizione
    assert coord._active_zone_idx == -1  # nessuna zona resta "attiva" a fine ciclo
    assert coord._cycle_active is False


async def test_manual_start_does_not_reissue_turn_on(hass):
    """Se l'utente ha già acceso manualmente lo switch della zona,
    start_cycle(manual=True) deve limitarsi a tracciare/contare senza
    ri-inviare un comando turn_on (che sarebbe ridondante e potrebbe
    interferire con l'accensione manuale in corso)."""
    coord = _make_coordinator(hass, [
        {"name": "Orto", "switch": "switch.z3", "duration_min": 0.01},
    ])
    await coord.storage.async_load()

    turn_on_calls = async_mock_service(hass, "homeassistant", "turn_on")
    turn_off_calls = async_mock_service(hass, "homeassistant", "turn_off")

    await coord.start_cycle(zone_idx=0, manual=True)
    await coord._cycle_task

    assert turn_on_calls == []  # nessun turn_on: lo switch era già acceso
    turn_off_z3 = [c for c in turn_off_calls if c.data.get("entity_id") == "switch.z3"]
    assert len(turn_off_z3) >= 1  # ma DEVE comunque spegnersi a fine durata


async def test_zone_turn_off_is_called_twice_but_harmlessly(hass):
    """Osservazione emersa scrivendo questo test (non un bug da correggere):
    lo spegnimento della zona attiva viene chiamato sia dentro il loop
    ('Deactivate zone') sia di nuovo nel blocco `finally` (rete di
    sicurezza 'ensure ALL zone switches are off'). Per un ciclo a zona
    singola questo significa DUE chiamate turn_off identiche — ridondante
    ma innocuo (spegnere uno switch già spento non ha effetti collaterali).
    Il test documenta il comportamento reale, non lo nasconde."""
    coord = _make_coordinator(hass, [
        {"name": "Orto", "switch": "switch.z4", "duration_min": 0.01},
    ])
    await coord.storage.async_load()

    turn_off_calls = async_mock_service(hass, "homeassistant", "turn_off")

    await coord.start_cycle()
    await coord._cycle_task

    turn_off_z4 = [c for c in turn_off_calls if c.data.get("entity_id") == "switch.z4"]
    assert len(turn_off_z4) == 2


async def test_cycle_time_is_not_double_counted(hass):
    """FIX (audit v7.0.0, CRITICO): il tempo veniva accumulato sia dai tick
    periodici di _async_update_data() (ogni COORDINATOR_UPDATE_INTERVAL,
    mentre _cycle_active è True) sia una seconda volta nel blocco `finally`
    di _run_cycle(), che ricalcolava e sommava elapsed_h dall'inizio del
    ciclo — un ciclo di 10 minuti risultava conteggiato come ~20 in
    "Tempo Oggi". Qui simuliamo 3 tick periodici durante un ciclo breve e
    verifichiamo che il tempo finale rifletta SOLO i tick, senza un
    ulteriore salto quando il ciclo termina."""
    coord = _make_coordinator(hass, [
        {"name": "Z", "switch": "switch.z8", "duration_min": 0.01},
    ])
    await coord.storage.async_load()
    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")

    await coord.start_cycle()
    # Simula 3 tick periodici del coordinator MENTRE il ciclo è attivo —
    # nella realtà _async_update_data gira ogni COORDINATOR_UPDATE_INTERVAL
    # indipendentemente dal task che sta eseguendo il ciclo.
    for _ in range(3):
        await coord._async_update_data()
    t_from_ticks = coord._t_today
    assert t_from_ticks > 0

    await coord._cycle_task  # il ciclo termina (durata minima + sleep mockato)

    # Il blocco finally NON deve sommare di nuovo il tempo trascorso reale:
    # il totale dopo la fine del ciclo deve restare quello dei tick, non raddoppiare.
    assert coord._t_today == t_from_ticks


async def test_interrupted_cycle_is_not_counted(hass):
    """Un ciclo fermato manualmente a metà (stop_cycle) non deve
    incrementare il contatore cicli — solo un ciclo completato per
    intero conta, altrimenti le statistiche mentirebbero."""
    coord = _make_coordinator(hass, [
        {"name": "Prato", "switch": "switch.z5", "duration_min": 5},  # durata lunga
    ])
    await coord.storage.async_load()

    async_mock_service(hass, "homeassistant", "turn_on")
    async_mock_service(hass, "homeassistant", "turn_off")

    cycles_before = coord._c_today
    await coord.start_cycle()
    coord._stop_requested = True  # interrompe subito, prima che scada la durata
    await coord._cycle_task

    assert coord._c_today == cycles_before  # NON incrementato


# ── Integrazione litri/kWh (stesso pattern verificato in coordinator.py) ─────

async def test_integrate_only_accumulates_during_active_cycle(hass):
    """A differenza del coordinator standard (che integra sempre se ha
    un sensore di potenza reale), l'irrigazione integra SOLO mentre un
    ciclo è attivo — fuori ciclo il flusso è a riposo e non va
    contabilizzato."""
    coord = _make_coordinator(hass, [{"name": "Z", "switch": "switch.z6", "duration_min": 1}])
    await coord.storage.async_load()
    coord._cycle_active = False
    coord._flow_w = 10.0

    coord._integrate()

    assert coord._l_total == 0.0


async def test_integrate_accumulates_litres_during_cycle(hass):
    """10 L/min per 60s (simulati spostando il timestamp) devono
    integrare a 10 litri esatti, leggendo il valore dal sensore di
    flusso reale configurato — non da un valore iniettato a mano."""
    coord = _make_coordinator(
        hass, [{"name": "Z", "switch": "switch.z7", "duration_min": 1}],
        **{CONF_FLOW_SENSOR: "sensor.flusso_z7"},
    )
    await coord.storage.async_load()
    hass.states.async_set("sensor.flusso_z7", "10")
    coord._cycle_active = True

    coord._integrate()  # prima chiamata: solo baseline, nessun accumulo
    assert coord._l_total == 0.0

    coord._last_int_ts -= 60
    coord._integrate()
    assert abs(coord._l_total - 10.0) < 1e-3


# ── Fix v6.2.5: notifica fine ciclo — rete/sole del CICLO, non del giorno ────

async def test_cycle_notification_shows_cycle_grid_split_not_daily_total(hass):
    """Stesso bug e stesso fix già applicati a coordinator.py (v6.2.4),
    trovato qui perché l'utente ha chiesto esplicitamente se la
    correzione copriva 'tutti i casi, inclusa l'irrigazione' — non li
    copriva: irrigation_coordinator.py ha una propria _notify_complete()
    indipendente, con lo stesso bug (leggeva il cumulativo di giornata
    invece del delta del singolo ciclo). Riprodotto con un'irrigazione
    precedente che aveva già usato un po' di rete oggi, e un ciclo
    successivo alimentato SOLO da accumulo."""
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_INSTANCE_ID: "irr_notify_test", CONF_SLOT: "1",
        CONF_ZONES: [{"name": "Siepe", "switch": "switch.siepe_notify", "duration_min": 0.01}],
        CONF_ZONE_ORDER: [0], CONF_FLOW_SENSOR: "sensor.flusso_siepe_notify",
    })
    entry.add_to_hass(hass)
    coord = IrrigationCoordinator(hass, entry)
    await coord.storage.async_load()

    hub_entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, "fv_enabled": True,
        "fv_grid_sensor": "sensor.grid_irr_notify", "costo_kwh": 0.25,
    }, title="Hub")
    hub_entry.add_to_hass(hass)

    # Un'irrigazione precedente OGGI ha già usato un po' di rete.
    coord._eg_today = 0.05
    coord._es_today = 0.02

    notified = {}
    orig_notify = coord._notify_complete
    async def _spy(duration, l_consumed, kwh_consumed, hub, eg_cycle=None, es_cycle=None):
        notified.update(eg_cycle=eg_cycle, es_cycle=es_cycle)
        await orig_notify(duration, l_consumed, kwh_consumed, hub, eg_cycle, es_cycle)
    coord._notify_complete = _spy

    task = asyncio.get_event_loop().create_task(coord.start_cycle())
    await asyncio.sleep(0.01)
    # Durante QUESTO specifico ciclo, +0.01 kWh SOLO da accumulo (nessun
    # contributo rete aggiuntivo oltre a quello già presente prima del ciclo).
    coord._es_today += 0.01
    await task
    await coord._cycle_task

    assert notified["eg_cycle"] == 0.0  # nessun prelievo rete in QUESTO ciclo
    assert abs(notified["es_cycle"] - 0.01) < 1e-9  # solo il contributo di QUESTO ciclo, non 0.02+0.01
