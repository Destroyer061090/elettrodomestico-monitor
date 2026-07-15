# ============================================================
# FILE:    switch.py
# VERSION: 5.8.13
# DESC:    Switch platform — main device switch, irrigation master/zone/day switches
# CHANGED: 2026-06-11
# ============================================================
"""Switch platform for Elettrodomestico Monitor v22.

Per device:
  switch.switch_elettrodomestici_xN         — comando principale (funziona per tutti i tipi)
  switch.notifica_push_elettrodomestici_xN  — toggle notifica push
  switch.notifica_alexa_elettrodomestici_xN
  switch.notifica_google_elettrodomestici_xN
  switch.notifica_whatsapp_elettrodomestici_xN
  switch.notifica_update_elettrodomestici_hub  (hub-managed, single toggle)

Il comando principale (_MainSwitch) delega al coordinator._sw() che gestisce:
  - Elettrodomestico/Acqua/Gas → switch.turn_on/off su CONF_SWITCH_ENTITY
  - Vacuum                     → vacuum.start / vacuum.return_to_base
  - Clima                      → climate.set_hvac_mode(heat/off)
  - Trigger generico           → homeassistant.turn_on/off
"""
from __future__ import annotations
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    VERSION,
    DOMAIN, CONF_INSTANCE_ID, CONF_APPLIANCE_NAME, CONF_SLOT,
    CONF_SWITCH_ENTITY, CONF_PRESET,
    CONF_NOTIFY_PUSH, CONF_NOTIFY_ALEXA, CONF_NOTIFY_GOOGLE,
    CONF_NOTIFY_WHATSAPP, CONF_NOTIFY_UPDATE,
    SFX_SW_SWITCH,
    SFX_SW_NOTIFY_PUSH, SFX_SW_NOTIFY_ALEXA, SFX_SW_NOTIFY_GOOGLE,
    SFX_SW_NOTIFY_WHATSAPP, SFX_SW_NOTIFY_UPDATE,
    ENTRY_TYPE_HUB, CONF_ENTRY_TYPE,
)
from .coordinator import ElettrodomesticoCoordinator

_LOGGER = logging.getLogger(__name__)

# Presets that never use a physical switch entity but still need a main switch
_TRIGGER_PRESETS = {"vacuum", "clima"}


def _hub_device_info():
    return DeviceInfo(
        identifiers={(DOMAIN, "hub")},
        name="Elettrodomestico Monitor Hub",
        manufacturer="Elettrodomestico Monitor",
        model="Hub Globale",
    )


class _HubUpdateNotifySwitch(SwitchEntity, RestoreEntity):
    """Single hub-level toggle for update push notifications.
    Shared by all devices — update checking is hub-managed."""

    def __init__(self, entry):
        self._entry = entry
        self._on: bool = bool(entry.data.get("notify_update", True))
        self._attr_unique_id       = f"{DOMAIN}_hub_notifica_update"
        self.entity_id             = "switch.notifica_update_elettrodomestici_hub"
        self._attr_name            = "Notifica Aggiornamenti"
        self._attr_icon            = "mdi:bell-ring"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _hub_device_info()

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._on = last.state == "on"

    @property
    def is_on(self) -> bool:
        return self._on

    async def async_turn_on(self, **kwargs) -> None:
        self._on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._on = False
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        # Hub-managed single update-notification toggle (shared by all devices)
        async_add_entities([_HubUpdateNotifySwitch(entry)])
        return
    # Irrigation
    from .const import ENTRY_TYPE_IRRIGATION
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or        entry.data.get("entry_type") == "irrigation":
        coord = hass.data[DOMAIN][entry.entry_id]
        await _async_setup_irrigation_switch(hass, entry, coord, async_add_entities)
        return
    # Battery Device
    from .const import ENTRY_TYPE_DEVICE
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or \
            entry.data.get("entry_type") == "device":
        coord = hass.data[DOMAIN][entry.entry_id]
        await _async_setup_device_switch(hass, entry, coord, async_add_entities)
        return
    coord: ElettrodomesticoCoordinator = hass.data[DOMAIN][entry.entry_id]
    name  = entry.data.get(CONF_APPLIANCE_NAME, "Elettrodomestico")
    slot  = str(entry.data.get(CONF_SLOT, "1"))
    preset = entry.data.get(CONF_PRESET, "elettrodomestico")

    entities: list = []

    # Main switch — always created for every device type
    # For standard devices: only if switch_entity configured OR trigger entity present
    has_switch  = bool(entry.data.get(CONF_SWITCH_ENTITY))
    has_trigger = bool(entry.data.get("trigger_entity") or
                       entry.data.get("vacuum_entity"))
    if has_switch or has_trigger or preset in _TRIGGER_PRESETS:
        entities.append(_MainSwitch(coord, entry, name, slot))

    # Notification toggles — always 5 per device
    entities += [
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_PUSH,
                      f"Notifica Push {name}",          CONF_NOTIFY_PUSH,    "mdi:cellphone-message", False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_ALEXA,
                      f"Notifica Alexa {name}",         CONF_NOTIFY_ALEXA,   "mdi:amazon-alexa",      False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_GOOGLE,
                      f"Notifica Google {name}",        CONF_NOTIFY_GOOGLE,  "mdi:google",            False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_WHATSAPP,
                      f"Notifica WhatsApp {name}",      CONF_NOTIFY_WHATSAPP,"mdi:whatsapp",          False),
    ]
    async_add_entities(entities)


