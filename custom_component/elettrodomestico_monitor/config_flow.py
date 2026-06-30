# ============================================================
# FILE:    config_flow.py
# VERSION: 5.8.9
# DESC:    Config flow — setup wizard for all device types including irrigation
# CHANGED: 2026-06-11
# ============================================================
"""Config flow for Elettrodomestico Monitor v12."""
from __future__ import annotations
import uuid
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

import os as _os

from .const import (
    DOMAIN,
    ENTRY_TYPE_HUB, ENTRY_TYPE_APPLIANCE,
    CONF_ENTRY_TYPE, CONF_INSTANCE_ID, CONF_SLOT,
    CONF_PRESET, CONF_DEVICE_ICON,
    CONF_COSTO_KWH,   CONF_COSTO_KWH_SENSOR,
    CONF_COSTO_ACQUA, CONF_COSTO_ACQUA_SENSOR,
    CONF_COSTO_GAS,   CONF_COSTO_GAS_SENSOR,
    CONF_VENDITA_KWH, CONF_VENDITA_KWH_SENSOR,
    CONF_FV_ENABLED, CONF_FV_GRID_SENSOR, CONF_FV_INVERT, CONF_FV_THRESHOLD_W, DEFAULT_FV_THRESHOLD, CONF_FV_EXCLUDE,
    CONF_NOTIFY_START_TIME, CONF_NOTIFY_END_TIME,
    CONF_PUSH_TARGETS, CONF_ALEXA_TARGETS, CONF_GOOGLE_TARGETS,
    CONF_WHATSAPP_ENTITY, CONF_AUTO_ON_TIME, CONF_AUTO_OFF_TIME,
    CONF_APPLIANCE_NAME, CONF_POWER_SENSOR, CONF_SWITCH_ENTITY,
    CONF_TRIGGER_ENTITY, CONF_VACUUM_ENTITY, CONF_BATTERY_SENSOR, CONF_VACUUM_RETURN_PCT,
    CONF_WORK_THRESHOLD_W, CONF_TRIGGER_DELAY_M, CONF_START_DELAY_S,
    CONF_CUSTOM_MESSAGE, CONF_SOURCE_UNIT, CONF_TOTAL_UNIT,
    CONF_SCHEDULE_OVERRIDE, CONF_AUTO_ON_LOCAL, CONF_AUTO_OFF_LOCAL,
    CONF_NOTIFY_PUSH, CONF_NOTIFY_ALEXA, CONF_NOTIFY_GOOGLE, CONF_NOTIFY_WHATSAPP,
    CONF_IMAGE_ON, CONF_IMAGE_OFF,
    CONF_POWER_SENSOR_2, CONF_POWER_SHARE,
    CONF_ZONES, CONF_ZONE_ORDER, CONF_FLOW_SENSOR, CONF_PUMP_SENSOR,
    CONF_METEO_ENTITY, CONF_IRR_SCHEDULE_1, CONF_IRR_SCHEDULE_2, CONF_IRR_SCHEDULE_3,
    ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE,
    DEFAULT_THRESHOLD_W, DEFAULT_TRIGGER_DELAY_M, DEFAULT_START_DELAY_S,
    DEFAULT_COST, DEFAULT_NOTIFY_START, DEFAULT_NOTIFY_END, DEFAULT_SCHEDULE,
)
from .presets import PRESET_IDS, PRESET_LABELS, get_preset

# ── Selectors ─────────────────────────────────────────────────────────────────
_SEL_SENSOR      = selector.selector({"entity": {"domain": "sensor"}})
_SEL_SENSOR_OPT  = selector.selector({"entity": {"domain": "sensor"}})
_SEL_VACUUM      = selector.selector({"entity": {"domain": "vacuum"}})
_SEL_SWITCH      = selector.selector({"entity": {"domain": ["switch", "input_boolean"]}})
_SEL_ANY_ENTITY  = selector.selector({"entity": {}})
_SEL_INPUT_TEXT  = selector.selector({"entity": {"domain": "input_text"}})
_SEL_NOTIFY_MULTI= selector.selector({"entity": {"domain": "notify",       "multiple": True}})
_SEL_MEDIA_MULTI = selector.selector({"entity": {"domain": "media_player", "multiple": True}})
_SEL_TIME        = selector.selector({"time": {}})
_SEL_TEXT        = selector.selector({"text": {}})
_SEL_BOOL        = selector.selector({"boolean": {}})
_SEL_NUM_INT     = selector.selector({"number": {"mode": "box", "min": 0, "max": 9999, "step": 1}})
_SEL_PCT         = selector.selector({"number": {"mode": "slider", "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"}})
_SEL_NUM_FLOAT   = selector.selector({"number": {"mode": "box", "min": 0, "max": 9999, "step": 0.001}})
_SEL_SLOT        = selector.selector({"number": {"mode": "box", "min": 1, "max": 999,  "step": 1}})
# Only show user-facing presets in config flow (hidden presets excluded)
_PRESET_IDS_UI = [
    "elettrodomestico", "acqua", "gas", "vacuum", "clima", "irrigazione", "dispositivo", "generico"
]
_PRESET_HUB_ONLY = "hub_only"  # special value: finish after hub, no device
_SEL_PRESET = selector.selector({"select": {"options":
    [{"value": _PRESET_HUB_ONLY, "label": "✅ Solo Hub (aggiungi device dopo)"}] +
    [{"value": pid, "label": PRESET_LABELS[pid]}
     for pid in _PRESET_IDS_UI
     if pid in PRESET_LABELS]
}})
_SEL_ICON        = selector.selector({"icon": {}})



_SEL_DAYS = selector.selector({"select": {
    "multiple": True,
    "options": [
        {"value": "lunedi",    "label": "Lunedì"},
        {"value": "martedi",   "label": "Martedì"},
        {"value": "mercoledi", "label": "Mercoledì"},
        {"value": "giovedi",   "label": "Giovedì"},
        {"value": "venerdi",   "label": "Venerdì"},
        {"value": "sabato",    "label": "Sabato"},
        {"value": "domenica",  "label": "Domenica"},
    ],
}})

_SEL_IRR_MODE = selector.selector({"select": {"options": [
    {"value": "fixed",   "label": "Orario fisso"},
    {"value": "sunrise", "label": "Alba"},
    {"value": "sunset",  "label": "Tramonto"},
]}})

def _scan_www_images_sync(www: str) -> list[str]:
    """Sync scan — must be called in executor, NOT in event loop."""
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
    paths = []
    try:
        for root, dirs, files in _os.walk(www):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in sorted(files):
                if any(fname.lower().endswith(ext) for ext in exts):
                    rel = _os.path.relpath(_os.path.join(root, fname), www)
                    paths.append(f"/local/{rel.replace(_os.sep, '/')}")
    except Exception:
        pass
    return paths


# Cache: images are scanned once per HA session to avoid repeated blocking calls
_www_images_cache: list[str] = []

async def _scan_www_images_async(hass) -> list[str]:
    """Scan /config/www in executor thread. Returns /local/... paths."""
    global _www_images_cache
    if not _www_images_cache:
        www = hass.config.path("www")
        _www_images_cache = await hass.async_add_executor_job(
            _scan_www_images_sync, www)
    return _www_images_cache


