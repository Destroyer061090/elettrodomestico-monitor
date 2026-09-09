"""Test per custom_components/elettrodomestico_monitor/coordinator.py.

È il cuore del calcolo consumi/costi: gira ogni COORDINATOR_UPDATE_INTERVAL
secondi per ogni dispositivo configurato, integra la potenza istantanea in
kWh, gestisce la ripartizione fotovoltaica (rete vs sole) e i reset
giornalieri/mensili/annuali delle statistiche. Un errore qui non blocca
l'avvio (a differenza di migration.py) ma produce dati economici sbagliati
in modo silenzioso — il tipo di bug che l'utente nota solo mesi dopo
confrontando le bollette.
"""
from __future__ import annotations

import time
import datetime

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    CONF_INSTANCE_ID,
    CONF_POWER_SENSOR,
    CONF_PRESET,
    CONF_SLOT,
    CONF_SOURCE_UNIT,
    CONF_TRIGGER_ENTITY,
    DOMAIN,
    ENTRY_TYPE_HUB,
)
from custom_components.elettrodomestico_monitor.coordinator import (
    ElettrodomesticoCoordinator,
)


def _make_coordinator(hass, data: dict, instance_id: str) -> ElettrodomesticoCoordinator:
    full_data = {CONF_INSTANCE_ID: instance_id, **data}
    entry = MockConfigEntry(domain=DOMAIN, data=full_data, title=instance_id)
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})
    coord = ElettrodomesticoCoordinator(hass, entry)
    hass.data[DOMAIN][instance_id] = coord
    return coord


def _make_hub_entry(hass, **fv_kwargs) -> None:
    hub_data = {CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, **fv_kwargs}
    entry = MockConfigEntry(domain=DOMAIN, data=hub_data, title="Hub")
    entry.add_to_hass(hass)


# ── Soglia di lavoro ──────────────────────────────────────────────────────────

async def test_default_threshold_is_10w(hass):
    """La soglia di default per un elettrodomestico generico è 10W."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "1", CONF_PRESET: "elettrodomestico",
    }, "thr1")
    assert coord._threshold == 10.0


async def test_flow_based_source_uses_low_threshold(hass):
    """Sorgenti a flusso (irrigazione, L/min) usano una soglia bassa (0.1)
    invece del default a potenza: qualunque flusso reale deve registrare
    un ciclo attivo, a differenza di un elettrodomestico dove 10W di
    rumore di fondo non deve far scattare un falso 'in funzione'."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "2", CONF_PRESET: "elettrodomestico", CONF_SOURCE_UNIT: "L/min",
    }, "thr2")
    assert coord._threshold == 0.1


# ── Integrazione kWh ──────────────────────────────────────────────────────────

async def test_integrate_first_call_only_sets_baseline(hass):
    """La primissima chiamata a _integrate() non deve accumulare nulla:
    non c'è un intervallo di tempo precedente da integrare."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "3", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p3",
    }, "int1")
    coord._power_w = 1000.0
    coord._integrate()
    assert coord._acc_total == 0.0


async def test_integrate_constant_power_one_hour(hass):
    """1000W costanti per 1 ora devono integrare esattamente a 1.0 kWh —
    è il calcolo alla base di ogni costo mostrato all'utente."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "4", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p4",
    }, "int2")
    coord._power_w = 1000.0
    coord._integrate()
    coord._last_int_ts -= 3600  # simula un'ora trascorsa dall'ultima lettura
    coord._integrate()
    assert abs(coord._acc_total - 1.0) < 1e-3
    assert abs(coord._e_today - coord._acc_total) < 1e-9


