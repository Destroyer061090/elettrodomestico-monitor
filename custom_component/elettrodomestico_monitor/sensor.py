# ============================================================
# FILE:    sensor.py
# VERSION: 5.8.10
# DESC:    Sensor platform — all sensors including irrigation sensors
# CHANGED: 2026-06-11
# ============================================================
"""Sensor platform for Elettrodomestico Monitor v6.

All entity names and device_class adapt to the preset.
"""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass, SensorEntity, SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .naming import unique_id, entity_suffix, slot_token, build_eids
from .const import (
    DOMAIN, CONF_APPLIANCE_NAME, CONF_INSTANCE_ID, CONF_SLOT, CONF_PRESET,
    WEEK_DAYS, WEEK_DAYS_EN,
    SFX_POWER, SFX_KWH, SFX_VOLUME_M3, SFX_MASTER, SFX_STATUS, SFX_VERSION,
    SFX_ENERGY_TODAY, SFX_ENERGY_MONTH, SFX_ENERGY_YEAR,
    SFX_CICLI_TODAY, SFX_CICLI_MONTH, SFX_CICLI_YEAR, SFX_CICLI_TOTAL,
    SFX_TEMPO_TODAY, SFX_TEMPO_MONTH, SFX_TEMPO_YEAR,
    SFX_COSTO_TODAY, SFX_COSTO_MONTH, SFX_COSTO_YEAR,
    SFX_LAST_CYCLE, SFX_WEEK_PREFIX, SFX_UPDATE, SFX_SCHEDULE, SFX_COSTO_SENSOR, SFX_VACUUM_BATTERY, SFX_DEVICE_BATTERY,
    ATTR_TERMINATO, ATTR_MANUTENZIONE, ATTR_TEMPO_CICLO,
    ATTR_OGGI, ATTR_MESE, ATTR_ANNO,
    ATTR_IERI, ATTR_MESE_PRECEDENTE, ATTR_ANNO_PRECEDENTE,
    ATTR_CONSUMO_CICLO, ATTR_COSTO_CICLO,
    ATTR_COSTO_GIORNALIERO, ATTR_COSTO_MENSILE, ATTR_COSTO_ANNUALE,
    ATTR_COSTO_IERI, ATTR_COSTO_MESE_PREC, ATTR_COSTO_ANNO_PREC,
    ATTR_CICLI_OGGI, ATTR_CICLI_MESE, ATTR_CICLI_ANNO,
    ATTR_WEEKLY_STATS, ATTR_VERSION, ATTR_LAST_RESET, ATTR_COSTO_FONTE, ATTR_PRESET,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
    VERSION,
)
from .coordinator import ElettrodomesticoCoordinator
from .presets import get_preset
from .update_coordinator import UpdateCheckCoordinator

_LOGGER = logging.getLogger(__name__)

# ── HA device_class mapping ───────────────────────────────────────────────────
_DC_MAP = {
    "energy": SensorDeviceClass.ENERGY,
    "water":  SensorDeviceClass.WATER,
    "gas":    SensorDeviceClass.GAS,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        upd = hass.data[DOMAIN].get("update_coordinator")
        if upd:
            async_add_entities([_UpdateSensor(upd, entry)])
        return

    # ── Irrigation device ──────────────────────────────────────────────────
    try:
        from .const import ENTRY_TYPE_IRRIGATION
        if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or
                entry.data.get("entry_type") == "irrigation"):
            coord = hass.data[DOMAIN][entry.entry_id]
            await _async_setup_irrigation_sensors(hass, entry, coord, async_add_entities)
            return
    except (ImportError, KeyError):
        pass

    # ── Battery Device ─────────────────────────────────────────────────────
    try:
        from .const import ENTRY_TYPE_DEVICE
        if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or
                entry.data.get("entry_type") == "device"):
            coord = hass.data[DOMAIN][entry.entry_id]
            await _async_setup_device_sensors(hass, entry, coord, async_add_entities)
            return
    except (ImportError, KeyError):
        pass

    coord: ElettrodomesticoCoordinator = hass.data[DOMAIN][entry.entry_id]
    name    = entry.data.get(CONF_APPLIANCE_NAME, "Device")
    slot    = str(entry.data.get(CONF_SLOT, "1"))
    preset  = get_preset(entry.data.get(CONF_PRESET, "elettrodomestico"))
    dc      = _DC_MAP.get(preset.device_class, SensorDeviceClass.ENERGY)

    entities: list = [
        _Power(coord, entry, name, slot, preset),
        _AccTotal(coord, entry, name, slot, preset, dc),
        _EnergyPeriod(coord, entry, name, slot, preset, dc, "oggi",  SFX_ENERGY_TODAY,  "energy_today",  "energy_yesterday"),
        _EnergyPeriod(coord, entry, name, slot, preset, dc, "mese",  SFX_ENERGY_MONTH,  "energy_month",  "energy_last_month"),
        _EnergyPeriod(coord, entry, name, slot, preset, dc, "anno",  SFX_ENERGY_YEAR,   "energy_year",   "energy_last_year"),
        _CicliPeriod(coord, entry, name, slot, "oggi", SFX_CICLI_TODAY, "cycles_today",  "cycles_yesterday"),
        _CicliPeriod(coord, entry, name, slot, "mese", SFX_CICLI_MONTH, "cycles_month",  "cycles_last_month"),
        _CicliPeriod(coord, entry, name, slot, "anno", SFX_CICLI_YEAR,  "cycles_year",   "cycles_last_year"),
        _CicliTotal(coord, entry, name, slot),
        _TempoPeriod(coord, entry, name, slot, "oggi", SFX_TEMPO_TODAY, "time_today_str",  "time_yesterday_str"),
        _TempoPeriod(coord, entry, name, slot, "mese", SFX_TEMPO_MONTH, "time_month_str",  "time_last_month_str"),
        _TempoPeriod(coord, entry, name, slot, "anno", SFX_TEMPO_YEAR,  "time_year_str",   "time_last_year_str"),
        _UltimoCiclo(coord, entry, name, slot, preset),
        _Schedule(coord, entry, name, slot),
        _Master(coord, entry, name, slot),
        _Stato(coord, entry, name, slot),
        _Versione(coord, entry, name, slot),
        _CostoEnergia(coord, entry, name, slot),
    ]
    # Battery sensors: only for their respective presets
    if entry.data.get(CONF_PRESET) == "vacuum":
        entities.append(_VacuumBattery(coord, entry, name, slot))
    if entry.data.get(CONF_PRESET) == "batteria":
        entities.append(_DeviceBattery(coord, entry, name, slot))

    # Cost sensors only for presets with show_cost
    if preset.show_cost:
        entities += [
            _CostoPeriod(coord, entry, name, slot, "oggi", SFX_COSTO_TODAY, "costo_oggi", "costo_ieri",      preset),
            _CostoPeriod(coord, entry, name, slot, "mese", SFX_COSTO_MONTH, "costo_mese", "costo_mese_prec", preset),
            _CostoPeriod(coord, entry, name, slot, "anno", SFX_COSTO_YEAR,  "costo_anno", "costo_anno_prec", preset),
        ]
        # FV: solar saving sensors (€ saved by self-consumption). Always created;
        # they read 0 when FV is disabled, and populate when the hub FV mode is on.
        entities += [
            _RisparmioSole(coord, entry, name, slot, "oggi", "risparmio_sole_oggi"),
            _RisparmioSole(coord, entry, name, slot, "mese", "risparmio_sole_mese"),
            _RisparmioSole(coord, entry, name, slot, "anno", "risparmio_sole_anno"),
            _CostoRete(coord, entry, name, slot, "oggi", "costo_rete_oggi"),
            _CostoRete(coord, entry, name, slot, "mese", "costo_rete_mese"),
            _CostoRete(coord, entry, name, slot, "anno", "costo_rete_anno"),
        ]

    # m³ sensor for Acqua/Gas
    if preset.has_volume_m3:
        entities.append(_VolumeM3(coord, entry, name, slot, preset))

    # 7 weekly sensors
    for day_it, day_en in zip(WEEK_DAYS, WEEK_DAYS_EN):
        entities.append(_WeekDay(coord, entry, name, slot, day_it, preset))

    async_add_entities(entities)