def _image_selector_cached(images: list[str]) -> dict:
    """Build selector from pre-fetched image list."""
    return selector.selector({
        "select": {
            "options": images or [],
            "custom_value": True,
            "mode": "dropdown",
            "sort": False,
        }
    })


def _image_selector(hass) -> dict:
    """Sync fallback — returns empty selector. Use _image_selector_cached with async scan."""
    return _image_selector_cached(_www_images_cache)


def _hub_entry(hass):
    for e in hass.config_entries.async_entries(DOMAIN):
        if e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
            return e
    return None


def _used_slots(hass) -> set[int]:
    # Slots must be unique across ALL device types (appliance, device/battery,
    # irrigation) — not just appliances. Counting only appliances let a new
    # appliance reuse a slot already taken by a battery/irrigation device.
    _types = {ENTRY_TYPE_APPLIANCE, ENTRY_TYPE_DEVICE, ENTRY_TYPE_IRRIGATION}
    used: set[int] = set()
    for e in hass.config_entries.async_entries(DOMAIN):
        et = e.data.get(CONF_ENTRY_TYPE) or e.data.get("entry_type")
        if et in _types:
            try:
                used.add(int(e.data.get(CONF_SLOT, 0)))
            except (ValueError, TypeError):
                pass
    return used


def _next_free_slot(hass) -> int:
    used = _used_slots(hass); i = 1
    while i in used: i += 1
    return i


def _clean_entity(val) -> str:
    if not val or str(val).strip() in ("", "None", "none"): return ""
    return str(val).strip()


def _clean_hub_data(data: dict) -> dict:
    for key in (CONF_COSTO_KWH_SENSOR, CONF_COSTO_ACQUA_SENSOR,
                CONF_COSTO_GAS_SENSOR, CONF_VENDITA_KWH_SENSOR,
                CONF_FV_GRID_SENSOR,
                CONF_WHATSAPP_ENTITY):
        data[key] = _clean_entity(data.get(key))
    return data


def _clean_appl_data(data: dict) -> dict:
    data[CONF_SWITCH_ENTITY]  = _clean_entity(data.get(CONF_SWITCH_ENTITY))
    data[CONF_TRIGGER_ENTITY] = _clean_entity(data.get(CONF_TRIGGER_ENTITY))
    data[CONF_VACUUM_ENTITY]  = _clean_entity(data.get(CONF_VACUUM_ENTITY))
    data[CONF_BATTERY_SENSOR] = _clean_entity(data.get(CONF_BATTERY_SENSOR))
    data[CONF_IMAGE_ON]      = (data.get(CONF_IMAGE_ON)  or "").strip()
    data[CONF_IMAGE_OFF]     = (data.get(CONF_IMAGE_OFF) or "").strip()
    data[CONF_POWER_SENSOR_2] = _clean_entity(data.get(CONF_POWER_SENSOR_2))

    data[CONF_POWER_SENSOR]   = _clean_entity(data.get(CONF_POWER_SENSOR))
    return data


def _entity_schema_field(key, value):
    """vol.Optional with default only if value is non-empty — never passes None to selector."""
    v = _clean_entity(value)
    if v:
        return vol.Optional(key, default=v)
    return vol.Optional(key)


def _is_vacuum_preset(preset_id: str) -> bool:
    return preset_id == "vacuum"


