# ============================================================
# FILE:    storage.py
# VERSION: 5.2.0
# DESC:    Storage — persistent data per device (statistics, cycle info)
# CHANGED: 2026-06-11
# ============================================================
"""Persistent storage for Elettrodomestico Monitor."""
from __future__ import annotations
import logging
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .const import DOMAIN, STORAGE_VERSION, STORAGE_KEY, WEEK_DAYS

_LOGGER = logging.getLogger(__name__)


def _default(instance_id: str) -> dict[str, Any]:
    weekly = {d: {"cicli": "0", "tempo": "0min", "consumo": 0.0, "costo": 0.0} for d in WEEK_DAYS}
    return {
        "instance_id": instance_id,
        # cycle
        "total_cycles": 0,
        "cycle_active": False,
        "cycle_start_kwh": 0.0,
        "cycle_start_ts": 0.0,
        "cycle_last_duration": "",
        "cycle_last_consumption": 0.0,
        "cycle_last_cost": 0.0,
        "cycle_end_time": "",
        # meta
        "maintenance_date": "",
        "reset_date": "",
        # accumulators
        "kwh_total_accum": 0.0,
        "energy_today": 0.0,   "energy_month": 0.0,   "energy_year": 0.0,
        "energy_yesterday": 0.0,"energy_last_month": 0.0,"energy_last_year": 0.0,
        "time_today": 0.0,     "time_month": 0.0,     "time_year": 0.0,
        "time_yesterday": 0.0, "time_last_month": 0.0,"time_last_year": 0.0,
        "cycles_today": 0,     "cycles_month": 0,     "cycles_year": 0,
        "cycles_yesterday": 0, "cycles_last_month": 0,"cycles_last_year": 0,
        "weekly": weekly,
    }


def _sanitize(data: dict, instance_id: str) -> dict:
    """Reset any top-level field whose stored type doesn't match the
    default's type back to the default value.

    FIX (audit v7.0.0, medio): async_load() merged whatever JSON was on
    disk with no type validation. A single corrupted numeric field (e.g.
    "energy_today" saved as a string by a bad write, a manual edit, or a
    future format change) would load silently and only surface later as an
    UNCAUGHT TypeError inside coordinator._integrate()'s
    "self._e_today += delta" — breaking that coordinator's updates
    indefinitely. Validating at load time keeps a single bad field from
    taking down the whole device.
    """
    defaults = _default(instance_id)
    for key, dflt in defaults.items():
        if key not in data or key == "weekly":
            continue
        val = data[key]
        ok = (
            isinstance(val, bool) if isinstance(dflt, bool) else
            (isinstance(val, (int, float)) and not isinstance(val, bool)) if isinstance(dflt, (int, float)) else
            isinstance(val, str) if isinstance(dflt, str) else
            True
        )
        if not ok:
            _LOGGER.warning(
                "[EM Storage] '%s': tipo inatteso per il campo '%s' (%r) — ripristinato al default",
                instance_id, key, val)
            data[key] = dflt
    return data


class ElettrodomesticoStorage:
    def __init__(self, hass: HomeAssistant, instance_id: str) -> None:
        self._store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{instance_id}")
        self._data: dict[str, Any] = _default(instance_id)
        self._instance_id = instance_id

    async def async_load(self) -> None:
        try:
            stored = await self._store.async_load()
        except Exception as ex:
            import logging
            logging.getLogger(__name__).warning(
                "[EM Storage] Failed to load storage for %s (corrupted?): %s — using defaults",
                self._instance_id, ex
            )
            stored = None
        if stored:
            try:
                base = _default(self._instance_id)
                base.update(stored)
                for d in WEEK_DAYS:
                    base["weekly"].setdefault(d, {"cicli":"0","tempo":"0min","consumo":0.0,"costo":0.0})
                base = _sanitize(base, self._instance_id)
                self._data = base
            except Exception as ex:
                import logging
                logging.getLogger(__name__).warning(
                    "[EM Storage] Failed to parse storage for %s: %s — using defaults",
                    self._instance_id, ex
                )

    async def async_save(self) -> None:
        await self._store.async_save(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def set_weekly(self, day: str, key: str, value: Any) -> None:
        self._data["weekly"].setdefault(day, {})
        self._data["weekly"][day][key] = value

    async def async_reset(self) -> None:
        self._data = _default(self._instance_id)
        await self.async_save()

    @property
    def data(self) -> dict[str, Any]:
        return self._data