async def _async_setup_irrigation_sensors(
    hass, entry, coord, async_add_entities
) -> None:
    """Create sensors for irrigation device."""
    from .irrigation_coordinator import IrrigationCoordinator
    from homeassistant.helpers.entity import DeviceInfo

    name  = entry.data.get("appliance_name", "Irrigazione")
    slot  = str(entry.data.get("slot", "1"))
    iid   = entry.data.get("instance_id", "irr")
    DOMAIN_LOCAL = "elettrodomestico_monitor"

    dev_info = DeviceInfo(
        identifiers={(DOMAIN_LOCAL, iid)},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Irrigazione",
        sw_version="4.49",
        configuration_url="https://github.com/Destroyer061090/elettrodomestico-monitor",
    )

    class _IrrBase(CoordinatorEntity, SensorEntity):
        def __init__(self, sfx):
            super().__init__(coord)
            self._attr_device_info = dev_info
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_{sfx}_x{slot}"
            self.entity_id         = f"sensor.{sfx}_x{slot}"
        @property
        def _d(self): return self.coordinator.data or {}

    class _FlowSensor(_IrrBase):
        def __init__(self):
            super().__init__("irrigazione_portata")
            self._attr_name = f"Portata {name}"
            self._attr_native_unit_of_measurement = "L/min"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:water-flow"
        @property
        def native_value(self): return self._d.get("flow_lmin", 0.0)

    class _LitreSensor(_IrrBase):
        def __init__(self, period, sfx_it, lbl):
            super().__init__(f"irrigazione_litri_{sfx_it}")
            self._key = f"l_{period}"
            self._attr_name = f"{lbl} {name}"
            self._attr_native_unit_of_measurement = "L"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_icon = "mdi:water"
        @property
        def native_value(self): return self._d.get(self._key, 0.0)

    class _IrrCicli(_IrrBase):
        """Dedicated cycle-count sensor (oggi/mese/anno) — clickable history."""
        def __init__(self, period, sfx_it, lbl):
            super().__init__(f"irrigazione_cicli_{sfx_it}")
            self._key = f"c_{period}"
            self._attr_name = f"Cicli {lbl} {name}"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_icon = "mdi:counter"
        @property
        def native_value(self): return self._d.get(self._key, 0)

    class _IrrCosto(_IrrBase):
        """Dedicated cost sensor (€) for irrigation — clickable history.
        kind: acqua | kwh | rete | sole."""
        def __init__(self, kind, period, sfx_it, lbl):
            super().__init__(f"irrigazione_costo_{kind}_{sfx_it}")
            self._key = {
                "acqua": f"costo_acqua_{period}",
                "kwh":   f"costo_kwh_{period}",
                "rete":  f"costo_rete_{period}",
                "sole":  f"risparmio_sole_{period}",
                "tot":   f"costo_tot_{period}",
            }[kind]
            self._attr_name = f"Costo {lbl} {sfx_it} {name}"
            self._attr_native_unit_of_measurement = "€"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_icon = "mdi:currency-eur"
        @property
        def native_value(self): return round(float(self._d.get(self._key, 0.0)), 2)

    class _CountdownSensor(_IrrBase):
        def __init__(self):
            super().__init__("irrigazione_countdown")
            self._attr_name = f"Countdown {name}"
            self._attr_native_unit_of_measurement = "s"
            self._attr_icon = "mdi:timer"
        @property
        def native_value(self): return self._d.get("countdown_s", 0)

    class _ZonaSensor(_IrrBase):
        def __init__(self):
            super().__init__("irrigazione_zona_attiva")
            self._attr_name = f"Zona Attiva {name}"
            self._attr_icon = "mdi:sprinkler"
        @property
        def native_value(self): return self._d.get("active_zone_name") or "—"

    class _MasterSensor(_IrrBase):
        """Master sensor with all attributes for 7 days and stats."""
        def __init__(self):
            super().__init__("irrigazione_time_on")
            self._attr_name = f"Statistiche {name}"
            self._attr_native_unit_of_measurement = "h"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:chart-bar"
        @property
        def native_value(self):
            return round(self._d.get("t_today", 0.0), 3)
        @property
        def extra_state_attributes(self):
            d = self._d
            return {
                "cicli_oggi":    d.get("c_today", 0),
                "cicli_mese":    d.get("c_month", 0),
                "cicli_anno":    d.get("c_year",  0),
                "litri_oggi":    d.get("l_today",  0.0),
                "litri_mese":    d.get("l_month",  0.0),
                "litri_anno":    d.get("l_year",   0.0),
                "kwh_oggi":      d.get("kwh_today",  0.0),
                "kwh_mese":      d.get("kwh_month",  0.0),
                "kwh_anno":      d.get("kwh_year",   0.0),
                "tempo_oggi":    d.get("t_today_str", "0min"),
                "tempo_mese":    d.get("t_month_str", "0min"),
                "tempo_anno":    d.get("t_year_str",  "0min"),
                "ciclo_attivo":  d.get("cycle_active", False),
                "zona_attiva":   d.get("active_zone_name", ""),
                "image_on":      d.get("image_on", ""),
                "image_off":     d.get("image_off", ""),
                "zona_ultima":   (
                    f'{d.get("last_zone_name", "")} ({d.get("last_zone_time", "")})'
                    if d.get("last_zone_name") else "—"
                ),
                "zona_ultima_ora": d.get("last_zone_time", ""),
                "countdown_s":   d.get("countdown_s", 0),
                "zone":          d.get("zones", []),
                "zone_order":    d.get("zone_order", []),
                # Cost attributes (computed by irrigation_coordinator._build())
                "costo_kwh_oggi":   d.get("costo_kwh_oggi",   0.0),
                "costo_kwh_mese":   d.get("costo_kwh_mese",   0.0),
                "costo_kwh_anno":   d.get("costo_kwh_anno",   0.0),
                "costo_acqua_oggi": d.get("costo_acqua_oggi", 0.0),
                "costo_acqua_mese": d.get("costo_acqua_mese", 0.0),
                "costo_acqua_anno": d.get("costo_acqua_anno", 0.0),
                "fv_enabled":          d.get("fv_enabled", False),
                "costo_rete_oggi":     d.get("costo_rete_oggi", 0.0),
                "costo_rete_mese":     d.get("costo_rete_mese", 0.0),
                "costo_rete_anno":     d.get("costo_rete_anno", 0.0),
                "risparmio_sole_oggi": d.get("risparmio_sole_oggi", 0.0),
                "risparmio_sole_mese": d.get("risparmio_sole_mese", 0.0),
                "risparmio_sole_anno": d.get("risparmio_sole_anno", 0.0),
                "costo_rete_ieri":       d.get("costo_rete_ieri",      0.0),
                "costo_rete_mese_prec":  d.get("costo_rete_mese_prec", 0.0),
                "costo_rete_anno_prec":  d.get("costo_rete_anno_prec", 0.0),
                "risparmio_sole_ieri":      d.get("risparmio_sole_ieri",      0.0),
                "risparmio_sole_mese_prec": d.get("risparmio_sole_mese_prec", 0.0),
                "risparmio_sole_anno_prec": d.get("risparmio_sole_anno_prec", 0.0),
                "statistiche_settimanali": d.get("weekly", {}),
                "eids":            build_eids(slot, irrigation=True),
                "l_ieri":          d.get("l_yesterday", 0.0),
                "kwh_ieri":        d.get("kwh_yesterday", 0.0),
                "tempo_ieri":      d.get("t_yesterday_str", "0min"),
                "cicli_ieri":      d.get("c_yesterday", 0),
                "costo_acqua_ieri": d.get("costo_acqua_ieri", 0.0),
                "costo_kwh_ieri":   d.get("costo_kwh_ieri", 0.0),
                "l_mese_prec":     d.get("l_last_month", 0.0),
                "kwh_mese_prec":   d.get("kwh_last_month", 0.0),
                "tempo_mese_prec": d.get("t_last_month_str", "0min"),
                "cicli_mese_prec": d.get("c_last_month", 0),
                "costo_acqua_mese_prec": d.get("costo_acqua_mese_prec", 0.0),
                "costo_kwh_mese_prec":   d.get("costo_kwh_mese_prec", 0.0),
                "l_anno_prec":     d.get("l_last_year", 0.0),
                "kwh_anno_prec":   d.get("kwh_last_year", 0.0),
                "tempo_anno_prec": d.get("t_last_year_str", "0min"),
                "cicli_anno_prec": d.get("c_last_year", 0),
                "costo_acqua_anno_prec": d.get("costo_acqua_anno_prec", 0.0),
                "costo_kwh_anno_prec":   d.get("costo_kwh_anno_prec", 0.0),
                "real_zone_switches": d.get("real_zone_switches", []),
                "flow_sensor_eid":    d.get("flow_sensor_eid",    ""),
                "pump_sensor_eid":    d.get("pump_sensor_eid",    ""),
                "versione":      d.get("version", ""),
                "manutenzione":  d.get("maintenance_date", ""),
                "ultimo_reset":  d.get("reset_date", ""),
                "notifiche_inizio": d.get("notify_window_start", "08:00:00")[:5],
                "notifiche_fine":   d.get("notify_window_end",   "22:00:00")[:5],
            }

    class _KWhSensor(_IrrBase):
        def __init__(self, period, sfx_it, lbl):
            super().__init__(f"irrigazione_kwh_{sfx_it}")
            self._key = f"kwh_{period}"
            self._attr_name = f"{lbl} {name}"
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_state_class = SensorStateClass.TOTAL
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_icon = "mdi:lightning-bolt"
        @property
        def native_value(self): return self._d.get(self._key, 0.0)

    class _LitriTotaleSensor(_IrrBase):
        """Ever-increasing total litres — compatible with HA's Energy dashboard
        (water). Reads the l_total accumulator already maintained by the
        coordinator."""
        def __init__(self):
            super().__init__("irrigazione_litri_totale")
            self._attr_name = f"Litri Totale {name}"
            self._attr_native_unit_of_measurement = "L"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.WATER
            self._attr_icon = "mdi:water-circle"
        @property
        def native_value(self): return self._d.get("l_total", 0.0)

    class _KWhTotaleSensor(_IrrBase):
        """Ever-increasing total pump energy — compatible with HA's Energy
        dashboard (energy). Reads the kwh_total accumulator."""
        def __init__(self):
            super().__init__("irrigazione_kwh_totale")
            self._attr_name = f"Consumo Pompa Totale {name}"
            self._attr_native_unit_of_measurement = "kWh"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_icon = "mdi:lightning-bolt-circle"
        @property
        def native_value(self): return self._d.get("kwh_total", 0.0)

    class _PumpSensor(_IrrBase):
        def __init__(self):
            super().__init__("irrigazione_pompa_w")
            self._attr_name = f"Potenza Pompa {name}"
            self._attr_native_unit_of_measurement = "W"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.POWER
            self._attr_icon = "mdi:water-pump"
        @property
        def native_value(self): return self._d.get("pump_w", 0.0)

    WEEK_DAYS_IRR = ["lunedi","martedi","mercoledi","giovedi","venerdi","sabato","domenica"]

    class _WeekDaySensor(_IrrBase):
        """Daily stat sensor matching SFX_WEEK_PREFIX naming for JS card compatibility."""
        def __init__(self, day: str):
            super().__init__(f"settimana_{day}_elettrodomestici")
            self._day = day
            self._attr_name = day.capitalize()
            self._attr_native_unit_of_measurement = "L"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:calendar-today"
        @property
        def native_value(self):
            weekly = self._d.get("weekly", {})
            return float(weekly.get(self._day, {}).get("litri", 0.0))
        @property
        def extra_state_attributes(self):
            weekly = self._d.get("weekly", {})
            day_data = weekly.get(self._day, {})
            return {
                "cicli": day_data.get("cicli", "0"),
                "tempo": day_data.get("tempo", "0min"),
                "litri": float(day_data.get("litri", 0.0)),
                "kwh":   float(day_data.get("kwh", 0.0)),
                "costo_acqua": float(day_data.get("costo_acqua", 0.0)),
                "costo_kwh":   float(day_data.get("costo_kwh", 0.0)),
            }

    irr_entities = [
        _FlowSensor(),
        _PumpSensor(),
        _LitreSensor("today", "oggi",   "Litri Oggi"),
        _LitreSensor("month", "mese",   "Litri Mese"),
        _LitreSensor("year",  "anno",   "Litri Anno"),
        _KWhSensor("today", "oggi",  "kWh Oggi"),
        _KWhSensor("month", "mese",  "kWh Mese"),
        _KWhSensor("year",  "anno",  "kWh Anno"),
        _LitriTotaleSensor(),
        _KWhTotaleSensor(),
        _IrrCicli("today", "oggi", "Oggi"),
        _IrrCicli("month", "mese", "Mese"),
        _IrrCicli("year",  "anno", "Anno"),
        _IrrCosto("acqua", "today", "oggi", "Acqua"),
        _IrrCosto("acqua", "month", "mese", "Acqua"),
        _IrrCosto("acqua", "year",  "anno", "Acqua"),
        _IrrCosto("kwh", "today", "oggi", "Pompa"),
        _IrrCosto("kwh", "month", "mese", "Pompa"),
        _IrrCosto("kwh", "year",  "anno", "Pompa"),
        _IrrCosto("rete", "today", "oggi", "Rete"),
        _IrrCosto("rete", "month", "mese", "Rete"),
        _IrrCosto("rete", "year",  "anno", "Rete"),
        _IrrCosto("sole", "today", "oggi", "Sole"),
        _IrrCosto("sole", "month", "mese", "Sole"),
        _IrrCosto("sole", "year",  "anno", "Sole"),
        _IrrCosto("tot", "today", "oggi", "Totale"),
        _IrrCosto("tot", "month", "mese", "Totale"),
        _IrrCosto("tot", "year",  "anno", "Totale"),
        _CountdownSensor(),
        _ZonaSensor(),
        _MasterSensor(),
    ] + [_WeekDaySensor(d) for d in WEEK_DAYS_IRR]
    async_add_entities(irr_entities)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _async_setup_device_sensors(hass, entry, coord, async_add_entities):
    name = entry.data.get(CONF_APPLIANCE_NAME, "Dispositivo")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    async_add_entities([
        _DevBattery(coord, entry, name, slot),
        _DevCicli(coord, entry, name, slot, "oggi", "ricariche_oggi"),
        _DevCicli(coord, entry, name, slot, "mese", "ricariche_mese"),
        _DevCicli(coord, entry, name, slot, "anno", "ricariche_anno"),
        _DevCicli(coord, entry, name, slot, "totali", "ricariche_totali"),
    ])


