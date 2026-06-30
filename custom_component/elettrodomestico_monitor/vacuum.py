# ============================================================
# FILE:    vacuum.py
# VERSION: 5.7.25
# DESC:    Vacuum platform — vacuum wrapper entity for vacuum preset devices
# CHANGED: 2026-06-11
# ============================================================
"""Vacuum platform for Elettrodomestico Monitor v16.

Creates vacuum.elettrodomestici_xN for vacuum preset devices.
Wraps the real vacuum entity (CONF_VACUUM_ENTITY) exposing:
  - State: cleaning / returning / docked / idle / paused / error
  - Battery level
  - Actions: start, pause, stop, return_to_base, locate
"""
from __future__ import annotations
import logging
from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
    VacuumActivity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    CONF_VACUUM_ENTITY, CONF_BATTERY_SENSOR, CONF_VACUUM_RETURN_PCT,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE, CONF_PRESET,
)
from .coordinator import ElettrodomesticoCoordinator

_LOGGER = logging.getLogger(__name__)

# State mapping from HA vacuum states to VacuumActivity
_STATE_MAP = {
    # Standard HA states
    "cleaning":          VacuumActivity.CLEANING,
    "returning":         VacuumActivity.RETURNING,
    "docked":            VacuumActivity.DOCKED,
    "idle":              VacuumActivity.IDLE,
    "paused":            VacuumActivity.PAUSED,
    "error":             VacuumActivity.ERROR,
    # Chinese robot extended states → mapped to nearest standard state
    "smart_cleaning":    VacuumActivity.CLEANING,   # Roborock/Xiaomi
    "zone_cleaning":     VacuumActivity.CLEANING,   # Roborock zone
    "spot_cleaning":     VacuumActivity.CLEANING,   # various
    "goto_target":       VacuumActivity.CLEANING,   # Roborock go to
    "quick_mapping":     VacuumActivity.CLEANING,   # Roborock mapping
    "fast_mapping":      VacuumActivity.CLEANING,   # Dreame mapping
    "selective_cleaning":VacuumActivity.CLEANING,   # Dreame
    "room_cleaning":     VacuumActivity.CLEANING,   # Dreame rooms
    "auto_cleaning":     VacuumActivity.CLEANING,   # generic
    "standby":           VacuumActivity.IDLE,
    "sleep":             VacuumActivity.IDLE,
    "charging":          VacuumActivity.DOCKED,
}

SFX_VACUUM = "elettrodomestici"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        return
    if entry.data.get(CONF_PRESET) != "vacuum":
        return

    coord: ElettrodomesticoCoordinator = hass.data[DOMAIN][entry.entry_id]
    name = entry.data.get(CONF_APPLIANCE_NAME, "Vacuum")
    slot = str(entry.data.get(CONF_SLOT, "1"))

    async_add_entities([_VacuumEntity(coord, entry, name, slot)])


def _device(entry, name):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Vacuum",
        sw_version="4.16",
    )