async def _async_setup_irrigation_switch(
    hass, entry, coord, async_add_entities
) -> None:
    """Create master switch + per-zone switches for irrigation."""
    from .irrigation_coordinator import IrrigationCoordinator
    from homeassistant.helpers.entity import DeviceInfo
    from homeassistant.helpers.restore_state import RestoreEntity

    name  = entry.data.get("appliance_name", "Irrigazione")
    slot  = str(entry.data.get("slot", "1"))
    iid   = entry.data.get("instance_id", "irr")
    DOMAIN_LOCAL = "elettrodomestico_monitor"

    dev_info = DeviceInfo(
        identifiers={(DOMAIN_LOCAL, iid)},
        name=name, manufacturer="Elettrodomestico Monitor", model="Irrigazione",
    )

    class _IrrMasterSwitch(CoordinatorEntity, SwitchEntity):
        """Master switch: starts/stops full cycle."""
        def __init__(self):
            super().__init__(coord)
            self._attr_unique_id    = f"{DOMAIN_LOCAL}_{iid}_irr_master_x{slot}"
            self.entity_id          = f"switch.irrigazione_master_x{slot}"
            self._attr_name         = f"Avvia Ciclo {name}"
            self._attr_icon         = "mdi:sprinkler-variant"
            self._attr_device_info  = dev_info
            self._attr_has_entity_name = False
        @property
        def is_on(self): return (self.coordinator.data or {}).get("cycle_active", False)
        async def async_turn_on(self, **kw): await coord.start_cycle()
        async def async_turn_off(self, **kw): await coord.stop_cycle()

    class _IrrZoneSwitch(SwitchEntity, RestoreEntity):
        """Per-zone manual switch."""
        def __init__(self, zone_idx, zone):
            self._zone_idx    = zone_idx
            self._zone        = zone
            self._sw_eid      = zone.get("switch", "")
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_irr_z{zone_idx}_x{slot}"
            self.entity_id         = f"switch.irrigazione_z{zone_idx+1}_x{slot}"
            self._attr_name        = f"{zone.get('name', f'Zona {zone_idx+1}')} {name}"
            self._attr_icon        = "mdi:water"
            self._attr_device_info = dev_info
        @property
        def is_on(self):
            if not self._sw_eid: return False
            st = hass.states.get(self._sw_eid)
            return st is not None and st.state == "on"
        async def async_added_to_hass(self):
            # Mirror the underlying physical switch reactively. Without this the
            # proxy's on/off state only refreshed sporadically, so toggling it
            # (which is the normal, EM-native way to command the zone) showed the
            # button bouncing back ON/OFF instead of settling immediately.
            if self._sw_eid:
                @callback
                def _mirror(*_):
                    self.async_write_ha_state()
                self.async_on_remove(
                    async_track_state_change_event(
                        hass, [self._sw_eid], _mirror))
        async def async_turn_on(self, **kw):
            if self._sw_eid:
                await hass.services.async_call("homeassistant", "turn_on", {"entity_id": self._sw_eid})
                self.async_write_ha_state()
        async def async_turn_off(self, **kw):
            if self._sw_eid:
                await hass.services.async_call("homeassistant", "turn_off", {"entity_id": self._sw_eid})
                self.async_write_ha_state()

    # ── Enable/disable scheduling switch ─────────────────────────────────────
    class _SchedEnableSwitch(SwitchEntity):
        """Master toggle for automatic scheduling. Off = paused (winter mode)."""
        def __init__(self):
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_irr_sched_enable_x{slot}"
            self.entity_id         = f"switch.irrigazione_programmazione_x{slot}"
            self._attr_name        = f"Programmazione {name}"
            self._attr_icon        = "mdi:calendar-clock"
            self._attr_device_info = dev_info

        @property
        def is_on(self) -> bool:
            return coord.config.get("irr_sched_enabled") is not False

        async def async_turn_on(self, **kw):
            conf = dict(coord.config); conf["irr_sched_enabled"] = True
            hass.config_entries.async_update_entry(entry, data=conf)
            coord._wire_schedules(); self.async_write_ha_state()

        async def async_turn_off(self, **kw):
            conf = dict(coord.config); conf["irr_sched_enabled"] = False
            hass.config_entries.async_update_entry(entry, data=conf)
            # Unsubscribe all schedules
            for unsub in coord._sched_unsubs:
                try: unsub()
                except Exception: pass
            coord._sched_unsubs = []
            self.async_write_ha_state()

    # ── Day-of-week switches — 7 shared across all schedules ────────────────
    class _DaySwitch(SwitchEntity):
        """Toggle a weekday. Days stored in 'irr_days' key and synced to active schedules."""
        def __init__(self, day_key: str, day_label: str):
            self._day_key = day_key
            self._attr_unique_id   = f"{DOMAIN_LOCAL}_{iid}_irr_day_{day_key}_x{slot}"
            self.entity_id         = f"switch.irrigazione_{day_key}_x{slot}"
            self._attr_name        = f"{day_label} {name}"
            self._attr_icon        = "mdi:calendar-week"
            self._attr_device_info = dev_info

        def _get_days(self) -> list:
            """Read from dedicated irr_days list."""
            return list(coord.config.get("irr_days") or [])

        @property
        def is_on(self) -> bool:
            return self._day_key in self._get_days()

        async def async_turn_on(self, **kw):
            await self._set_day(True)

        async def async_turn_off(self, **kw):
            await self._set_day(False)

        async def _set_day(self, active: bool):
            days = self._get_days()
            if active and self._day_key not in days:
                days.append(self._day_key)
            elif not active and self._day_key in days:
                days.remove(self._day_key)
            else:
                return  # no change

            conf = dict(coord.config)
            conf["irr_days"] = days

            # Sync days to ALL schedule slots (coordinator filters 00:00 itself)
            for sk in ("irr_schedule_1", "irr_schedule_2", "irr_schedule_3"):
                sched = dict(conf.get(sk) or {})
                if not sched:
                    sched = {"time": "00:00:00", "days": [], "mode": "fixed", "offset_min": 0}
                sched["days"] = days
                conf[sk] = sched

            hass.config_entries.async_update_entry(entry, data=conf)
            # Note: _wire_schedules NOT called here to avoid UI refresh/focus loss
            # Coordinator reads days fresh at fire time (see _schedule_fixed)
            self.async_write_ha_state()

    sw_entities = [_IrrMasterSwitch(), _SchedEnableSwitch()]
    zones = coord.zones
    _LOGGER.debug("[IRR] switch setup: %d zones, coord.config keys: %s",
                  len(zones), list(coord.config.keys()))
    for i, zone in enumerate(zones):
        sw_entities.append(_IrrZoneSwitch(i, zone))
    # Add 7 day-of-week switches (shared across all 3 schedule slots)
    days_it = [
        ("lunedi","Lun"),("martedi","Mar"),("mercoledi","Mer"),("giovedi","Gio"),
        ("venerdi","Ven"),("sabato","Sab"),("domenica","Dom"),
    ]
    for day_key, day_label in days_it:
        sw_entities.append(_DaySwitch(day_key, day_label))

    # Notification toggle switches (push/alexa/google/whatsapp) — same as appliances
    from .const import (
        SFX_SW_NOTIFY_PUSH, SFX_SW_NOTIFY_ALEXA,
        SFX_SW_NOTIFY_GOOGLE, SFX_SW_NOTIFY_WHATSAPP,
        CONF_NOTIFY_PUSH, CONF_NOTIFY_ALEXA, CONF_NOTIFY_GOOGLE, CONF_NOTIFY_WHATSAPP,
    )
    _irr_notify = [
        (SFX_SW_NOTIFY_PUSH,     f"Notifica Push {name}",     CONF_NOTIFY_PUSH,     "mdi:cellphone"),
        (SFX_SW_NOTIFY_ALEXA,    f"Notifica Alexa {name}",    CONF_NOTIFY_ALEXA,    "mdi:amazon-alexa"),
        (SFX_SW_NOTIFY_GOOGLE,   f"Notifica Google {name}",   CONF_NOTIFY_GOOGLE,   "mdi:google-home"),
        (SFX_SW_NOTIFY_WHATSAPP, f"Notifica WhatsApp {name}", CONF_NOTIFY_WHATSAPP, "mdi:whatsapp"),
    ]
    for _sfx, _label, _conf, _icon in _irr_notify:
        sw_entities.append(_NotifySwitch(entry, name, slot, _sfx, _label, _conf, _icon, False))

    _LOGGER.info("[IRR] Creating %d irrigation switches (1 master + %d zones + 21 day toggles + 4 notify)",
                 len(sw_entities), len(zones))
    async_add_entities(sw_entities, update_before_add=True)