# ═══════════════════════════════════════════════════════════════════════════════
class ElettrodomesticoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._hub: dict = {}
        self._appl: dict = {}
        self._need_hub = False
        self._preset_id = "elettrodomestico"

    async def async_step_user(self, ui=None):
        if _hub_entry(self.hass) is None:
            self._need_hub = True
            return await self.async_step_hub_costs()
        return await self.async_step_preset_select()

    async def async_step_import(self, data):
        """Import flow: recreates an entry from exported data, preserving its type."""
        import uuid as _uuid
        from .const import ENTRY_TYPE_DEVICE, ENTRY_TYPE_IRRIGATION
        data = dict(data)
        # Preserve the original entry type (device / irrigation / appliance)
        et = data.get(CONF_ENTRY_TYPE) or data.get("entry_type") or ENTRY_TYPE_APPLIANCE
        data[CONF_ENTRY_TYPE] = et
        data["entry_type"]    = et
        data.setdefault(CONF_INSTANCE_ID, _uuid.uuid4().hex[:12])
        slot = data.get(CONF_SLOT, "?")
        name = data.get(CONF_APPLIANCE_NAME, "Device")
        # Title prefix matching each type
        if et == ENTRY_TYPE_DEVICE or et == "device":
            title = f"(x{slot}) 🔋 {name}"
        elif et == ENTRY_TYPE_IRRIGATION or et == "irrigation":
            title = f"(x{slot}) {name}"
        else:
            title = f"(x{slot}) {name}"
        return self.async_create_entry(title=title, data=data)

    # ── HUB ──────────────────────────────────────────────────────────────────
    async def async_step_hub_costs(self, ui=None):
        if ui is not None:
            self._hub.update(_clean_hub_data(dict(ui)))
            return await self.async_step_hub_notifications()
        return self.async_show_form(
            step_id="hub_costs",
            data_schema=vol.Schema({
                vol.Optional(CONF_COSTO_KWH,   default=DEFAULT_COST): _SEL_NUM_FLOAT,
                vol.Optional(CONF_COSTO_KWH_SENSOR):                  _SEL_SENSOR_OPT,
                vol.Optional(CONF_COSTO_ACQUA, default=DEFAULT_COST): _SEL_NUM_FLOAT,
                vol.Optional(CONF_COSTO_ACQUA_SENSOR):                _SEL_SENSOR_OPT,
                vol.Optional(CONF_COSTO_GAS,   default=DEFAULT_COST): _SEL_NUM_FLOAT,
                vol.Optional(CONF_COSTO_GAS_SENSOR):                  _SEL_SENSOR_OPT,
                vol.Optional(CONF_VENDITA_KWH, default=DEFAULT_COST): _SEL_NUM_FLOAT,
                vol.Optional(CONF_VENDITA_KWH_SENSOR):                _SEL_SENSOR_OPT,
                vol.Optional(CONF_FV_ENABLED, default=False):         _SEL_BOOL,
                vol.Optional(CONF_FV_GRID_SENSOR):                    _SEL_SENSOR_OPT,
                vol.Optional(CONF_FV_INVERT, default=False):          _SEL_BOOL,
                vol.Optional(CONF_FV_THRESHOLD_W, default=DEFAULT_FV_THRESHOLD): _SEL_NUM_FLOAT,
            }),
        )

    async def async_step_hub_notifications(self, ui=None):
        if ui is not None:
            data = dict(ui)
            data[CONF_WHATSAPP_ENTITY] = _clean_entity(data.get(CONF_WHATSAPP_ENTITY))
            self._hub.update(data)
            return await self.async_step_hub_schedule()
        return self.async_show_form(
            step_id="hub_notifications",
            data_schema=vol.Schema({
                vol.Optional(CONF_NOTIFY_START_TIME, default=DEFAULT_NOTIFY_START): _SEL_TIME,
                vol.Optional(CONF_NOTIFY_END_TIME,   default=DEFAULT_NOTIFY_END):   _SEL_TIME,
                vol.Optional(CONF_PUSH_TARGETS,      default=[]):  _SEL_NOTIFY_MULTI,
                vol.Optional(CONF_ALEXA_TARGETS,     default=[]):  _SEL_MEDIA_MULTI,
                vol.Optional(CONF_GOOGLE_TARGETS,    default=[]):  _SEL_MEDIA_MULTI,
                vol.Optional(CONF_WHATSAPP_ENTITY):                _SEL_INPUT_TEXT,
                vol.Optional(CONF_METEO_ENTITY):                  selector.selector({"entity": {"domain": "binary_sensor"}}),
            }),
        )

    async def async_step_hub_schedule(self, ui=None):
        if ui is not None:
            self._hub.update(ui)
            return await self.async_step_preset_select()
        return self.async_show_form(
            step_id="hub_schedule",
            data_schema=vol.Schema({
                vol.Optional(CONF_AUTO_ON_TIME,  default=DEFAULT_SCHEDULE): _SEL_TIME,
                vol.Optional(CONF_AUTO_OFF_TIME, default=DEFAULT_SCHEDULE): _SEL_TIME,
            }),
        )

    # ── DEVICE: preset selection ──────────────────────────────────────────────
    async def async_step_preset_select(self, ui=None):
        if ui is not None:
            self._preset_id = ui[CONF_PRESET]
            # Hub-only: finish config flow without creating a device
            if self._preset_id == _PRESET_HUB_ONLY:
                if self._need_hub:
                    # Create hub entry directly with data collected in previous steps
                    hub_data = {
                        **self._hub,
                        CONF_ENTRY_TYPE:  ENTRY_TYPE_HUB,
                        CONF_INSTANCE_ID: "hub",
                    }
                    return self.async_create_entry(
                        title="⚙️ Hub Globale",
                        data=hub_data,
                    )
                # Hub already exists — user just closed the flow
                return self.async_abort(reason="hub_only_selected")
            self._appl[CONF_PRESET] = self._preset_id
            if _is_vacuum_preset(self._preset_id):
                return await self.async_step_vacuum()
            if self._preset_id == "irrigazione":
                return await self.async_step_irrigation()
            if self._preset_id == "dispositivo":
                return await self.async_step_device()
            return await self.async_step_appliance()
        return self.async_show_form(
            step_id="preset_select",
            data_schema=vol.Schema({
                vol.Required(CONF_PRESET, default="elettrodomestico"): _SEL_PRESET,
            }),
        )

    # ── DEVICE: vacuum-specific setup ─────────────────────────────────────────
    async def async_step_vacuum(self, ui=None):
        errors: dict = {}
        _images = await _scan_www_images_async(self.hass)
        if ui is not None:
            vacuum = _clean_entity(ui.get(CONF_VACUUM_ENTITY))
            if not vacuum or not self.hass.states.get(vacuum):
                errors[CONF_VACUUM_ENTITY] = "entity_not_found"
            else:
                slot = int(ui.get(CONF_SLOT, 1))
                if slot in _used_slots(self.hass):
                    errors[CONF_SLOT] = "slot_taken"
                else:
                    data = _clean_appl_data(dict(ui))
                    # For vacuum: use vacuum entity as trigger, no real power sensor
                    data[CONF_TRIGGER_ENTITY] = vacuum
                    data[CONF_POWER_SENSOR]   = ""  # no power sensor for vacuum
                    self._appl.update(data)
                    self._appl[CONF_SLOT] = slot
                    return await self.async_step_appliance_advanced()

        return self.async_show_form(
            step_id="vacuum",
            data_schema=vol.Schema({
                vol.Required(CONF_SLOT,            default=_next_free_slot(self.hass)): _SEL_SLOT,
                vol.Required(CONF_APPLIANCE_NAME):                                      _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON,     default="mdi:robot-vacuum"):        _SEL_ICON,
                vol.Required(CONF_VACUUM_ENTITY):                                       _SEL_VACUUM,
                vol.Optional(CONF_BATTERY_SENSOR):                                     _SEL_SENSOR_OPT,
                vol.Optional(CONF_VACUUM_RETURN_PCT, default=0):                       _SEL_PCT,
                vol.Optional(CONF_IMAGE_ON):                                            _image_selector_cached(_images),
                vol.Optional(CONF_IMAGE_OFF):                                           _image_selector_cached(_images),
                vol.Optional(CONF_TRIGGER_DELAY_M, default=float(DEFAULT_TRIGGER_DELAY_M)): _SEL_NUM_INT,
                vol.Optional(CONF_CUSTOM_MESSAGE,  default=""):                        _SEL_TEXT,
                vol.Optional(CONF_NOTIFY_PUSH,     default=False):                     _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_ALEXA,    default=False):                     _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_GOOGLE,   default=False):                     _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_WHATSAPP, default=False):                     _SEL_BOOL,
            }),
            errors=errors,
        )

    # ── DEVICE: standard appliance setup ─────────────────────────────────────
    async def async_step_appliance(self, ui=None):
        errors: dict = {}
        preset = get_preset(self._preset_id)
        _images = await _scan_www_images_async(self.hass)
        if ui is not None:
            slot    = int(ui.get(CONF_SLOT, 1))
            trigger = _clean_entity(ui.get(CONF_TRIGGER_ENTITY))
            power   = _clean_entity(ui.get(CONF_POWER_SENSOR))
            if slot in _used_slots(self.hass):
                errors[CONF_SLOT] = "slot_taken"
            elif not power and not trigger:
                errors[CONF_POWER_SENSOR] = "entity_not_found"
            elif power and not self.hass.states.get(power):
                errors[CONF_POWER_SENSOR] = "entity_not_found"
            else:
                if not power:
                    ui = dict(ui); ui[CONF_POWER_SENSOR] = trigger
                self._appl.update(_clean_appl_data(dict(ui)))
                self._appl[CONF_SLOT] = slot
                return await self.async_step_appliance_advanced()

        return self.async_show_form(
            step_id="appliance",
            data_schema=vol.Schema({
                vol.Required(CONF_SLOT,            default=_next_free_slot(self.hass)): _SEL_SLOT,
                vol.Required(CONF_APPLIANCE_NAME):                                      _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON,     default=preset.default_icon):       _SEL_ICON,
                vol.Optional(CONF_POWER_SENSOR):                                        _SEL_SENSOR,
                vol.Optional(CONF_SWITCH_ENTITY):                                       _SEL_SWITCH,
                vol.Optional(CONF_TRIGGER_ENTITY):                                      _SEL_ANY_ENTITY,
                vol.Optional(CONF_SOURCE_UNIT,     default=preset.source_unit):        _SEL_TEXT,
                vol.Optional(CONF_TOTAL_UNIT,      default=preset.total_unit):         _SEL_TEXT,
                vol.Optional(CONF_WORK_THRESHOLD_W,default=float(DEFAULT_THRESHOLD_W)):     _SEL_NUM_FLOAT,
                vol.Optional(CONF_TRIGGER_DELAY_M, default=float(DEFAULT_TRIGGER_DELAY_M)): _SEL_NUM_INT,
                vol.Optional(CONF_START_DELAY_S,   default=float(DEFAULT_START_DELAY_S)):   _SEL_NUM_INT,
                vol.Optional(CONF_CUSTOM_MESSAGE,  default=""):                         _SEL_TEXT,
                vol.Optional(CONF_IMAGE_ON):                                              _image_selector_cached(_images),
                vol.Optional(CONF_IMAGE_OFF):                                             _image_selector_cached(_images),
                vol.Optional(CONF_POWER_SENSOR_2):                                        _SEL_SENSOR_OPT,
                vol.Optional(CONF_BATTERY_SENSOR):                                       _SEL_SENSOR_OPT,
                vol.Optional(CONF_NOTIFY_PUSH,     default=False):                      _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_ALEXA,    default=False):                      _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_GOOGLE,   default=False):                      _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_WHATSAPP, default=False):                      _SEL_BOOL,
            }),
            errors=errors,
        )

    async def async_step_appliance_advanced(self, ui=None):
        if ui is not None:
            self._appl.update(ui)
            return self._finalize()
        return self.async_show_form(
            step_id="appliance_advanced",
            data_schema=vol.Schema({
                vol.Optional(CONF_SCHEDULE_OVERRIDE, default=False):            _SEL_BOOL,
                vol.Optional(CONF_AUTO_ON_LOCAL,     default=DEFAULT_SCHEDULE): _SEL_TIME,
                vol.Optional(CONF_AUTO_OFF_LOCAL,    default=DEFAULT_SCHEDULE): _SEL_TIME,
            }),
        )

    # ── IRRIGATION FLOW ──────────────────────────────────────────────────────

    async def async_step_irrigation(self, ui=None):
        """Step 1: irrigation basics — sensors and number of zones."""
        errors: dict = {}
        if ui is not None:
            slot = int(ui.get(CONF_SLOT, 1))
            if slot in _used_slots(self.hass):
                errors[CONF_SLOT] = "slot_taken"
            else:
                self._appl.update({
                    CONF_SLOT:           slot,
                    CONF_APPLIANCE_NAME: ui.get(CONF_APPLIANCE_NAME, "Irrigazione"),
                    CONF_DEVICE_ICON:    ui.get(CONF_DEVICE_ICON, "mdi:sprinkler-variant"),
                    CONF_FLOW_SENSOR:    _clean_entity(ui.get(CONF_FLOW_SENSOR)),
                    CONF_PUMP_SENSOR:    _clean_entity(ui.get(CONF_PUMP_SENSOR)),
                    CONF_METEO_ENTITY:   _clean_entity(ui.get(CONF_METEO_ENTITY)),
                    "_num_zones":        int(ui.get("_num_zones", 1)),
                    "entry_type":        ENTRY_TYPE_IRRIGATION,
                })
                self._appl["_zone_step"] = 0
                self._appl[CONF_ZONES] = []
                return await self.async_step_irrigation_zone()

        return self.async_show_form(
            step_id="irrigation",
            data_schema=vol.Schema({
                vol.Required(CONF_SLOT,            default=_next_free_slot(self.hass)): _SEL_SLOT,
                vol.Required(CONF_APPLIANCE_NAME):                                       _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON, default="mdi:sprinkler-variant"):        _SEL_ICON,
                vol.Required(CONF_FLOW_SENSOR):                                          _SEL_SENSOR,
                vol.Optional(CONF_PUMP_SENSOR):                                          _SEL_SENSOR_OPT,
                vol.Optional(CONF_METEO_ENTITY):    selector.selector({"entity": {"domain": "binary_sensor"}}),
                vol.Required("_num_zones", default=1): selector.selector(
                    {"number": {"mode": "box", "min": 1, "max": 8, "step": 1}}),
            }),
            errors=errors,
        )

    async def async_step_device(self, ui=None):
        """Battery device: battery sensor, charge switch, thresholds."""
        from .const import (CONF_DEV_BATTERY_SENSOR, CONF_DEV_CHARGE_SWITCH,
                            CONF_DEV_START_PCT, CONF_DEV_STOP_PCT,
                            DEFAULT_DEV_START_PCT, DEFAULT_DEV_STOP_PCT, ENTRY_TYPE_DEVICE)
        self._dev_images = await _scan_www_images_async(self.hass)
        errors: dict = {}
        if ui is not None:
            slot = int(ui.get(CONF_SLOT, 1))
            bsens = _clean_entity(ui.get(CONF_DEV_BATTERY_SENSOR))
            csw   = _clean_entity(ui.get(CONF_DEV_CHARGE_SWITCH))
            if slot in _used_slots(self.hass):
                errors[CONF_SLOT] = "slot_taken"
            elif not bsens or not self.hass.states.get(bsens):
                errors[CONF_DEV_BATTERY_SENSOR] = "entity_not_found"
            else:
                data = {
                    CONF_SLOT:           slot,
                    CONF_APPLIANCE_NAME: ui.get(CONF_APPLIANCE_NAME, "Dispositivo"),
                    CONF_DEVICE_ICON:    ui.get(CONF_DEVICE_ICON, "mdi:battery-charging"),
                    CONF_PRESET:         "dispositivo",
                    CONF_DEV_BATTERY_SENSOR: bsens,
                    CONF_DEV_CHARGE_SWITCH:  csw,
                    CONF_DEV_START_PCT:  int(ui.get(CONF_DEV_START_PCT, DEFAULT_DEV_START_PCT)),
                    CONF_DEV_STOP_PCT:   int(ui.get(CONF_DEV_STOP_PCT, DEFAULT_DEV_STOP_PCT)),
                    CONF_IMAGE_ON:       (ui.get(CONF_IMAGE_ON)  or "").strip(),
                    CONF_IMAGE_OFF:      (ui.get(CONF_IMAGE_OFF) or "").strip(),
                    CONF_NOTIFY_PUSH:    ui.get(CONF_NOTIFY_PUSH, False),
                    CONF_NOTIFY_ALEXA:   ui.get(CONF_NOTIFY_ALEXA, False),
                    CONF_NOTIFY_GOOGLE:  ui.get(CONF_NOTIFY_GOOGLE, False),
                    CONF_NOTIFY_WHATSAPP:ui.get(CONF_NOTIFY_WHATSAPP, False),
                    CONF_INSTANCE_ID:    uuid.uuid4().hex[:12],
                    CONF_ENTRY_TYPE:     ENTRY_TYPE_DEVICE,
                    "entry_type":        ENTRY_TYPE_DEVICE,
                }
                return self.async_create_entry(
                    title=f"(x{slot}) 🔋 {data[CONF_APPLIANCE_NAME]}", data=data)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({
                vol.Required(CONF_SLOT, default=_next_free_slot(self.hass)): _SEL_SLOT,
                vol.Required(CONF_APPLIANCE_NAME): _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON, default="mdi:battery-charging"): _SEL_ICON,
                vol.Required(CONF_DEV_BATTERY_SENSOR): _SEL_SENSOR,
                vol.Optional(CONF_DEV_CHARGE_SWITCH): selector.selector({"entity": {"domain": "switch"}}),
                vol.Optional(CONF_DEV_START_PCT, default=DEFAULT_DEV_START_PCT): _SEL_NUM_INT,
                vol.Optional(CONF_DEV_STOP_PCT,  default=DEFAULT_DEV_STOP_PCT):  _SEL_NUM_INT,
                vol.Optional(CONF_IMAGE_ON):  _image_selector_cached(self._dev_images),
                vol.Optional(CONF_IMAGE_OFF): _image_selector_cached(self._dev_images),
                vol.Optional(CONF_NOTIFY_PUSH,     default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_ALEXA,    default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_GOOGLE,   default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_WHATSAPP, default=False): _SEL_BOOL,
            }),
            errors=errors,
        )

    async def async_step_irrigation_zone(self, ui=None):
        """Step 2+: configure each zone."""
        step_num  = self._appl.get("_zone_step", 0)
        num_zones = self._appl.get("_num_zones", 1)
        errors: dict = {}

        if ui is not None:
            sw = _clean_entity(ui.get("zone_switch"))
            if sw and not self.hass.states.get(sw):
                errors["zone_switch"] = "entity_not_found"
            else:
                self._appl[CONF_ZONES].append({
                    "name":         ui.get("zone_name", f"Zona {step_num + 1}"),
                    "switch":       sw,
                    "duration_min": float(ui.get("zone_duration", 10)),
                })
                self._appl["_zone_step"] = step_num + 1
                if step_num + 1 < num_zones:
                    return await self.async_step_irrigation_zone()
                # All zones done → set default order
                self._appl[CONF_ZONE_ORDER] = list(range(num_zones))
                return await self.async_step_irrigation_schedule()

        return self.async_show_form(
            step_id="irrigation_zone",
            description_placeholders={
                "zone_num":   str(step_num + 1),
                "total":      str(num_zones),
            },
            data_schema=vol.Schema({
                vol.Required("zone_name", default=f"Zona {step_num + 1}"): _SEL_TEXT,
                vol.Optional("zone_switch"):  _SEL_SWITCH,
                vol.Optional("zone_duration", default=10.0): selector.selector(
                    {"number": {"mode": "box", "min": 1, "max": 180, "step": 1}}),
            }),
            errors=errors,
        )

    async def async_step_irrigation_schedule(self, ui=None):
        """Step 3: configure up to 3 schedules."""
        if ui is not None:
            def _parse_sched(n):
                mode = ui.get(f"s{n}_mode", "fixed")
                t    = str(ui.get(f"s{n}_time") or "00:00:00")
                days = list(ui.get(f"s{n}_days") or [])
                off  = int(ui.get(f"s{n}_offset", 0))
                # Always save — even with no days yet (days added via switch entities)
                return {"time": t, "days": days, "mode": mode, "offset_min": off}

            s1 = _parse_sched(1); s2 = _parse_sched(2); s3 = _parse_sched(3)
            self._appl[CONF_IRR_SCHEDULE_1] = s1
            self._appl[CONF_IRR_SCHEDULE_2] = s2
            self._appl[CONF_IRR_SCHEDULE_3] = s3
            return self._finalize_irrigation()

        return self.async_show_form(
            step_id="irrigation_schedule",
            data_schema=vol.Schema({
                # Schedule 1
                vol.Optional("s1_time"):             _SEL_TIME,
                vol.Optional("s1_days", default=[]): _SEL_DAYS,
                vol.Optional("s1_mode", default="fixed"): _SEL_IRR_MODE,
                vol.Optional("s1_offset", default=0): selector.selector(
                    {"number": {"mode": "box", "min": -120, "max": 120, "step": 5}}),
                # Schedule 2
                vol.Optional("s2_time"):             _SEL_TIME,
                vol.Optional("s2_days", default=[]): _SEL_DAYS,
                vol.Optional("s2_mode", default="fixed"): _SEL_IRR_MODE,
                vol.Optional("s2_offset", default=0): selector.selector(
                    {"number": {"mode": "box", "min": -120, "max": 120, "step": 5}}),
                # Schedule 3
                vol.Optional("s3_time"):             _SEL_TIME,
                vol.Optional("s3_days", default=[]): _SEL_DAYS,
                vol.Optional("s3_mode", default="fixed"): _SEL_IRR_MODE,
                vol.Optional("s3_offset", default=0): selector.selector(
                    {"number": {"mode": "box", "min": -120, "max": 120, "step": 5}}),
                # Notifications
                vol.Optional(CONF_NOTIFY_PUSH,     default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_ALEXA,    default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_GOOGLE,   default=False): _SEL_BOOL,
                vol.Optional(CONF_NOTIFY_WHATSAPP, default=False): _SEL_BOOL,
            }),
        )

    def _finalize_irrigation(self):
        import uuid as _uuid
        # Clean up temp keys
        appl = dict(self._appl)
        for k in ("_zone_step", "_num_zones"):
            appl.pop(k, None)
        appl.setdefault(CONF_INSTANCE_ID, _uuid.uuid4().hex[:12])
        appl["entry_type"] = ENTRY_TYPE_IRRIGATION
        name = appl.get(CONF_APPLIANCE_NAME, "Irrigazione")
        slot = appl.get(CONF_SLOT, 1)
        return self.async_create_entry(title=f"(x{slot}) {name}", data=appl)

    def _finalize(self):
        if not self._appl.get(CONF_CUSTOM_MESSAGE, "").strip():
            self._appl[CONF_CUSTOM_MESSAGE] = (
                self._appl.get(CONF_APPLIANCE_NAME, "Elettrodomestico") + " completata"
            )
        appl = {
            CONF_ENTRY_TYPE:  ENTRY_TYPE_APPLIANCE,
            CONF_INSTANCE_ID: str(uuid.uuid4()).replace("-", "")[:12],
            **self._appl,
        }
        if self._need_hub:
            appl["_pending_hub"] = {
                CONF_ENTRY_TYPE:  ENTRY_TYPE_HUB,
                CONF_INSTANCE_ID: "hub",
                **self._hub,
            }
        name = self._appl.get(CONF_APPLIANCE_NAME, "Device")
        slot = self._appl.get(CONF_SLOT, 1)
        return self.async_create_entry(title=f"(x{slot}) {name}", data=appl)

    async def async_step_hub_import(self, data: dict):
        return self.async_create_entry(title="⚙️ Hub Globale", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
            return HubOptionsFlow(config_entry)
        if (config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or
                config_entry.data.get("entry_type") == "irrigation"):
            return IrrigationOptionsFlow(config_entry)
        from .const import ENTRY_TYPE_DEVICE
        if (config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or
                config_entry.data.get("entry_type") == "device"):
            return DeviceOptionsFlow(config_entry)
        if config_entry.data.get(CONF_PRESET) == "vacuum":
            return VacuumOptionsFlow(config_entry)
        return ApplianceOptionsFlow(config_entry)


# ═══════════════════════════════════════════════════════════════════════════════
class HubOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, e): self._entry = e; self._data = dict(e.data)

    async def async_step_init(self, ui=None): return await self.async_step_hub_costs(ui)

    async def async_step_hub_costs(self, ui=None):
        if ui is not None:
            self._data.update(_clean_hub_data(dict(ui)))
            return await self.async_step_hub_notifications()
        c = self._data
        return self.async_show_form(step_id="hub_costs", data_schema=vol.Schema({
            vol.Optional(CONF_COSTO_KWH,   default=c.get(CONF_COSTO_KWH,   DEFAULT_COST)): _SEL_NUM_FLOAT,
            _entity_schema_field(CONF_COSTO_KWH_SENSOR,   c.get(CONF_COSTO_KWH_SENSOR)):   _SEL_SENSOR_OPT,
            vol.Optional(CONF_COSTO_ACQUA, default=c.get(CONF_COSTO_ACQUA, DEFAULT_COST)): _SEL_NUM_FLOAT,
            _entity_schema_field(CONF_COSTO_ACQUA_SENSOR, c.get(CONF_COSTO_ACQUA_SENSOR)): _SEL_SENSOR_OPT,
            vol.Optional(CONF_COSTO_GAS,   default=c.get(CONF_COSTO_GAS,   DEFAULT_COST)): _SEL_NUM_FLOAT,
            _entity_schema_field(CONF_COSTO_GAS_SENSOR,   c.get(CONF_COSTO_GAS_SENSOR)):   _SEL_SENSOR_OPT,
            vol.Optional(CONF_VENDITA_KWH, default=c.get(CONF_VENDITA_KWH, DEFAULT_COST)): _SEL_NUM_FLOAT,
            _entity_schema_field(CONF_VENDITA_KWH_SENSOR, c.get(CONF_VENDITA_KWH_SENSOR)): _SEL_SENSOR_OPT,
            vol.Optional(CONF_FV_ENABLED, default=c.get(CONF_FV_ENABLED, False)): _SEL_BOOL,
            _entity_schema_field(CONF_FV_GRID_SENSOR, c.get(CONF_FV_GRID_SENSOR)): _SEL_SENSOR_OPT,
            vol.Optional(CONF_FV_INVERT, default=c.get(CONF_FV_INVERT, False)): _SEL_BOOL,
            vol.Optional(CONF_FV_THRESHOLD_W, default=c.get(CONF_FV_THRESHOLD_W, DEFAULT_FV_THRESHOLD)): _SEL_NUM_FLOAT,
        }))

    async def async_step_hub_notifications(self, ui=None):
        if ui is not None:
            data = dict(ui); data[CONF_WHATSAPP_ENTITY] = _clean_entity(data.get(CONF_WHATSAPP_ENTITY))
            self._data.update(data)
            return await self.async_step_hub_schedule()
        c = self._data
        return self.async_show_form(step_id="hub_notifications", data_schema=vol.Schema({
            vol.Optional(CONF_NOTIFY_START_TIME, default=c.get(CONF_NOTIFY_START_TIME, DEFAULT_NOTIFY_START)): _SEL_TIME,
            vol.Optional(CONF_NOTIFY_END_TIME,   default=c.get(CONF_NOTIFY_END_TIME,   DEFAULT_NOTIFY_END)):   _SEL_TIME,
            vol.Optional(CONF_PUSH_TARGETS,      default=c.get(CONF_PUSH_TARGETS,  []) or []): _SEL_NOTIFY_MULTI,
            vol.Optional(CONF_ALEXA_TARGETS,     default=c.get(CONF_ALEXA_TARGETS, []) or []): _SEL_MEDIA_MULTI,
            vol.Optional(CONF_GOOGLE_TARGETS,    default=c.get(CONF_GOOGLE_TARGETS,[]) or []): _SEL_MEDIA_MULTI,
            _entity_schema_field(CONF_WHATSAPP_ENTITY, c.get(CONF_WHATSAPP_ENTITY)):            _SEL_INPUT_TEXT,
        }))

    async def async_step_hub_schedule(self, ui=None):
        if ui is not None:
            self._data.update(ui)
            self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data={})
        c = self._data
        return self.async_show_form(step_id="hub_schedule", data_schema=vol.Schema({
            vol.Optional(CONF_AUTO_ON_TIME,  default=c.get(CONF_AUTO_ON_TIME,  DEFAULT_SCHEDULE)): _SEL_TIME,
            vol.Optional(CONF_AUTO_OFF_TIME, default=c.get(CONF_AUTO_OFF_TIME, DEFAULT_SCHEDULE)): _SEL_TIME,
        }))