class _VacuumEntity(CoordinatorEntity, StateVacuumEntity):
    """
    Vacuum entity that mirrors and controls the real vacuum.
    entity_id: vacuum.elettrodomestici_xN
    """

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Mirror the underlying vacuum's features (crash-safe).
        Only enables bits valid in this HA version's enum, so a robot that
        advertises an unknown bit can't take the entity to 'unavailable'."""
        base = (VacuumEntityFeature.START
                | VacuumEntityFeature.PAUSE
                | VacuumEntityFeature.STOP
                | VacuumEntityFeature.RETURN_HOME
                | VacuumEntityFeature.STATE
                | VacuumEntityFeature.LOCATE)
        st = self.hass.states.get(self._vacuum_eid) if self._vacuum_eid else None
        if not st:
            return base
        feat = base
        if st.attributes.get("fan_speed_list"):
            feat |= VacuumEntityFeature.FAN_SPEED
        # CLEAN_SPOT and SEND_COMMAND have methods implemented below, so enable
        # them if the device advertises them via its mode/feature data.
        raw = st.attributes.get("supported_features")
        if isinstance(raw, int) and raw > 0:
            try:
                if hasattr(VacuumEntityFeature, "CLEAN_SPOT") and (raw & int(VacuumEntityFeature.CLEAN_SPOT)):
                    feat |= VacuumEntityFeature.CLEAN_SPOT
                if hasattr(VacuumEntityFeature, "SEND_COMMAND") and (raw & int(VacuumEntityFeature.SEND_COMMAND)):
                    feat |= VacuumEntityFeature.SEND_COMMAND
            except (ValueError, TypeError):
                pass
        return feat

    def __init__(self, coord, entry, name, slot):
        super().__init__(coord)
        self._entry        = entry
        self._slot         = str(slot)
        self._vacuum_eid   = (entry.data.get(CONF_VACUUM_ENTITY) or "").strip()
        self._battery_eid  = (entry.data.get(CONF_BATTERY_SENSOR) or "").strip()
        self._return_pct   = int(entry.data.get(CONF_VACUUM_RETURN_PCT, 0) or 0)
        self._return_armed = True
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))

        self._attr_unique_id   = f"{DOMAIN}_{iid}_{SFX_VACUUM}_vacuum_x{slot}"
        self.entity_id         = f"vacuum.{SFX_VACUUM}_x{slot}"
        self._attr_name        = name
        self._attr_icon        = entry.data.get("device_icon", "mdi:robot-vacuum")
        self._attr_device_info = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Track real vacuum state changes
        if self._vacuum_eid:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._vacuum_eid], self._on_vacuum_state
                )
            )
        if self._battery_eid:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, [self._battery_eid], self._on_battery_state
                )
            )

    @callback
    def _on_vacuum_state(self, event) -> None:
        self.async_write_ha_state()

    @callback
    def _on_battery_state(self, event) -> None:
        self._check_battery_return()
        self.async_write_ha_state()

    def _check_battery_return(self) -> None:
        """If a return threshold is set and the battery drops to/below it while
        the robot is actively cleaning, send it back to base. Fires once per
        discharge cycle (re-armed when the battery climbs back above threshold).

        The threshold is read live from the number entity (editable from the
        card), falling back to the value stored at setup."""
        pct = self._return_pct
        num_st = self.hass.states.get(f"number.soglia_rientro_vacuum_x{self._slot}")
        if num_st and num_st.state not in ("unknown", "unavailable", ""):
            try:
                pct = int(float(num_st.state))
            except (ValueError, TypeError):
                pass
        if not pct or pct <= 0:
            return
        if not self._battery_eid:
            return
        st = self.hass.states.get(self._battery_eid)
        if not st or st.state in ("unknown", "unavailable", ""):
            return
        try:
            level = float(st.state)
        except (ValueError, TypeError):
            return
        # Re-arm once we're comfortably above the threshold again
        if level > pct + 2:
            self._return_armed = True
        if not self._return_armed:
            return
        if level > pct:
            return
        # Only act if the robot is actually cleaning (not already docked/idle)
        vst = self.hass.states.get(self._vacuum_eid) if self._vacuum_eid else None
        state = vst.state if vst else None
        if state not in ("cleaning", "running", "on"):
            return
        self._return_armed = False
        _LOGGER.info("[Vacuum x%s] Batteria %.0f%% <= soglia %.0f%% → rientro alla base",
                     self._slot, level, pct)
        self.hass.async_create_task(self._battery_return_and_notify(level))

    async def _battery_return_and_notify(self, level: float) -> None:
        try:
            await self._call_vacuum("return_to_base")
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[Vacuum x%s] return_to_base fallito: %s", self._slot, ex)
        # Notify via the coordinator's shared channels, if available
        notify = getattr(self.coordinator, "_notify", None)
        if callable(notify):
            try:
                await notify(
                    f"Batteria al {level:.0f}% — rientro alla base",
                    self._device_name() if hasattr(self, "_device_name") else "Aspirapolvere")
            except Exception:  # noqa: BLE001
                pass

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def activity(self) -> VacuumActivity | None:
        if not self._vacuum_eid:
            return VacuumActivity.IDLE
        st = self.hass.states.get(self._vacuum_eid)
        if st is None:
            return None
        state_lower = st.state.lower()
        if state_lower in _STATE_MAP:
            return _STATE_MAP[state_lower]
        # Unknown state: if it's not an inactive state, assume cleaning
        # (handles any future or non-standard Chinese robot states)
        from .const import VACUUM_INACTIVE_STATES
        if state_lower not in VACUUM_INACTIVE_STATES:
            return VacuumActivity.CLEANING
        return VacuumActivity.IDLE

    # battery_level removed — HA 2026.8 deprecated VacuumEntityFeature.BATTERY
    # Use sensor.batteria_vacuum_xN instead (created by sensor.py for vacuum preset)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "entita_vacuum": self._vacuum_eid,
        }
        if self._vacuum_eid:
            st = self.hass.states.get(self._vacuum_eid)
            if st:
                # Forward useful attributes from the real vacuum
                for attr in ("fan_speed", "fan_speed_list", "status",
                             "cleaned_area", "cleaning_time",
                             "last_clean_start", "last_clean_end"):
                    val = st.attributes.get(attr)
                    if val is not None:
                        attrs[attr] = val
        # Add coordinator stats
        d = self.coordinator.data or {}
        attrs["cicli_totale"] = d.get("total_cycles", 0)
        attrs["cicli_oggi"]   = d.get("cycles_today",  0)
        attrs["tempo_oggi"]   = d.get("time_today_str", "0min")
        return attrs

    # ── Actions ───────────────────────────────────────────────────────────────

    async def _call_vacuum(self, service: str, **kwargs) -> None:
        if not self._vacuum_eid:
            _LOGGER.warning("No vacuum entity configured")
            return
        try:
            await self.hass.services.async_call(
                "vacuum", service,
                {"entity_id": self._vacuum_eid, **kwargs},
            )
        except Exception as ex:
            _LOGGER.error("vacuum.%s failed: %s", service, ex)

    async def async_start(self) -> None:
        # Also notify coordinator so cycle tracking starts
        await self._call_vacuum("start")
        coord = self.hass.data.get("elettrodomestico_monitor", {}).get(self._entry.entry_id)
        if coord:
            await coord._sw("turn_on")

    async def async_pause(self) -> None:
        await self._call_vacuum("pause")

    async def async_stop(self, **kwargs) -> None:
        await self._call_vacuum("stop")

    async def async_return_to_base(self, **kwargs) -> None:
        # Also notify coordinator so cycle tracking ends
        await self._call_vacuum("return_to_base")
        coord = self.hass.data.get("elettrodomestico_monitor", {}).get(self._entry.entry_id)
        if coord:
            await coord._sw("turn_off")

    async def async_locate(self, **kwargs) -> None:
        await self._call_vacuum("locate")

    async def async_set_fan_speed(self, fan_speed: str, **kwargs) -> None:
        await self._call_vacuum("set_fan_speed", fan_speed=fan_speed)

    async def async_clean_spot(self, **kwargs) -> None:
        await self._call_vacuum("clean_spot")

    async def async_send_command(self, command: str, params=None, **kwargs) -> None:
        data = {"command": command}
        if params is not None:
            data["params"] = params
        await self._call_vacuum("send_command", **data)