async def test_integrate_negative_power_does_not_subtract_energy(hass):
    """Un sensore anomalo che riporta potenza negativa non deve MAI
    generare energia negativa (protezione già presente: `if delta > 0`).
    Verifica che non regredisca."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "5", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p5",
    }, "int3")
    coord._power_w = -500.0
    coord._integrate()
    coord._last_int_ts -= 3600
    coord._power_w = -500.0
    coord._integrate()
    assert coord._acc_total == 0.0


# ── Split fotovoltaico (rete vs sole) ─────────────────────────────────────────

async def test_fv_disabled_returns_none(hass):
    """FV non abilitato a livello hub: nessuna ripartizione, tutto va
    contabilizzato come costo pieno (comportamento pre-v6)."""
    _make_hub_entry(hass, fv_enabled=False)
    coord = _make_coordinator(hass, {
        CONF_SLOT: "6", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p6",
    }, "fv1")
    assert coord._fv_grid_fraction() is None


async def test_fv_grid_sensor_unknown_falls_back_safely(hass):
    """Sensore di rete in stato 'unknown' (es. all'avvio, prima del primo
    valore): deve tornare None invece di stimare un valore inventato o
    sollevare un'eccezione che romperebbe l'intero update del coordinator."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "unknown")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "7", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p7",
    }, "fv2")
    assert coord._fv_grid_fraction() is None


async def test_fv_grid_sensor_unavailable_falls_back_safely(hass):
    """Stesso caso ma con 'unavailable' (es. integrazione del sensore di
    rete temporaneamente offline)."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "unavailable")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "8", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p8",
    }, "fv3")
    assert coord._fv_grid_fraction() is None


async def test_fv_all_from_grid(hass):
    """Dispositivo assorbe 1000W, il sensore di rete misura 1000W di
    prelievo: tutta l'energia viene dalla rete, fraction = 1.0."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "1000")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "9", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p9",
    }, "fv4")
    coord._power_w = 1000.0
    assert coord._fv_grid_fraction() == 1.0


async def test_fv_all_from_solar_when_exporting(hass):
    """Il sensore di rete misura un export (valore negativo, convenzione
    standard + import / - export): il dispositivo è alimentato
    interamente dal fotovoltaico, fraction = 0.0. Verifica anche che
    max(0.0, ...) impedisca una frazione negativa."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "-500")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "10", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p10",
    }, "fv5")
    coord._power_w = 1000.0
    assert coord._fv_grid_fraction() == 0.0


async def test_fv_proportional_split(hass):
    """Caso intermedio: dispositivo 1000W, rete fornisce solo 400W —
    il resto (600W) viene dal sole. fraction = 0.4."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "400")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "11", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p11",
    }, "fv6")
    coord._power_w = 1000.0
    assert abs(coord._fv_grid_fraction() - 0.4) < 1e-9


async def test_fv_inverted_sensor_convention(hass):
    """Alcuni sensori di rete usano la convenzione opposta (+ export /
    - import). Con fv_invert=True, un valore di -1000 deve essere letto
    come 1000W di prelievo reale (fraction = 1.0), non come export."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid", fv_invert=True)
    hass.states.async_set("sensor.grid", "-1000")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "12", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p12",
    }, "fv7")
    coord._power_w = 1000.0
    assert coord._fv_grid_fraction() == 1.0


async def test_fv_exclude_overrides_global_setting(hass):
    """Un dispositivo con fv_exclude=True non deve MAI ricevere lo split
    fotovoltaico, anche se il FV è abilitato globalmente a livello hub
    (es. un carico che si vuole sempre contabilizzare a tariffa piena)."""
    _make_hub_entry(hass, fv_enabled=True, fv_grid_sensor="sensor.grid")
    hass.states.async_set("sensor.grid", "1000")
    coord = _make_coordinator(hass, {
        CONF_SLOT: "13", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p13",
        "fv_exclude": True,
    }, "fv8")
    coord._power_w = 1000.0
    assert coord._fv_grid_fraction() is None


# ── Reset giornaliero / mensile / annuale ─────────────────────────────────────

async def test_midnight_moves_today_to_yesterday(hass):
    """Al passaggio di mezzanotte, i contatori 'oggi' diventano 'ieri' e
    vengono azzerati per il nuovo giorno. Include i contatori FV separati
    (eg_/es_), che devono seguire la stessa logica."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "14", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p14",
    }, "mid1")
    await coord.storage.async_load()
    coord._e_today, coord._t_today, coord._c_today = 2.5, 3.0, 4
    coord._eg_today, coord._es_today = 2.0, 0.5

    class _FakeNow:
        day, month = 15, 6
        def weekday(self): return 0

    await coord._midnight(_FakeNow())

    assert coord.storage.get("energy_yesterday") == 2.5
    assert coord._e_today == 0.0
    assert coord.storage.get("cycles_yesterday") == 4
    assert coord.storage.get("eg_yesterday") == 2.0
    assert coord.storage.get("es_yesterday") == 0.5


