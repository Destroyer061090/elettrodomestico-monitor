"""Test per custom_components/elettrodomestico_monitor/sensor.py.

Nessun test prima di questa passata (audit v7.0.0) copriva sensor.py, e
proprio lì viveva il bug più grave trovato dall'audit: quasi tutti i
sensori "periodo" (oggi/mese/anno) e il totale a vita (acc_total) erano
dichiarati con state_class TOTAL invece di TOTAL_INCREASING — ma il loro
valore viene azzerato ogni notte/mese/anno da coordinator._midnight() /
irrigation_coordinator._midnight(), o dal pulsante "Reset Contatori". Con
TOTAL, Home Assistant interpreta un calo come dato reale (es. immissione
in rete) invece che come reset del contatore, e registra un picco negativo
fittizio nelle Statistiche a lungo termine / Energy Dashboard — corrompendo
silenziosamente l'unico storico che l'utente guarda.

Questi test enumerano i sensori periodo/totale (elettrodomestici e
irrigazione) e verificano lo state_class dichiarato, così una futura
regressione viene intercettata meccanicamente invece che scoperta solo
ispezionando lo storico dell'Energy Dashboard mesi dopo.

NOTA (v7.0.1): la 7.0.0 aveva corretto TUTTI i sensori periodo a
TOTAL_INCREASING indiscriminatamente, inclusi quelli di costo in €
(_CostoPeriod, _RisparmioSole, _CostoRete, _IrrCosto). Sbagliato — vedi
test_cost_and_solar_saving_sensors_have_no_state_class e
test_irrigation_cost_sensors_have_no_state_class qui sotto per il perché
(device_class monetary incompatibile, e valore non garantito monotono con
tariffa dinamica). Solo i sensori FISICI (kWh/L/cicli, genuinamente
monotoni) restano TOTAL_INCREASING.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorStateClass
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.elettrodomestico_monitor import sensor as sensor_mod
from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    CONF_INSTANCE_ID,
    CONF_PRESET,
    CONF_SLOT,
    DOMAIN,
    ENTRY_TYPE_APPLIANCE,
    ENTRY_TYPE_IRRIGATION,
)
from custom_components.elettrodomestico_monitor.coordinator import (
    ElettrodomesticoCoordinator,
)
from custom_components.elettrodomestico_monitor.irrigation_coordinator import (
    IrrigationCoordinator,
)
from custom_components.elettrodomestico_monitor.presets import get_preset


def _make_appliance_entry(hass, preset="elettrodomestico", instance_id="sens_test", **extra):
    data = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_INSTANCE_ID: instance_id,
        CONF_SLOT: "1",
        CONF_PRESET: preset,
        "power_sensor": "sensor.power_test",
        **extra,
    }
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=instance_id)
    entry.add_to_hass(hass)
    return entry


def _assert_total_increasing(entity, label):
    """I sensori che si azzerano a un rollover periodico o a un reset
    DEVONO essere TOTAL_INCREASING — mai TOTAL — altrimenti HA registra
    il calo come dato reale invece che come reset del contatore."""
    assert entity._attr_state_class == SensorStateClass.TOTAL_INCREASING, (
        f"{label}: state_class={entity._attr_state_class!r}, atteso "
        "TOTAL_INCREASING (il valore si azzera a un rollover periodico o al reset)"
    )


# ── Elettrodomestico: sensori periodo/totale ──────────────────────────────────

async def test_acc_total_is_total_increasing(hass):
    """kWh Totale si azzera con 'Reset Contatori' (coordinator.async_reset_all)."""
    entry  = _make_appliance_entry(hass)
    coord  = ElettrodomesticoCoordinator(hass, entry)
    preset = get_preset("elettrodomestico")
    dc     = sensor_mod._DC_MAP.get(preset.device_class)
    ent = sensor_mod._AccTotal(coord, entry, "Test", "1", preset, dc)
    _assert_total_increasing(ent, "_AccTotal (kWh Totale)")


async def test_volume_m3_is_total_increasing(hass):
    entry  = _make_appliance_entry(hass, preset="acqua", instance_id="sens_vol")
    coord  = ElettrodomesticoCoordinator(hass, entry)
    preset = get_preset("acqua")
    ent = sensor_mod._VolumeM3(coord, entry, "Acqua Test", "1", preset)
    _assert_total_increasing(ent, "_VolumeM3")


async def test_energy_period_sensors_are_total_increasing(hass):
    """energy_oggi/mese/anno si azzerano a mezzanotte/mese/anno."""
    entry  = _make_appliance_entry(hass, instance_id="sens_energy")
    coord  = ElettrodomesticoCoordinator(hass, entry)
    preset = get_preset("elettrodomestico")
    dc     = sensor_mod._DC_MAP.get(preset.device_class)
    for period, sfx, dk, lk in (
        ("oggi", "energy_oggi_elettrodomestici", "energy_today", "energy_yesterday"),
        ("mese", "energy_mese_elettrodomestici", "energy_month", "energy_last_month"),
        ("anno", "energy_anno_elettrodomestici", "energy_year",  "energy_last_year"),
    ):
        ent = sensor_mod._EnergyPeriod(coord, entry, "Test", "1", preset, dc, period, sfx, dk, lk)
        _assert_total_increasing(ent, f"_EnergyPeriod ({period})")


async def test_cicli_period_is_total_increasing(hass):
    entry  = _make_appliance_entry(hass, instance_id="sens_cost")
    coord  = ElettrodomesticoCoordinator(hass, entry)

    cicli = sensor_mod._CicliPeriod(
        coord, entry, "Test", "1", "oggi",
        "cicli_oggi_elettrodomestici", "cycles_today", "cycles_yesterday")
    _assert_total_increasing(cicli, "_CicliPeriod (oggi)")


def _assert_no_state_class(entity, label):
    """I sensori di costo in € (accumulo_fisico × tariffa, che può essere
    dinamica) NON possono avere state_class:
    - device_class MONETARY non ammette 'total_increasing' in nessun caso
      (HA: "is using state class 'total_increasing' which is impossible
      considering device class ('monetary')...").
    - il valore non è garantito monotono nemmeno con 'total': con una
      tariffa dinamica può scendere anche a metà periodo, senza alcun
      reset (confermato in produzione: HA logga "state is not strictly
      increasing" per un calo avvenuto in pieno giorno, non a mezzanotte).
    'None' è la scelta sicura raccomandata da HA per un valore non
    garantito monotono (developers.home-assistant.io/docs/core/entity/sensor)."""
    assert entity._attr_state_class is None, (
        f"{label}: state_class={entity._attr_state_class!r}, atteso None "
        "(costo in € = accumulo × tariffa, non garantito monotono)"
    )


async def test_cost_and_solar_saving_sensors_have_no_state_class(hass):
    """FIX (v7.0.1): la 7.0.0 aveva messo questi sensori a TOTAL_INCREASING
    insieme ai contatori fisici — sbagliato, vedi _assert_no_state_class.
    Regressione confermata dai log reali dell'utente entro un'ora dal
    deploy della 7.0.0 (errori di validazione HA per _CostoRete, dovuti al
    device_class MONETARY, più warning runtime "not strictly increasing")."""
    entry  = _make_appliance_entry(hass, instance_id="sens_cost")
    coord  = ElettrodomesticoCoordinator(hass, entry)
    preset = get_preset("elettrodomestico")

    costo = sensor_mod._CostoPeriod(
        coord, entry, "Test", "1", "oggi",
        "costo_oggi_elettrodomestici", "costo_oggi", "costo_ieri", preset)
    _assert_no_state_class(costo, "_CostoPeriod (oggi)")

    sole = sensor_mod._RisparmioSole(coord, entry, "Test", "1", "oggi", "risparmio_sole_oggi")
    _assert_no_state_class(sole, "_RisparmioSole (oggi)")

    rete = sensor_mod._CostoRete(coord, entry, "Test", "1", "oggi", "costo_rete_oggi")
    _assert_no_state_class(rete, "_CostoRete (oggi)")
    # device_class MONETARY invece resta corretto da tenere (solo lo
    # state_class è incompatibile, non il device_class in sé).
    from homeassistant.components.sensor import SensorDeviceClass
    assert rete._attr_device_class == SensorDeviceClass.MONETARY


async def test_cicli_totali_is_total_increasing_for_contrast(hass):
    """Contrasto: il contatore a vita NON si azzera mai (tranne al reset
    esplicito) — era già corretto prima dell'audit, deve restarlo."""
    entry = _make_appliance_entry(hass, instance_id="sens_tot")
    coord = ElettrodomesticoCoordinator(hass, entry)
    ent = sensor_mod._CicliTotal(coord, entry, "Test", "1")
    _assert_total_increasing(ent, "_CicliTotal")


async def test_device_charge_cycle_sensors_are_total_increasing_for_every_period(hass):
    """FIX (audit v7.0.0): prima solo period=='totali' era TOTAL_INCREASING;
    oggi/mese/anno (che SI azzerano ai rollover) erano rimasti TOTAL."""
    entry = _make_appliance_entry(hass, preset="batteria", instance_id="sens_dev")
    coord = ElettrodomesticoCoordinator(hass, entry)
    for period, dk in (
        ("oggi", "ricariche_oggi"), ("mese", "ricariche_mese"),
        ("anno", "ricariche_anno"), ("totali", "ricariche_totali"),
    ):
        ent = sensor_mod._DevCicli(coord, entry, "Test", "1", period, dk)
        _assert_total_increasing(ent, f"_DevCicli ({period})")


async def test_vacuum_battery_sensor_falls_back_to_zero_not_none(hass):
    """FIX (audit v7.0.0): 'val if val is not None else None' non faceva
    nulla — il fallback a 0 promesso dal commento non era mai applicato, e
    il sensore restava 'unknown' invece di mostrare un valore noto."""
    entry = _make_appliance_entry(hass, preset="vacuum", instance_id="sens_vacbat")
    coord = ElettrodomesticoCoordinator(hass, entry)
    ent = sensor_mod._VacuumBattery(coord, entry, "Vacuum Test", "1")

    class _FakeCoord:
        data = {"is_vacuum": True}  # vacuum_battery assente dal dizionario

    ent.coordinator = _FakeCoord()
    assert ent.native_value == 0


# ── Irrigazione: sensori periodo (classi annidate in _async_setup_irrigation_sensors) ──

def _capture():
    captured: list = []

    def _add(entities, update_before_add=False):
        captured.extend(entities)

    return captured, _add


async def test_irrigation_period_sensors_are_total_increasing(hass):
    """I sensori FISICI litri/cicli/kWh oggi-mese-anno dell'irrigazione si
    azzerano a mezzanotte/mese/anno via irrigation_coordinator._midnight()
    e sono genuinamente monotoni (solo somme di delta reali >= 0), quindi
    DEVONO essere TOTAL_INCREASING. I sensori di COSTO (€) sono verificati
    a parte in test_irrigation_cost_sensors_have_no_state_class — non sono
    monotoni allo stesso modo (accumulo × tariffa, vedi
    test_cost_and_solar_saving_sensors_have_no_state_class in questo file).
    Queste classi sono definite come nested class dentro
    _async_setup_irrigation_sensors, quindi il modo realistico di
    verificarle è passare dalla funzione di setup reale."""
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_IRRIGATION,
        "entry_type": "irrigation",
        CONF_INSTANCE_ID: "irr_sens_test",
        CONF_SLOT: "1",
        "appliance_name": "Irrigazione Test",
    }, title="Irrigazione Test")
    entry.add_to_hass(hass)
    coord = IrrigationCoordinator(hass, entry)

    captured, add_entities = _capture()
    await sensor_mod._async_setup_irrigation_sensors(hass, entry, coord, add_entities)
    by_id = {e.entity_id: e for e in captured}

    period_sensors = (
        "sensor.irrigazione_litri_oggi_x1",
        "sensor.irrigazione_litri_mese_x1",
        "sensor.irrigazione_litri_anno_x1",
        "sensor.irrigazione_cicli_oggi_x1",
        "sensor.irrigazione_cicli_mese_x1",
        "sensor.irrigazione_cicli_anno_x1",
        "sensor.irrigazione_kwh_oggi_x1",
    )
    for eid in period_sensors:
        assert eid in by_id, f"sensore {eid} non trovato tra le entità create dal setup irrigazione"
        ent = by_id[eid]
        assert ent._attr_state_class == SensorStateClass.TOTAL_INCREASING, (
            f"{eid}: state_class={ent._attr_state_class!r}, atteso TOTAL_INCREASING "
            "(si azzera a mezzanotte/mese/anno)"
        )

    # Contrasto: gli accumulatori a vita restano TOTAL_INCREASING (già corretti prima dell'audit)
    for eid in ("sensor.irrigazione_litri_totale_x1", "sensor.irrigazione_kwh_totale_x1"):
        assert by_id[eid]._attr_state_class == SensorStateClass.TOTAL_INCREASING