# ═══════════════════════════════════════════════════════════════════════════════
class VacuumOptionsFlow(config_entries.OptionsFlow):
    """Options flow dedicated to vacuum devices."""
    def __init__(self, e): self._entry = e; self._data = dict(e.data)

    async def async_step_init(self, ui=None):
        errors: dict = {}
        _images = await _scan_www_images_async(self.hass)
        if ui is not None:
            vacuum = _clean_entity(ui.get(CONF_VACUUM_ENTITY))
            if not vacuum or not self.hass.states.get(vacuum):
                errors[CONF_VACUUM_ENTITY] = "entity_not_found"
            else:
                data = _clean_appl_data(dict(ui))
                data[CONF_TRIGGER_ENTITY] = vacuum
                data[CONF_POWER_SENSOR]   = ""
                self._data.update(data)
                return await self.async_step_reset_confirm()
        c = self._data
        return self.async_show_form(
            step_id="init", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_APPLIANCE_NAME, default=c.get(CONF_APPLIANCE_NAME, "")): _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON,    default=c.get(CONF_DEVICE_ICON, "mdi:robot-vacuum")): _SEL_ICON,
                vol.Required(CONF_VACUUM_ENTITY,  default=c.get(CONF_VACUUM_ENTITY, c.get(CONF_TRIGGER_ENTITY, ""))): _SEL_VACUUM,
                _entity_schema_field(CONF_BATTERY_SENSOR, c.get(CONF_BATTERY_SENSOR)): _SEL_SENSOR_OPT,
                vol.Optional(CONF_VACUUM_RETURN_PCT, default=c.get(CONF_VACUUM_RETURN_PCT, 0)): _SEL_PCT,
                vol.Optional(CONF_IMAGE_ON,  default=c.get(CONF_IMAGE_ON, "")):  _image_selector_cached(_images),
                vol.Optional(CONF_IMAGE_OFF, default=c.get(CONF_IMAGE_OFF, "")): _image_selector_cached(_images),
                vol.Optional(CONF_TRIGGER_DELAY_M, default=c.get(CONF_TRIGGER_DELAY_M, DEFAULT_TRIGGER_DELAY_M)): _SEL_NUM_INT,
                vol.Optional(CONF_CUSTOM_MESSAGE,  default=c.get(CONF_CUSTOM_MESSAGE, "")): _SEL_TEXT,
                # Notification toggles managed via switch entities after creation
            }),
        )

    async def async_step_reset_confirm(self, ui=None):
        if ui is not None:
            do_reset = ui.get("reset_now", False)
            # Reset BEFORE updating the entry: async_update_entry triggers a
            # reload that recreates the coordinator and re-reads storage. If we
            # reset after (or as a background task) the reload races the reset
            # and historical data survives. Reset synchronously first.
            if do_reset:
                coord = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
                if coord and hasattr(coord, "async_reset_all"):
                    await coord.async_reset_all()
            self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="reset_confirm",
            data_schema=vol.Schema({vol.Optional("reset_now", default=False): _SEL_BOOL}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
class ApplianceOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, e): self._entry = e; self._data = dict(e.data)

    async def async_step_init(self, ui=None):
        errors: dict = {}
        _images = await _scan_www_images_async(self.hass)
        if ui is not None:
            power   = _clean_entity(ui.get(CONF_POWER_SENSOR))
            trigger = _clean_entity(ui.get(CONF_TRIGGER_ENTITY, self._data.get(CONF_TRIGGER_ENTITY,"")))
            if not power and not trigger:
                errors[CONF_POWER_SENSOR] = "entity_not_found"
            elif power and not self.hass.states.get(power):
                errors[CONF_POWER_SENSOR] = "entity_not_found"
            else:
                self._data.update(_clean_appl_data(dict(ui)))
                return await self.async_step_advanced()
        c = self._data
        preset = get_preset(c.get(CONF_PRESET, "elettrodomestico"))
        return self.async_show_form(
            step_id="init", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_APPLIANCE_NAME, default=c.get(CONF_APPLIANCE_NAME, "")): _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON,    default=c.get(CONF_DEVICE_ICON, preset.default_icon)): _SEL_ICON,
                _entity_schema_field(CONF_POWER_SENSOR,   c.get(CONF_POWER_SENSOR)):   _SEL_SENSOR,
                _entity_schema_field(CONF_SWITCH_ENTITY,  c.get(CONF_SWITCH_ENTITY)):  _SEL_SWITCH,
                _entity_schema_field(CONF_TRIGGER_ENTITY, c.get(CONF_TRIGGER_ENTITY)): _SEL_ANY_ENTITY,
            vol.Optional(CONF_IMAGE_ON,  default=c.get(CONF_IMAGE_ON,  "")): _image_selector_cached(_images),
            vol.Optional(CONF_IMAGE_OFF, default=c.get(CONF_IMAGE_OFF, "")): _image_selector_cached(_images),
            _entity_schema_field(CONF_POWER_SENSOR_2, c.get(CONF_POWER_SENSOR_2)): _SEL_SENSOR_OPT,
            _entity_schema_field(CONF_BATTERY_SENSOR, c.get(CONF_BATTERY_SENSOR)):  _SEL_SENSOR_OPT,
                vol.Optional(CONF_SOURCE_UNIT,    default=c.get(CONF_SOURCE_UNIT, preset.source_unit)): _SEL_TEXT,
                vol.Optional(CONF_TOTAL_UNIT,     default=c.get(CONF_TOTAL_UNIT,  preset.total_unit)):  _SEL_TEXT,
                vol.Optional(CONF_WORK_THRESHOLD_W, default=c.get(CONF_WORK_THRESHOLD_W, DEFAULT_THRESHOLD_W)):     _SEL_NUM_FLOAT,
                vol.Optional(CONF_TRIGGER_DELAY_M,  default=c.get(CONF_TRIGGER_DELAY_M, DEFAULT_TRIGGER_DELAY_M)): _SEL_NUM_INT,
                vol.Optional(CONF_START_DELAY_S,    default=c.get(CONF_START_DELAY_S,   DEFAULT_START_DELAY_S)):   _SEL_NUM_INT,
                vol.Optional(CONF_CUSTOM_MESSAGE,   default=c.get(CONF_CUSTOM_MESSAGE, "")): _SEL_TEXT,
                # Notification toggles are managed via the switch entities after creation
                # (single source of truth). They are intentionally not shown here.
            }),
        )

    async def async_step_advanced(self, ui=None):
        if ui is not None:
            self._data.update(ui)
            return await self.async_step_reset_confirm()
        c = self._data
        return self.async_show_form(step_id="advanced", data_schema=vol.Schema({
            vol.Optional(CONF_SCHEDULE_OVERRIDE, default=c.get(CONF_SCHEDULE_OVERRIDE, False)): _SEL_BOOL,
            vol.Optional(CONF_AUTO_ON_LOCAL,  default=c.get(CONF_AUTO_ON_LOCAL,  DEFAULT_SCHEDULE)): _SEL_TIME,
            vol.Optional(CONF_AUTO_OFF_LOCAL, default=c.get(CONF_AUTO_OFF_LOCAL, DEFAULT_SCHEDULE)): _SEL_TIME,
        }))

    async def async_step_reset_confirm(self, ui=None):
        if ui is not None:
            do_reset = ui.get("reset_now", False)
            # Reset BEFORE updating the entry: async_update_entry triggers a
            # reload that recreates the coordinator and re-reads storage. If we
            # reset after (or as a background task) the reload races the reset
            # and historical data survives. Reset synchronously first.
            if do_reset:
                coord = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
                if coord and hasattr(coord, "async_reset_all"):
                    await coord.async_reset_all()
            self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="reset_confirm",
            data_schema=vol.Schema({vol.Optional("reset_now", default=False): _SEL_BOOL}),
        )