def _device_dev(entry, name):
    icon = entry.data.get("device_icon", "mdi:battery-charging")
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Dispositivi",
        sw_version=VERSION,
    )


class _DevBase(CoordinatorEntity, SensorEntity):
    def __init__(self, coord, entry, name, slot, sfx):
        super().__init__(coord)
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id   = f"{DOMAIN}_{iid}_{sfx}_x{slot}"
        self.entity_id         = f"sensor.{sfx}_x{slot}"
        self._attr_device_info = _device_dev(entry, name)
    @property
    def _d(self): return self.coordinator.data or {}


class _DevBattery(_DevBase):
    def __init__(self, coord, entry, name, slot):
        super().__init__(coord, entry, name, slot, "ricarica_dispositivo")
        self._attr_name = name
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
    @property
    def native_value(self): return self._d.get("battery_pct", 0)
    @property
    def extra_state_attributes(self):
        d = self._d
        return {
            "stato_carica":     d.get("stato_carica", ""),
            "tempo_in_carica":  d.get("tempo_in_carica", ""),
            "tempo_a_batteria": d.get("tempo_a_batteria", ""),
            "ricariche_oggi":   d.get("ricariche_oggi", 0),
            "ricariche_mese":   d.get("ricariche_mese", 0),
            "ricariche_anno":   d.get("ricariche_anno", 0),
            "ricariche_totali": d.get("ricariche_totali", 0),
            "ricariche_ieri":   d.get("ricariche_ieri", 0),
            "ricariche_mese_prec": d.get("ricariche_mese_prec", 0),
            "ricariche_anno_prec": d.get("ricariche_anno_prec", 0),
            "soglia_avvio":     d.get("soglia_avvio", 0),
            "soglia_stop":      d.get("soglia_stop", 0),
            "auto_attivo":      d.get("auto_attivo", False),
            "charge_switch_eid": d.get("charge_switch_eid", ""),
            "battery_sensor_eid": d.get("battery_sensor_eid", ""),
            "manutenzione":     d.get("maintenance_date", ""),
            "ultimo_reset":     d.get("reset_date", ""),
            "versione":         d.get("version", ""),
        }