async def test_midnight_first_of_month_also_rolls_monthly(hass):
    """Il giorno 1 del mese, oltre al rollover giornaliero, deve scattare
    anche quello mensile."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "15", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p15",
    }, "mid2")
    await coord.storage.async_load()
    coord._e_month, coord._c_month = 50.0, 20

    class _FakeNow:
        day, month = 1, 7
        def weekday(self): return 2

    await coord._midnight(_FakeNow())

    assert coord.storage.get("energy_last_month") == 50.0
    assert coord._e_month == 0.0


async def test_midnight_jan_first_also_rolls_yearly(hass):
    """Il 1° gennaio deve scattare anche il rollover annuale, oltre a
    quello giornaliero e mensile."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "16", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p16",
    }, "mid3")
    await coord.storage.async_load()
    coord._e_year = 500.0

    class _FakeNow:
        day, month = 1, 1
        def weekday(self): return 3

    await coord._midnight(_FakeNow())

    assert coord.storage.get("energy_last_year") == 500.0
    assert coord._e_year == 0.0


async def test_midnight_open_cycle_counts_as_one_not_zero(hass):
    """Caso limite documentato nel codice stesso: se un ciclo è ancora in
    corso a mezzanotte, 'ieri' non deve mostrare 0 cicli con ore di
    utilizzo accumulate (visivamente incoerente per l'utente) — deve
    contare come 1, senza rischio di doppio conteggio quando il ciclo
    si chiuderà effettivamente oggi."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "17", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p17",
    }, "mid4")
    await coord.storage.async_load()
    coord._ac_state = True
    coord.data = {"cycle_active": True}

    class _FakeNow:
        day, month = 20, 6
        def weekday(self): return 4

    await coord._midnight(_FakeNow())

    assert coord.storage.get("cycles_yesterday") == 1


# ── Condivisione sensore tra più dispositivi ──────────────────────────────────

async def test_shared_power_sensor_splits_among_active_devices(hass):
    """Due dispositivi condividono lo stesso sensore di potenza fisico
    (es. una presa smart che misura due carichi a monte). Solo il device
    ATTIVO deve ricevere la potenza."""
    hass.states.async_set("sensor.shared", "900")
    hass.states.async_set("binary_sensor.a_active", "on")
    hass.states.async_set("binary_sensor.b_active", "off")

    coord_a = _make_coordinator(hass, {
        CONF_SLOT: "1", CONF_PRESET: "elettrodomestico",
        CONF_POWER_SENSOR: "sensor.shared", CONF_TRIGGER_ENTITY: "binary_sensor.a_active",
    }, "a_device")
    coord_b = _make_coordinator(hass, {
        CONF_SLOT: "2", CONF_PRESET: "elettrodomestico",
        CONF_POWER_SENSOR: "sensor.shared", CONF_TRIGGER_ENTITY: "binary_sensor.b_active",
    }, "b_device")

    await coord_a._read_power()
    await coord_b._read_power()

    assert coord_a._power_w == 900.0
    assert coord_b._power_w == 0.0


async def test_shared_power_sensor_no_longer_lags_between_coordinators(hass):
    """FIX v6.2.2: prima di questo fix, il coordinator con l'instance_id
    più basso ("master") calcolava la ripartizione per tutto il gruppo
    ad ogni proprio update, e gli altri ("slave") si limitavano a
    leggere quel valore — restando fino a un intero intervallo di
    polling indietro se il dispositivo attivo cambiava esattamente tra
    un update del master e uno slave (comportamento confermato con
    esecuzione reale durante l'audit). Ora ogni coordinator ricalcola la
    propria quota in modo indipendente al proprio turno: questo test
    verifica che lo slave veda il valore fresco IMMEDIATAMENTE al
    proprio update, senza dover aspettare che l'altro coordinator
    rifaccia il giro."""
    hass.states.async_set("sensor.shared", "900")
    hass.states.async_set("binary_sensor.a_active", "on")
    hass.states.async_set("binary_sensor.b_active", "off")

    coord_a = _make_coordinator(hass, {
        CONF_SLOT: "1", CONF_PRESET: "elettrodomestico",
        CONF_POWER_SENSOR: "sensor.shared", CONF_TRIGGER_ENTITY: "binary_sensor.a_active",
    }, "a_device2")
    coord_b = _make_coordinator(hass, {
        CONF_SLOT: "2", CONF_PRESET: "elettrodomestico",
        CONF_POWER_SENSOR: "sensor.shared", CONF_TRIGGER_ENTITY: "binary_sensor.b_active",
    }, "b_device2")

    await coord_a._read_power()
    await coord_b._read_power()
    assert coord_b._power_w == 0.0  # b non attivo: nessuna quota

    # "b" diventa attivo. Aggiorniamo SOLO b (a non rifà il proprio giro):
    # prima del fix, b sarebbe rimasto a 0.0 fino al prossimo update di a.
    hass.states.async_set("binary_sensor.b_active", "on")
    await coord_b._read_power()

    assert coord_b._power_w == 450.0  # fresco, calcolato da solo — non più in ritardo


# ── Fix v6.2.2: stato "ciclo terminato" pubblicato subito ────────────────────

async def test_cycle_end_publishes_inactive_state_immediately(hass):
    """Prima del fix, `self.data` restava con `cycle_active=True` (e un
    timer "In funzione" che continuava a scorrere) per l'intera durata
    di `asyncio.sleep(5)` dentro `_cycle_end()`, anche se il dispositivo
    era già spento. Ora la pubblicazione con `cycle_active=False` e i
    valori finali del ciclo deve avvenire subito, non dopo il delay."""
    import asyncio
    import time

    coord = _make_coordinator(hass, {
        CONF_SLOT: "18", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p18",
    }, "cend_test")
    await coord.storage.async_load()
    coord._cycle_active = True
    coord._cycle_start_ts = time.time() - 120
    coord._cycle_start_acc = 0.0
    coord._acc_total = 0.5

    task = asyncio.get_event_loop().create_task(coord._cycle_end())
    await asyncio.sleep(0.05)  # ben prima che scada il vecchio sleep(5)

    assert coord.data is not None
    assert coord.data.get("cycle_active") is False

    await task  # lascia terminare il task per non lasciare pendenze tra i test


# ── Fix v6.2.3: costo storico settimanale non ricalcolato col prezzo attuale ─

async def test_weekly_cost_uses_historical_price_not_current(hass):
    """Prima del fix, il costo mostrato per un giorno passato (es. 'Lunedì')
    veniva SEMPRE ricalcolato con il prezzo €/kWh ATTUALE, scartando il
    valore corretto già salvato in storage con il prezzo in vigore quel
    giorno. Per un prezzo fisso questo è invisibile (non cambia mai), ma
    per chi usa un sensore di costo dinamico il costo storico cambiava
    ogni volta che il prezzo di oggi cambiava — bug reale, confermato con
    esecuzione reale durante l'audit."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "19", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p19",
    }, "week_test")
    await coord.storage.async_load()

    hub_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, "costo_kwh": 0.20}, title="Hub")
    hub_entry.add_to_hass(hass)

    coord._e_today = 10.0
    lunedi = __import__("datetime").datetime(2026, 7, 20, 23, 59, 59)  # lunedì
    await coord._midnight(lunedi)

    stored = coord.storage.get("weekly")["lunedi"]
    assert stored["costo"] == 2.0  # 10 kWh * 0.20 €/kWh

    # il prezzo cambia OGGI (es. sensore dinamico)
    hass.config_entries.async_update_entry(hub_entry, data={**hub_entry.data, "costo_kwh": 0.50})
    data = coord._build()

    assert data["weekly"]["lunedi"]["costo"] == 2.0  # NON deve diventare 5.0


