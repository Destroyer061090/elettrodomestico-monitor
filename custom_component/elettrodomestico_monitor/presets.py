# ============================================================
# FILE:    presets.py
# VERSION: 5.0.0
# DESC:    Presets — device type definitions
# CHANGED: 2026-06-11
# ============================================================
"""Preset definitions for Elettrodomestico Monitor.

Each preset pre-fills unit of measurement, device_class, icons and labels.
All values are overridable by the user in the config flow.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# ── Cost key constants (must match hub.py keys) ───────────────────────────────
COST_KEY_KWH     = "costo_kwh"
COST_KEY_ACQUA   = "costo_acqua_m3"
COST_KEY_GAS     = "costo_gas_m3"
COST_KEY_VENDITA = "vendita_kwh"   # Solare: revenue instead of cost

# ── Preset IDs ────────────────────────────────────────────────────────────────
PRESET_ELETTRODOMESTICO = "elettrodomestico"
PRESET_ACQUA            = "acqua"
PRESET_GAS              = "gas"
PRESET_VACUUM           = "vacuum"
PRESET_SOLARE           = "solare"
PRESET_BATTERIA         = "batteria"
PRESET_CLIMA            = "clima"
PRESET_IRRIGAZIONE      = "irrigazione"
PRESET_GENERICO         = "generico"

PRESET_IDS = [
    PRESET_ELETTRODOMESTICO,
    PRESET_ACQUA,
    PRESET_GAS,
    PRESET_VACUUM,
    PRESET_CLIMA,
    PRESET_IRRIGAZIONE,
    PRESET_GENERICO,
]
# Hidden presets (not shown in config flow selector but available in code)
PRESET_IDS_HIDDEN = [PRESET_BATTERIA, PRESET_SOLARE]

PRESET_LABELS = {
    PRESET_ELETTRODOMESTICO: "Elettrodomestico (W → kWh)",
    PRESET_ACQUA:            "Acqua (L/min → L / m³)",
    PRESET_GAS:              "Gas (m³/h → m³)",
    PRESET_VACUUM:           "Aspirapolvere (W → kWh)",
    PRESET_BATTERIA:         "Batteria Dispositivo (ricarica telefoni/tablet)",
    PRESET_CLIMA:            "Clima / Termostato",
    PRESET_IRRIGAZIONE:      "Irrigazione (L/min + kWh pompa)",
    PRESET_SOLARE:           "Solare / Fotovoltaico (W → kWh prodotti)",
    PRESET_GENERICO:         "Generico (personalizzabile)",
}


@dataclass
class PresetConfig:
    """All per-preset configuration values."""
    # Source sensor unit (what the power/flow sensor measures)
    source_unit: str
    # Accumulated total unit
    total_unit: str
    # HA device_class for energy/water/gas sensors
    device_class: str          # "energy" | "water" | "gas" | None
    # Which hub cost key to use
    cost_key: str
    # Default icon for the device
    default_icon: str
    # Suggested icons shown in config flow
    suggested_icons: list[str]
    # UI labels
    label_consumo: str         # "Consumo" | "Produzione" | "Volume"
    label_costo: str           # "Costo" | "Risparmio/Guadagno"
    label_unit_display: str    # shown in sensor names
    # Whether this preset has an extra m³ derived sensor
    has_volume_m3: bool = False
    # Whether cost logic is inverted (solar: production = revenue)
    inverted_cost: bool = False
    # Whether to show cost entities (vacuum has no cost)
    show_cost: bool = True


PRESETS: dict[str, PresetConfig] = {
    PRESET_ELETTRODOMESTICO: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_KWH,
        default_icon      = "mdi:washing-machine",
        suggested_icons   = [
            "mdi:washing-machine", "mdi:dishwasher", "mdi:tumble-dryer",
            "mdi:fridge", "mdi:microwave", "mdi:stove", "mdi:air-conditioner",
            "mdi:television", "mdi:coffee-maker", "mdi:flash",
        ],
        label_consumo     = "Consumo",
        label_costo       = "Costo",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_ACQUA: PresetConfig(
        source_unit       = "L/min",
        total_unit        = "L",
        device_class      = "water",
        cost_key          = COST_KEY_ACQUA,
        default_icon      = "mdi:water",
        suggested_icons   = [
            "mdi:water", "mdi:water-pump", "mdi:shower", "mdi:bathtub",
            "mdi:sprinkler", "mdi:pipe",
        ],
        label_consumo     = "Consumo",
        label_costo       = "Costo Acqua",
        label_unit_display= "L",
        has_volume_m3     = True,   # adds sensor.volume_m3_*
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_GAS: PresetConfig(
        source_unit       = "m³/h",
        total_unit        = "m³",
        device_class      = "gas",
        cost_key          = COST_KEY_GAS,
        default_icon      = "mdi:gas-burner",
        suggested_icons   = [
            "mdi:gas-burner", "mdi:fire", "mdi:radiator", "mdi:heating-coil",
        ],
        label_consumo     = "Consumo Gas",
        label_costo       = "Costo Gas",
        label_unit_display= "m³",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_VACUUM: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_KWH,
        default_icon      = "mdi:robot-vacuum",
        suggested_icons   = [
            "mdi:robot-vacuum", "mdi:robot-vacuum-variant", "mdi:broom",
        ],
        label_consumo     = "Consumo",
        label_costo       = "Costo",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,   # enable for smart plug cost trackinggful cost tracking
    ),
    PRESET_BATTERIA: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_KWH,
        default_icon      = "mdi:battery-charging",
        suggested_icons   = [
            "mdi:battery-charging", "mdi:cellphone-charging",
            "mdi:tablet-cellphone", "mdi:laptop",
            "mdi:battery-charging-100",
        ],
        label_consumo     = "Energia Ricarica",
        label_costo       = "Costo Ricarica",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_SOLARE: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_VENDITA,
        default_icon      = "mdi:solar-power",
        suggested_icons   = [
            "mdi:solar-power", "mdi:solar-power-variant",
            "mdi:white-balance-sunny", "mdi:weather-sunny",
        ],
        label_consumo     = "Produzione",
        label_costo       = "Risparmio/Guadagno",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = True,   # revenue instead of cost
        show_cost         = True,
    ),
    PRESET_CLIMA: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_KWH,
        default_icon      = "mdi:thermostat",
        suggested_icons   = [
            "mdi:thermostat", "mdi:air-conditioner",
            "mdi:heat-wave", "mdi:snowflake",
        ],
        label_consumo     = "Energia Climatizzazione",
        label_costo       = "Costo Climatizzazione",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_IRRIGAZIONE: PresetConfig(
        source_unit       = "L/min",
        total_unit        = "L",
        device_class      = "water",
        cost_key          = COST_KEY_ACQUA,
        default_icon      = "mdi:sprinkler-variant",
        suggested_icons   = [
            "mdi:sprinkler-variant", "mdi:water-pump",
            "mdi:watering-can", "mdi:pipe-valve",
        ],
        label_consumo     = "Acqua Consumata",
        label_costo       = "Costo Irrigazione",
        label_unit_display= "L",
        has_volume_m3     = True,
        inverted_cost     = False,
        show_cost         = True,
    ),
    PRESET_GENERICO: PresetConfig(
        source_unit       = "W",
        total_unit        = "kWh",
        device_class      = "energy",
        cost_key          = COST_KEY_KWH,
        default_icon      = "mdi:gauge",
        suggested_icons   = [
            "mdi:gauge", "mdi:flash", "mdi:chart-line", "mdi:cog",
        ],
        label_consumo     = "Consumo",
        label_costo       = "Costo",
        label_unit_display= "kWh",
        has_volume_m3     = False,
        inverted_cost     = False,
        show_cost         = True,
    ),
}


def get_preset(preset_id: str) -> PresetConfig:
    """Return preset config, falling back to generico."""
    return PRESETS.get(preset_id, PRESETS[PRESET_GENERICO])