class _DevCicli(_DevBase):
    def __init__(self, coord, entry, name, slot, period, dk):
        super().__init__(coord, entry, name, slot, f"cicli_ricarica_{period}")
        self._dk = dk
        self._attr_name = f"Cicli Ricarica {name} {period.capitalize()}"
        self._attr_native_unit_of_measurement = "cicli"
        self._attr_state_class = SensorStateClass.TOTAL if period != "totali" else SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:battery-sync"
    @property
    def native_value(self): return self._d.get(self._dk, 0)


def _uid(iid, sfx, slot): return unique_id(iid, sfx, slot)
def _eid(sfx, slot):      return entity_suffix(sfx, slot)

def _device(entry, name):
    icon = entry.data.get("device_icon", "mdi:washing-machine")
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Elettrodomestici",
        sw_version=VERSION,
        configuration_url="https://github.com/Destroyer061090/elettrodomestico-monitor",
    )

def _hub_device(entry):
    return DeviceInfo(
        identifiers={(DOMAIN, "hub")},
        name="Elettrodomestico Monitor Hub",
        manufacturer="Elettrodomestico Monitor",
        model="Hub Globale",
        sw_version=VERSION,
    )


class _Base(CoordinatorEntity, SensorEntity):
    def __init__(self, coord, entry, name, slot, sfx):
        super().__init__(coord)
        self._attr_unique_id   = _uid(entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))), sfx, slot)
        self.entity_id         = f"sensor.{_eid(sfx, slot)}"
        self._attr_device_info = _device(entry, name)

    @property
    def _d(self) -> dict[str, Any]: return self.coordinator.data or {}