async def test_weekly_cost_falls_back_to_recompute_for_legacy_data(hass):
    """Retrocompatibilità: dati salvati PRIMA di questo fix non hanno il
    campo 'costo' — per quelli il ricalcolo resta l'unica opzione
    disponibile (nessun valore storico da preservare)."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "20", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.p20",
    }, "week_legacy")
    await coord.storage.async_load()

    hub_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, "costo_kwh": 0.30}, title="Hub")
    hub_entry.add_to_hass(hass)

    coord.storage._data.setdefault("weekly", {})["martedi"] = {
        "cicli": "1", "tempo": "1h", "consumo": 5.0,  # niente "costo": dato salvato prima del fix
    }
    data = coord._build()

    assert data["weekly"]["martedi"]["costo"] == round(5.0 * coord._cost_factor * 0.30, 2)



# ── Fix v6.2.4: notifica di fine ciclo — rete/sole del CICLO, non del giorno ──

async def test_cycle_notification_shows_cycle_grid_split_not_daily_total(hass):
    """Bug segnalato da un utente reale: un ciclo alimentato interamente da
    accumulo/batteria (0€ di rete PER QUEL CICLO) mostrava comunque un
    "Rete: X €" diverso da zero nella notifica — perché il valore veniva
    letto dal cumulativo di TUTTA la giornata (che includeva un uso
    precedente con la rete), non dal delta del singolo ciclo appena
    concluso. "Costo" era invece corretto (calcolato per il solo ciclo),
    quindi Rete+Sole non sommava mai a Costo — la discrepanza che ha
    permesso di individuare il bug.
    Riprodotto con gli stessi numeri riportati dall'utente: dopo il fix,
    Rete/Sole riflettono solo QUESTO ciclo, non l'intera giornata."""
    coord = _make_coordinator(hass, {
        CONF_SLOT: "21", CONF_PRESET: "elettrodomestico", CONF_POWER_SENSOR: "sensor.macchina_caffe",
    }, "notify_cycle_test")
    await coord.storage.async_load()

    hub_entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_HUB, "fv_enabled": True,
        "fv_grid_sensor": "sensor.grid_notify_test", "costo_kwh": 0.25,
    }, title="Hub")
    hub_entry.add_to_hass(hass)

    # Un caffè precedente, oggi, ha già usato un po' di rete: cumulativo
    # di giornata diverso da zero PRIMA che inizi il ciclo che testiamo.
    coord._eg_today = 0.08
    coord._es_today = 0.04

    hass.states.async_set("sensor.macchina_caffe", "500")
    hass.states.async_set("sensor.grid_notify_test", "-50")  # casa in export: alimentata da accumulo

    await coord._cycle_start()
    await coord._read_power()
    coord._integrate()  # baseline
    coord._last_int_ts -= 180  # 3 minuti dopo
    await coord._read_power()
    coord._integrate()  # 500W per 3 min, tutto attribuito a "sole" (grid negativo)

    notified = {}
    orig_notify = coord._notify
    async def _spy(duration, consumption, cost, rete_cost=None, sole_cost=None):
        notified.update(cost=cost, rete_cost=rete_cost, sole_cost=sole_cost)
        await orig_notify(duration, consumption, cost, rete_cost, sole_cost)
    coord._notify = _spy

    await coord._cycle_end()

    assert notified["rete_cost"] == 0.0  # QUESTO ciclo non ha usato la rete
    assert notified["sole_cost"] == notified["cost"]  # tutto il costo del ciclo è solare
    assert round(notified["rete_cost"] + notified["sole_cost"], 2) == notified["cost"]  # ora tornano