async def test_irrigation_cost_sensors_have_no_state_class(hass):
    """FIX (v7.0.1): i sensori di costo dell'irrigazione (_IrrCosto —
    acqua/kwh/rete/sole/tot) hanno tutti device_class MONETARY e un valore
    = accumulo × tariffa del Hub (può essere dinamica) — stessa
    regressione reale di _CostoRete/_CostoPeriod, vedi
    test_cost_and_solar_saving_sensors_have_no_state_class."""
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ENTRY_TYPE: ENTRY_TYPE_IRRIGATION,
        "entry_type": "irrigation",
        CONF_INSTANCE_ID: "irr_sens_cost_test",
        CONF_SLOT: "2",
        "appliance_name": "Irrigazione Costo Test",
    }, title="Irrigazione Costo Test")
    entry.add_to_hass(hass)
    coord = IrrigationCoordinator(hass, entry)

    captured, add_entities = _capture()
    await sensor_mod._async_setup_irrigation_sensors(hass, entry, coord, add_entities)
    by_id = {e.entity_id: e for e in captured}

    for eid in (
        "sensor.irrigazione_costo_acqua_oggi_x2",
        "sensor.irrigazione_costo_kwh_oggi_x2",
        "sensor.irrigazione_costo_rete_oggi_x2",
        "sensor.irrigazione_costo_sole_oggi_x2",
        "sensor.irrigazione_costo_tot_oggi_x2",
    ):
        assert eid in by_id, f"sensore {eid} non trovato tra le entità create dal setup irrigazione"
        assert by_id[eid]._attr_state_class is None, (
            f"{eid}: state_class={by_id[eid]._attr_state_class!r}, atteso None"
        )