# ── Power sensor ──────────────────────────────────────────────────────────────

class _Power(_Base):
    def __init__(self, c, e, n, s, preset):
        super().__init__(c, e, n, s, SFX_POWER)
        src_unit = e.data.get("source_unit", preset.source_unit)
        self._attr_name = f"Potenza {n} {src_unit}"
        self._attr_native_unit_of_measurement = src_unit
        # Use POWER device class only for W
        self._attr_device_class = SensorDeviceClass.POWER if src_unit == "W" else None
        self._attr_state_class  = SensorStateClass.MEASUREMENT
        self._attr_icon = e.data.get("device_icon", preset.default_icon)

    @property
    def native_value(self): return self._d.get("power_w", 0.0)


# ── Accumulated total (kWh / L / m³) ─────────────────────────────────────────

class _AccTotal(_Base):
    def __init__(self, c, e, n, s, preset, dc):
        super().__init__(c, e, n, s, SFX_KWH)
        total_unit = e.data.get("total_unit", preset.total_unit)
        lbl = preset.label_consumo
        self._attr_name = f"{lbl} Totale {n}"
        self._attr_native_unit_of_measurement = total_unit
        self._attr_device_class = dc
        self._attr_state_class  = SensorStateClass.TOTAL
        self._attr_icon = "mdi:lightning-bolt" if total_unit == "kWh" else "mdi:water" if total_unit == "L" else "mdi:gauge"

    @property
    def native_value(self): return self._d.get("acc_total", 0.0)


# ── Volume m³ (Acqua / Gas only) ──────────────────────────────────────────────

class _VolumeM3(_Base):
    def __init__(self, c, e, n, s, preset):
        super().__init__(c, e, n, s, SFX_VOLUME_M3)
        self._attr_name = f"Volume m³ {n}"
        self._attr_native_unit_of_measurement = "m³"
        self._attr_device_class = SensorDeviceClass.WATER if preset.device_class == "water" else SensorDeviceClass.GAS
        self._attr_state_class  = SensorStateClass.TOTAL
        self._attr_icon = "mdi:water-outline"

    @property
    def native_value(self): return self._d.get("volume_m3", 0.0)


# ── Period sensors ────────────────────────────────────────────────────────────