# ═══════════════════════════════════════════════════════════════════════════════
class IrrigationOptionsFlow(config_entries.OptionsFlow):
    """Options flow for irrigation devices."""
    def __init__(self, e):
        self._entry = e
        self._data  = dict(e.data)
        self._num_zones = len(e.data.get(CONF_ZONES) or [])

    async def async_step_init(self, ui=None):
        """Step 1: edit basic settings + schedule times."""
        if ui is not None:
            self._data[CONF_APPLIANCE_NAME] = ui.get(CONF_APPLIANCE_NAME, self._data.get(CONF_APPLIANCE_NAME, ""))
            self._data[CONF_DEVICE_ICON]    = ui.get(CONF_DEVICE_ICON, self._data.get(CONF_DEVICE_ICON, "mdi:sprinkler-variant"))
            self._data[CONF_FLOW_SENSOR]    = _clean_entity(ui.get(CONF_FLOW_SENSOR))
            self._data[CONF_PUMP_SENSOR]    = _clean_entity(ui.get(CONF_PUMP_SENSOR))
            self._data[CONF_METEO_ENTITY]   = _clean_entity(ui.get(CONF_METEO_ENTITY))
            self._data[CONF_IMAGE_ON]       = (ui.get(CONF_IMAGE_ON,  self._data.get(CONF_IMAGE_ON,  "")) or "").strip()
            self._data[CONF_IMAGE_OFF]      = (ui.get(CONF_IMAGE_OFF, self._data.get(CONF_IMAGE_OFF, "")) or "").strip()
            # Store schedule times (days managed via switch entities)
            for key, s_key in [("s1_time", CONF_IRR_SCHEDULE_1),
                                ("s2_time", CONF_IRR_SCHEDULE_2),
                                ("s3_time", CONF_IRR_SCHEDULE_3)]:
                t = str(ui.get(key) or "00:00:00")
                sched = dict(self._data.get(s_key) or {})
                sched["time"] = t
                if not sched.get("days"): sched["days"] = []
                if not sched.get("mode"): sched["mode"] = "fixed"
                self._data[s_key] = sched
            # Notify toggles are managed via switch entities (not in this form);
            # preserve existing config values untouched.
            # Save immediately so time entities reflect the new schedule times
            self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            # Re-wire schedules in coordinator
            coord = self.hass.data.get("elettrodomestico_monitor", {}).get(self._entry.entry_id)
            if coord and hasattr(coord, "_wire_schedules"):
                coord._wire_schedules()
            return await self.async_step_irr_zones()

        d = self._data
        s1 = d.get(CONF_IRR_SCHEDULE_1) or {}
        s2 = d.get(CONF_IRR_SCHEDULE_2) or {}
        s3 = d.get(CONF_IRR_SCHEDULE_3) or {}
        _imgs = await _scan_www_images_async(self.hass)

        def _t(sched): return str(sched.get("time") or "00:00:00")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_APPLIANCE_NAME, default=d.get(CONF_APPLIANCE_NAME, "")): _SEL_TEXT,
                vol.Optional(CONF_DEVICE_ICON, default=d.get(CONF_DEVICE_ICON, "mdi:sprinkler-variant")): _SEL_ICON,
                _entity_schema_field(CONF_FLOW_SENSOR, d.get(CONF_FLOW_SENSOR)): _SEL_SENSOR,
                _entity_schema_field(CONF_PUMP_SENSOR, d.get(CONF_PUMP_SENSOR)): _SEL_SENSOR_OPT,
                _entity_schema_field(CONF_METEO_ENTITY, d.get(CONF_METEO_ENTITY)): selector.selector({"entity": {"domain": "binary_sensor"}}),
                # Schedule times — loaded from saved config
                vol.Optional("s1_time", default=_t(s1)): _SEL_TIME,
                vol.Optional("s2_time", default=_t(s2)): _SEL_TIME,
                vol.Optional("s3_time", default=_t(s3)): _SEL_TIME,
                vol.Optional(CONF_IMAGE_ON,  default=d.get(CONF_IMAGE_ON,  "")): _image_selector_cached(_imgs),
                vol.Optional(CONF_IMAGE_OFF, default=d.get(CONF_IMAGE_OFF, "")): _image_selector_cached(_imgs),
                # Notifications
                # Notification toggles managed via switch entities after creation
            }),
        )

    async def async_step_irr_zones(self, ui=None):
        """Step 2: edit zone names, switches and durations."""
        if ui is not None:
            zones = list(self._data.get(CONF_ZONES) or [])
            for i in range(len(zones)):
                zones[i] = dict(zones[i])
                zones[i]["name"]         = ui.get(f"z{i}_name",     zones[i].get("name", f"Zona {i+1}"))
                zones[i]["switch"]       = _clean_entity(ui.get(f"z{i}_switch", zones[i].get("switch", "")))
                zones[i]["duration_min"] = float(ui.get(f"z{i}_dur", zones[i].get("duration_min", 10)))
            self._data[CONF_ZONES] = zones
            hass = self.hass
            hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data={})

        zones = self._data.get(CONF_ZONES) or []
        schema_dict = {}
        for i, zone in enumerate(zones):
            schema_dict[vol.Optional(f"z{i}_name",   default=zone.get("name",   f"Zona {i+1}"))] = _SEL_TEXT
            schema_dict[vol.Optional(f"z{i}_switch", default=zone.get("switch", ""))]             = _SEL_SWITCH
            schema_dict[vol.Optional(f"z{i}_dur",    default=float(zone.get("duration_min", 10)))] = selector.selector(
                {"number": {"mode": "box", "min": 1, "max": 180, "step": 1}})

        return self.async_show_form(
            step_id="irr_zones",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"num_zones": str(len(zones))},
        )