def _device(entry, name):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1"))))},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo",
        sw_version=VERSION,
    )


class _MainSwitch(CoordinatorEntity, SwitchEntity):
    """
    Comando principale del device.
    Funziona per tutti i tipi: vacuum, clima, switch fisico, trigger generico.
    Delega l'azione effettiva al coordinator._sw() che sa come gestire ogni tipo.
    """

    def __init__(self, coord, entry, name, slot):
        super().__init__(coord)
        self._entry = entry
        self._preset = entry.data.get(CONF_PRESET, "elettrodomestico")
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id   = f"{DOMAIN}_{iid}_{SFX_SW_SWITCH}_x{slot}"
        self.entity_id         = f"switch.{SFX_SW_SWITCH}_x{slot}"
        self._attr_name        = f"Switch {name}"
        self._attr_device_info = _device(entry, name)

        # Icon depends on device type
        if self._preset == "vacuum":
            self._attr_icon = "mdi:robot-vacuum"
        elif self._preset == "clima":
            self._attr_icon = "mdi:thermostat"
        else:
            self._attr_icon = "mdi:power"

    @property
    def is_on(self) -> bool:
        """
        Reads main_on from coordinator data which correctly reflects:
        - vacuum: cleaning/returning/paused state of vacuum entity
        - clima: hvac_mode != off of climate entity
        - standard: physical switch entity state
        - trigger: trigger entity active state
        - fallback: power threshold ac_state
        """
        d = self.coordinator.data or {}
        return d.get("main_on", d.get("ac_state", False))

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        return {
            "preset":       self._preset,
            "ciclo_attivo": d.get("cycle_active", False),
            "switch_fisico": self._entry.data.get(CONF_SWITCH_ENTITY, ""),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on — delegates to coordinator which knows the device type."""
        coord: ElettrodomesticoCoordinator = self.coordinator
        await coord._sw("turn_on")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off — delegates to coordinator which knows the device type."""
        coord: ElettrodomesticoCoordinator = self.coordinator
        await coord._sw("turn_off")
        self.async_write_ha_state()


class _NotifySwitch(SwitchEntity, RestoreEntity):
    """
    Per-device notification toggle.
    State persists across restarts via RestoreEntity.
    The coordinator reads this entity's state when sending notifications.
    """

    def __init__(self, entry, name, slot, sfx, label, conf_key, icon, default):
        self._entry    = entry
        self._conf_key = conf_key
        self._on: bool = bool(entry.data.get(conf_key, default))

        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id       = f"{DOMAIN}_{iid}_{sfx}_x{slot}"
        self.entity_id             = f"switch.{sfx}_x{slot}"
        self._attr_name            = label
        self._attr_icon            = icon
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info     = _device(entry, name)

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._on = last.state == "on"
        else:
            self._on = bool(self._entry.data.get(self._conf_key, False))

    @property
    def is_on(self) -> bool:
        return self._on

    async def async_turn_on(self, **kwargs) -> None:
        self._on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        self._on = False
        self.async_write_ha_state()




# ════════════════════════════════════════════════════════════════════════════
# Battery Device switches
# ════════════════════════════════════════════════════════════════════════════

def _device_dev_info(entry, name):
    iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
    return DeviceInfo(
        identifiers={(DOMAIN, iid)},
        name=name,
        manufacturer="Elettrodomestico Monitor",
        model="Centro Controllo Dispositivi",
    )


async def _async_setup_device_switch(hass, entry, coord, async_add_entities):
    name = entry.data.get(CONF_APPLIANCE_NAME, "Dispositivo")
    slot = str(entry.data.get(CONF_SLOT, "1"))
    ents = [
        _DevChargeSwitch(coord, entry, name, slot),
        _DevAutoSwitch(entry, name, slot),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_PUSH,
                      f"Notifica Push {name}",     CONF_NOTIFY_PUSH,    "mdi:cellphone-message", False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_ALEXA,
                      f"Notifica Alexa {name}",    CONF_NOTIFY_ALEXA,   "mdi:amazon-alexa",      False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_GOOGLE,
                      f"Notifica Google {name}",   CONF_NOTIFY_GOOGLE,  "mdi:google",            False),
        _NotifySwitch(entry, name, slot, SFX_SW_NOTIFY_WHATSAPP,
                      f"Notifica WhatsApp {name}", CONF_NOTIFY_WHATSAPP,"mdi:whatsapp",          False),
    ]
    async_add_entities(ents)