class _EnergyPeriod(_Base):
    def __init__(self, c, e, n, s, preset, dc, period, sfx, dk, lk):
        super().__init__(c, e, n, s, sfx)
        total_unit = e.data.get("total_unit", preset.total_unit)
        lbl = preset.label_consumo
        self._dk, self._lk = dk, lk
        self._attr_name = f"{lbl} {n} {period.capitalize()}"
        self._attr_native_unit_of_measurement = total_unit
        self._attr_device_class = dc
        self._attr_state_class  = SensorStateClass.TOTAL
        self._attr_icon = "mdi:lightning-bolt-circle"

    @property
    def native_value(self): return self._d.get(self._dk, 0.0)

    @property
    def extra_state_attributes(self):
        v   = self._d.get(self._dk, 0.0)
        cpp = self._d.get("cost_per_unit", 0.0)
        cf  = self._d.get("cost_factor", 1.0)
        return {
            "last_period":  self._d.get(self._lk, 0.0),
            "costo_eur":    round(v * cf * cpp, 2),
            "fonte_costo":  self._d.get("cost_source", "fisso"),
        }


class _CicliPeriod(_Base):
    def __init__(self, c, e, n, s, period, sfx, dk, lk):
        super().__init__(c, e, n, s, sfx)
        self._dk, self._lk = dk, lk
        self._attr_name = f"Cicli {n} {period.capitalize()}"
        self._attr_native_unit_of_measurement = "cicli"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self): return self._d.get(self._dk, 0)

    @property
    def extra_state_attributes(self): return {"last_period": self._d.get(self._lk, 0)}


class _CicliTotal(_Base):
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_CICLI_TOTAL)
        self._attr_name = f"Cicli Totali {n}"
        self._attr_native_unit_of_measurement = "cicli"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self): return self._d.get("total_cycles", 0)


class _TempoPeriod(_Base):
    def __init__(self, c, e, n, s, period, sfx, dk, lk):
        super().__init__(c, e, n, s, sfx)
        self._dk, self._lk = dk, lk
        self._attr_name = f"Tempo {n} {period.capitalize()}"
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> str: return self._d.get(self._dk, "0min")

    @property
    def extra_state_attributes(self):
        # Expose BOTH keys: 'last_period' (canonical, used by the card's
        # lastPeriod flag like cycles/energy) and 'periodo_precedente'
        # (backwards compatibility).
        lp = self._d.get(self._lk, "0min")
        return {"last_period": lp, "periodo_precedente": lp}


class _CostoPeriod(_Base):
    def __init__(self, c, e, n, s, period, sfx, dk, lk, preset):
        super().__init__(c, e, n, s, sfx)
        lbl = preset.label_costo
        self._dk, self._lk = dk, lk
        self._attr_name = f"{lbl} {n} {period.capitalize()}"
        self._attr_native_unit_of_measurement = "€"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:cash-plus" if not self._d.get("inverted_cost") else "mdi:solar-power"

    @property
    def native_value(self) -> float: return self._d.get(self._dk, 0.0)


class _RisparmioSole(_Base):
    """Solar self-consumption saving (€) for a period."""
    def __init__(self, c, e, n, s, period, dk):
        super().__init__(c, e, n, s, f"risparmio_sole_{period}")
        self._dk = dk
        self._attr_name = f"Risparmio Sole {n} {period.capitalize()}"
        self._attr_native_unit_of_measurement = "€"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_icon = "mdi:solar-power-variant"

    @property
    def native_value(self) -> float: return self._d.get(self._dk, 0.0)

    @property
    def extra_state_attributes(self):
        return {
            "fv_attivo":     self._d.get("fv_enabled", False),
            "energia_sole":  self._d.get("energia_sole_oggi", 0.0),
            "energia_rete":  self._d.get("energia_rete_oggi", 0.0),
        }


class _CostoRete(_Base):
    """Grid cost (€) for a period when FV is active — clickable history."""
    def __init__(self, c, e, n, s, period, dk):
        super().__init__(c, e, n, s, f"costo_rete_{period}")
        self._dk = dk
        self._attr_name = f"Costo Rete {n} {period.capitalize()}"
        self._attr_native_unit_of_measurement = "€"
        self._attr_state_class = SensorStateClass.TOTAL
        self._attr_device_class = SensorDeviceClass.MONETARY
        self._attr_icon = "mdi:transmission-tower"

    @property
    def native_value(self) -> float: return round(float(self._d.get(self._dk, 0.0)), 2)


# ── Ultimo ciclo ──────────────────────────────────────────────────────────────

class _UltimoCiclo(_Base):
    def __init__(self, c, e, n, s, preset):
        super().__init__(c, e, n, s, SFX_LAST_CYCLE)
        total_unit = e.data.get("total_unit", preset.total_unit)
        self._preset   = preset
        self._attr_name = f"Ultimo Ciclo {n}"
        self._attr_native_unit_of_measurement = total_unit
        dc = _DC_MAP.get(preset.device_class)
        self._attr_device_class = dc
        self._attr_icon = "mdi:history"

    @property
    def native_value(self) -> float: return self._d.get("consumo_ciclo", 0.0)

    @property
    def extra_state_attributes(self):
        d = self._d
        attrs = {
            "durata":           d.get("tempo_ciclo",    ""),
            "fine_ciclo":       d.get("terminato",      ""),
            "in_funzione":      d.get("cycle_active",   False),
            "kwh_inizio_ciclo": d.get("cycle_start_acc", 0.0),
            "fonte_costo":      d.get("cost_source",    "fisso"),
        }
        if self._preset.show_cost:
            attrs["costo_eur"] = d.get("costo_ciclo", 0.0)
        return attrs


# ── Schedule sensor ───────────────────────────────────────────────────────────