# ═══════════════════════════════════════════════════════════════════════════════
class DeviceOptionsFlow(config_entries.OptionsFlow):
    """Options flow for battery devices — edits sensor, switch, thresholds, image."""
    def __init__(self, e):
        self._entry = e
        self._data  = dict(e.data)

    async def async_step_init(self, ui=None):
        from .const import (CONF_DEV_BATTERY_SENSOR, CONF_DEV_CHARGE_SWITCH,
                            CONF_DEV_START_PCT, CONF_DEV_STOP_PCT,
                            DEFAULT_DEV_START_PCT, DEFAULT_DEV_STOP_PCT)
        c = self._data
        if ui is not None:
            self._data[CONF_APPLIANCE_NAME]     = ui.get(CONF_APPLIANCE_NAME, c.get(CONF_APPLIANCE_NAME, "Dispositivo"))
            self._data[CONF_DEVICE_ICON]        = ui.get(CONF_DEVICE_ICON, c.get(CONF_DEVICE_ICON, "mdi:battery-charging"))
            self._data[CONF_DEV_BATTERY_SENSOR] = _clean_entity(ui.get(CONF_DEV_BATTERY_SENSOR, c.get(CONF_DEV_BATTERY_SENSOR, "")))
            self._data[CONF_DEV_CHARGE_SWITCH]  = _clean_entity(ui.get(CONF_DEV_CHARGE_SWITCH, c.get(CONF_DEV_CHARGE_SWITCH, "")))
            self._data[CONF_DEV_START_PCT]      = int(ui.get(CONF_DEV_START_PCT, c.get(CONF_DEV_START_PCT, DEFAULT_DEV_START_PCT)))
            self._data[CONF_DEV_STOP_PCT]       = int(ui.get(CONF_DEV_STOP_PCT, c.get(CONF_DEV_STOP_PCT, DEFAULT_DEV_STOP_PCT)))
            self._data[CONF_IMAGE_ON]           = (ui.get(CONF_IMAGE_ON, c.get(CONF_IMAGE_ON, "")) or "").strip()
            self._data[CONF_IMAGE_OFF]          = (ui.get(CONF_IMAGE_OFF, c.get(CONF_IMAGE_OFF, "")) or "").strip()
            self.hass.config_entries.async_update_entry(self._entry, data=self._data)
            return self.async_create_entry(title="", data={})

        _images = await _scan_www_images_async(self.hass)
        schema = {
            vol.Optional(CONF_APPLIANCE_NAME, default=c.get(CONF_APPLIANCE_NAME, "Dispositivo")): _SEL_TEXT,
            vol.Optional(CONF_DEVICE_ICON, default=c.get(CONF_DEVICE_ICON, "mdi:battery-charging")): _SEL_ICON,
        }
        schema[_entity_schema_field(CONF_DEV_BATTERY_SENSOR, c.get(CONF_DEV_BATTERY_SENSOR))] = _SEL_SENSOR
        schema[_entity_schema_field(CONF_DEV_CHARGE_SWITCH,  c.get(CONF_DEV_CHARGE_SWITCH))]  = _SEL_SWITCH
        schema[vol.Optional(CONF_DEV_START_PCT, default=c.get(CONF_DEV_START_PCT, DEFAULT_DEV_START_PCT))] = _SEL_NUM_INT
        schema[vol.Optional(CONF_DEV_STOP_PCT,  default=c.get(CONF_DEV_STOP_PCT,  DEFAULT_DEV_STOP_PCT))]  = _SEL_NUM_INT
        schema[vol.Optional(CONF_IMAGE_ON,  default=c.get(CONF_IMAGE_ON,  ""))] = _image_selector_cached(_images)
        schema[vol.Optional(CONF_IMAGE_OFF, default=c.get(CONF_IMAGE_OFF, ""))] = _image_selector_cached(_images)
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