class _DevChargeSwitch(CoordinatorEntity, SwitchEntity):
    """Mirrors/controls the real charging plug switch."""
    def __init__(self, coord, entry, name, slot):
        super().__init__(coord)
        self._coord = coord
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id   = f"{DOMAIN}_{iid}_carica_dispositivo_x{slot}"
        self.entity_id         = f"switch.carica_dispositivo_x{slot}"
        self._attr_name        = f"Carica {name}"
        self._attr_icon        = "mdi:power-plug"
        self._attr_device_info = _device_dev_info(entry, name)

    @property
    def is_on(self) -> bool:
        return bool((self.coordinator.data or {}).get("charging", False))

    async def async_turn_on(self, **kw):
        await self._coord._set_charge(True)
        await self._coord.async_request_refresh()

    async def async_turn_off(self, **kw):
        await self._coord._set_charge(False)
        await self._coord.async_request_refresh()


class _DevAutoSwitch(SwitchEntity, RestoreEntity):
    """Enable/disable automatic charge management (persisted)."""
    def __init__(self, entry, name, slot):
        self._on = True
        iid = entry.data.get(CONF_INSTANCE_ID, str(entry.data.get(CONF_SLOT, "1")))
        self._attr_unique_id       = f"{DOMAIN}_{iid}_ricarica_auto_dispositivo_x{slot}"
        self.entity_id             = f"switch.ricarica_auto_dispositivo_x{slot}"
        self._attr_name            = f"Ricarica Automatica {name}"
        self._attr_icon            = "mdi:battery-sync"
        self._attr_device_info     = _device_dev_info(entry, name)

    async def async_added_to_hass(self):
        last = await self.async_get_last_state()
        if last and last.state in ("on", "off"):
            self._on = last.state == "on"

    @property
    def is_on(self): return self._on
    async def async_turn_on(self, **kw): self._on = True; self.async_write_ha_state()
    async def async_turn_off(self, **kw): self._on = False; self.async_write_ha_state()