class _Schedule(_Base):
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_SCHEDULE)
        self._attr_name = f"Programma {n}"
        self._attr_icon = "mdi:clock-time-four-outline"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> str:
        # State represents the OFF time (spegnimento) to match the card's SPEGNIMENTO column
        off = self._d.get("schedule_auto_off", "00:00:00")
        try:
            h, m = int(off.split(":")[0]), int(off.split(":")[1])
        except (IndexError, ValueError):
            h = m = 0
        return "Disabilitato" if (h == 0 and m == 0) else off[:5]

    @property
    def extra_state_attributes(self):
        d = self._d
        def _disp(val):
            try:
                h, m = int(val.split(":")[0]), int(val.split(":")[1])
                return "Disabilitato" if (h == 0 and m == 0) else val[:5]
            except (IndexError, ValueError, AttributeError):
                return "Disabilitato"
        on  = d.get("schedule_auto_on",  "00:00:00")
        off = d.get("schedule_auto_off", "00:00:00")
        on_disp  = _disp(on)
        off_disp = _disp(off)
        # Notification window comes from the HUB (always set, default 08:00-22:00)
        nw_start = d.get("notify_window_start", "08:00:00")[:5]
        nw_end   = d.get("notify_window_end",   "22:00:00")[:5]
        attrs = {
            "accensione":      on_disp,
            "spegnimento":     off_disp,
            "notifiche_inizio": nw_start,
            "notifiche_fine":   nw_end,
            "sorgente":        d.get("schedule_source",   "hub"),
            "override_locale": d.get("schedule_override", False),
            "soglia_w":        d.get("threshold_w",       0),
            "delay_off_min":   d.get("delay_off_m",       0),
            "delay_on_sec":    d.get("delay_on_s",        0),
        }
        if d.get("use_trigger_entity"):
            attrs["trigger_entity"] = d.get("trigger_entity", "")
            attrs["trigger_stato"]  = d.get("trigger_state",  "")
        return attrs


# ── Weekly sensors (7 × per device) ──────────────────────────────────────────

class _WeekDay(_Base):
    def __init__(self, c, e, n, s, day_it, preset):
        sfx = f"{SFX_WEEK_PREFIX}_{day_it}_elettrodomestici"
        super().__init__(c, e, n, s, sfx)
        self._day_it = day_it
        self._preset = preset
        total_unit = e.data.get("total_unit", preset.total_unit)
        self._attr_name = f"{n} {day_it.capitalize()}"
        self._attr_native_unit_of_measurement = total_unit
        dc = _DC_MAP.get(preset.device_class)
        self._attr_device_class = dc
        self._attr_icon = "mdi:calendar-today"

    @property
    def native_value(self) -> float:
        w = self._d.get("weekly", {}).get(self._day_it, {})
        return float(w.get("consumo", 0.0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        w   = self._d.get("weekly", {}).get(self._day_it, {})
        cpp = self._d.get("cost_per_unit", 0.0)
        cf  = self._d.get("cost_factor", 1.0)
        kwh = float(w.get("consumo", 0.0))
        attrs = {
            "cicli":       w.get("cicli",  "0"),
            "tempo":       w.get("tempo",  "0min"),
            "consumo":     round(kwh, 3),
            "fonte_costo": self._d.get("cost_source", "fisso"),
        }
        if self._preset.show_cost:
            attrs["costo_eur"] = round(kwh * cf * cpp, 2)
        return attrs


# ── Master sensor ─────────────────────────────────────────────────────────────

class _Master(_Base):
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_MASTER)
        self._slot_val = s
        self._attr_name = f"Time On {n}"
        self._attr_native_unit_of_measurement = "h"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:history"

    @property
    def native_value(self) -> float:
        d = self._d
        if not d.get("ac_state") or not d.get("cycle_active"): return 0.0
        ts = self.coordinator.storage.get("cycle_start_ts", 0.0)
        if ts <= 0: return 0.0
        from homeassistant.util import dt as dt_util
        return round((dt_util.utcnow().timestamp() - ts) / 3600.0, 4)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self._d
        return {
            ATTR_TERMINATO:         d.get("terminato",          ""),
            ATTR_MANUTENZIONE:      d.get("maintenance_date",   ""),
            ATTR_TEMPO_CICLO:       d.get("tempo_ciclo",        ""),
            ATTR_OGGI:              d.get("time_today_str",     "0min"),
            ATTR_MESE:              d.get("time_month_str",     "0min"),
            ATTR_ANNO:              d.get("time_year_str",      "0min"),
            ATTR_IERI:              d.get("time_yesterday_str", "0min"),
            ATTR_MESE_PRECEDENTE:   d.get("time_last_month_str","0min"),
            ATTR_ANNO_PRECEDENTE:   d.get("time_last_year_str", "0min"),
            ATTR_CONSUMO_CICLO:     f"{d.get('consumo_ciclo',0.0)} {d.get('total_unit','kWh')}",
            ATTR_COSTO_CICLO:       d.get("costo_ciclo",        0.0),
            ATTR_COSTO_GIORNALIERO: d.get("costo_oggi",         0.0),
            ATTR_COSTO_MENSILE:     d.get("costo_mese",         0.0),
            ATTR_COSTO_ANNUALE:     d.get("costo_anno",         0.0),
            ATTR_COSTO_IERI:        d.get("costo_ieri",         0.0),
            ATTR_COSTO_MESE_PREC:   d.get("costo_mese_prec",   0.0),
            ATTR_COSTO_ANNO_PREC:   d.get("costo_anno_prec",   0.0),
            ATTR_CICLI_OGGI:        d.get("cycles_today",       0),
            ATTR_CICLI_MESE:        d.get("cycles_month",       0),
            ATTR_CICLI_ANNO:        d.get("cycles_year",        0),
            ATTR_WEEKLY_STATS:      d.get("weekly",             {}),
            ATTR_COSTO_FONTE:       d.get("cost_source",        "fisso"),
            "costo_per_unita":      d.get("cost_per_unit",      0.0),
            "unita_totale":         d.get("total_unit",         "kWh"),
            ATTR_PRESET:            d.get("preset_id",          ""),
            ATTR_VERSION:           d.get("version",            VERSION),
            ATTR_LAST_RESET:        d.get("reset_date",         ""),
            "programma_accensione": d.get("schedule_auto_on",  ""),
            "programma_spegnimento":d.get("schedule_auto_off", ""),
            "display_name":         d.get("display_name",      ""),
            "image_on":             d.get("image_on",          ""),
            "image_off":            d.get("image_off",         ""),
            "trigger_entity":       d.get("trigger_entity",    ""),
            "sensor_online":        d.get("sensor_online",     True),
            "switch_state":         d.get("switch_state",      None),
            "has_power_sensor":      d.get("has_power_sensor",  False),
            "source_unit":           d.get("source_unit",       "W"),
            "total_unit":            d.get("total_unit",        "kWh"),
            "fv_enabled":            d.get("fv_enabled",        False),
            "costo_rete_oggi":       d.get("costo_rete_oggi",   0.0),
            "costo_rete_mese":       d.get("costo_rete_mese",   0.0),
            "costo_rete_anno":       d.get("costo_rete_anno",   0.0),
            "risparmio_sole_oggi":   d.get("risparmio_sole_oggi", 0.0),
            "risparmio_sole_mese":   d.get("risparmio_sole_mese", 0.0),
            "risparmio_sole_anno":   d.get("risparmio_sole_anno", 0.0),
            "costo_rete_ieri":       d.get("costo_rete_ieri",      0.0),
            "costo_rete_mese_prec":  d.get("costo_rete_mese_prec", 0.0),
            "costo_rete_anno_prec":  d.get("costo_rete_anno_prec", 0.0),
            "risparmio_sole_ieri":      d.get("risparmio_sole_ieri",      0.0),
            "risparmio_sole_mese_prec": d.get("risparmio_sole_mese_prec", 0.0),
            "risparmio_sole_anno_prec": d.get("risparmio_sole_anno_prec", 0.0),
            "eids":                  build_eids(self._slot_val),
        }


# ── Stato / Versione ──────────────────────────────────────────────────────────

class _Stato(_Base):
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_STATUS)
        self._attr_name = f"Stato {n}"
        self._attr_icon = "mdi:checkbox-blank-circle-outline"

    @property
    def native_value(self): return "OK" if self._d.get("sensor_online", True) else "OFFLINE"


class _Versione(_Base):
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_VERSION)
        self._attr_name = f"Versione {n}"
        self._attr_icon = "mdi:information-outline"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self): return self._d.get("version", VERSION)



# ── Costo energia sensor (dedicated €/kWh, no unit inheritance from master) ───

class _CostoEnergia(_Base):
    """sensor.costo_energia_elettrodomestici_x1
    Dedicated sensor for energy cost per unit.
    Unit adapts to preset: €/kWh for energy, €/m³ for water/gas.
    """
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_COSTO_SENSOR)
        self._preset_ref = get_preset(e.data.get("preset", "elettrodomestico"))
        # Determine cost unit based on preset
        total_unit = e.data.get("total_unit", self._preset_ref.total_unit)
        if total_unit in ("L", "l"):
            cost_unit = "€/m³"
        elif total_unit in ("m³", "m3"):
            cost_unit = "€/m³"
        else:
            cost_unit = "€/kWh"
        self._attr_name = f"Costo Energia {n}"
        self._attr_native_unit_of_measurement = cost_unit
        self._attr_state_class  = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:currency-eur"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> float:
        return round(self._d.get("cost_per_unit", 0.0), 4)

    @property
    def extra_state_attributes(self):
        return {
            "fonte":      self._d.get("cost_source", "fisso"),
            "preset":     self._d.get("preset_id",   ""),
            "unita":      self._attr_native_unit_of_measurement,
        }



# ── Vacuum battery sensor ──────────────────────────────────────────────────────

class _VacuumBattery(_Base):
    """sensor.batteria_vacuum_x1 — battery % from battery sensor or vacuum attributes."""
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_VACUUM_BATTERY)
        self._attr_name = f"Batteria {n}"
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class  = SensorDeviceClass.BATTERY
        self._attr_state_class   = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        # Always return a value for vacuum preset; None = unknown (shown as unavailable by HA)
        # but we return 0 as fallback so the entity stays visible
        if not self._d.get("is_vacuum", False):
            return None
        val = self._d.get("vacuum_battery")
        return val if val is not None else None

    @property
    def available(self) -> bool:
        # Always available - this entity is only created for vacuum preset
        return True



# ── Device battery sensor (batteria preset) ────────────────────────────────────

class _DeviceBattery(_Base):
    """sensor.batteria_dispositivo_x1 — battery % for batteria preset devices."""
    def __init__(self, c, e, n, s):
        super().__init__(c, e, n, s, SFX_DEVICE_BATTERY)
        self._attr_name = f"Batteria {n}"
        self._attr_native_unit_of_measurement = "%"
        self._attr_device_class  = SensorDeviceClass.BATTERY
        self._attr_state_class   = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:battery"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return self._d.get("device_battery")

    @property
    def available(self) -> bool:
        return self._d.get("is_battery", False)


# ── Update sensor (Hub-level) ─────────────────────────────────────────────────

class _UpdateSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coord: UpdateCheckCoordinator, entry):
        super().__init__(coord)
        self._attr_unique_id    = f"{DOMAIN}_hub_update"
        self.entity_id          = f"sensor.{SFX_UPDATE}_hub"
        self._attr_name         = "Aggiornamento Elettrodomestico Monitor"
        self._attr_icon         = "mdi:update"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info  = _hub_device(entry)

    @property
    def _ud(self) -> dict[str, Any]: return self.coordinator.data or {}

    @property
    def native_value(self) -> str:
        return "Aggiornamento disponibile" if self._ud.get("update_available") else "Aggiornato"

    @property
    def extra_state_attributes(self):
        d = self._ud
        return {
            "versione_installata":  d.get("current_version",  ""),
            "versione_disponibile": d.get("latest_version",   ""),
            "url_release":          d.get("release_url",      ""),
            "note_release":         d.get("release_notes",    ""),
            "aggiornamento":        d.get("update_available", False),
        }
