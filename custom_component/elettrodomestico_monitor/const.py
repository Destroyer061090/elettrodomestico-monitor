# ============================================================
# FILE:    const.py
# VERSION: 5.0.0
# DESC:    Constants — domain, config keys, defaults, vacuum states
# CHANGED: 2026-06-11
# ============================================================
"""Constants for Elettrodomestico Monitor v8."""

DOMAIN   = "elettrodomestico_monitor"
VERSION  = "5.0.6"

GITHUB_USER             = "Destroyer061090"
GITHUB_REPO             = "elettrodomestico-monitor"
GITHUB_API_URL          = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
UPDATE_CHECK_INTERVAL_H = 12

ENTRY_TYPE_HUB       = "hub"
ENTRY_TYPE_APPLIANCE = "appliance"

CONF_ENTRY_TYPE  = "entry_type"
CONF_INSTANCE_ID = "instance_id"
CONF_SLOT        = "slot"
CONF_PRESET      = "preset"
CONF_DEVICE_ICON = "device_icon"
CONF_IMAGE_ON               = "image_on"
CONF_IMAGE_OFF              = "image_off"

# Hub
CONF_COSTO_KWH          = "costo_kwh"
CONF_COSTO_KWH_SENSOR   = "costo_kwh_sensor"
CONF_COSTO_ACQUA        = "costo_acqua_m3"
CONF_COSTO_ACQUA_SENSOR = "costo_acqua_m3_sensor"
CONF_COSTO_GAS          = "costo_gas_m3"
CONF_COSTO_GAS_SENSOR   = "costo_gas_m3_sensor"
CONF_VENDITA_KWH        = "vendita_kwh"
CONF_VENDITA_KWH_SENSOR = "vendita_kwh_sensor"
CONF_NOTIFY_START_TIME  = "notify_start_time"
CONF_NOTIFY_END_TIME    = "notify_end_time"
CONF_PUSH_TARGETS       = "push_targets"
CONF_ALEXA_TARGETS      = "alexa_targets"
CONF_GOOGLE_TARGETS     = "google_targets"
CONF_WHATSAPP_ENTITY    = "whatsapp_entity"
CONF_AUTO_ON_TIME       = "auto_on_time"
CONF_AUTO_OFF_TIME      = "auto_off_time"

# Appliance
CONF_APPLIANCE_NAME     = "appliance_name"
CONF_POWER_SENSOR       = "power_sensor"
CONF_SWITCH_ENTITY      = "switch_entity"
CONF_TRIGGER_ENTITY     = "trigger_entity"    # optional: external entity to drive AC state
CONF_WORK_THRESHOLD_W   = "work_threshold_w"
CONF_TRIGGER_DELAY_M    = "trigger_delay_m"
CONF_START_DELAY_S      = "start_delay_s"
CONF_CUSTOM_MESSAGE     = "custom_message"
CONF_SCHEDULE_OVERRIDE  = "schedule_override"
CONF_AUTO_ON_LOCAL      = "auto_on_local"
CONF_AUTO_OFF_LOCAL     = "auto_off_local"
CONF_NOTIFY_PUSH        = "notify_push"
CONF_NOTIFY_ALEXA       = "notify_alexa"
CONF_NOTIFY_GOOGLE      = "notify_google"
CONF_NOTIFY_WHATSAPP    = "notify_whatsapp"
CONF_NOTIFY_UPDATE      = "notify_update"
CONF_SOURCE_UNIT        = "source_unit"
CONF_TOTAL_UNIT         = "total_unit"
CONF_DEVICE_CLASS       = "device_class_override"

# Defaults
DEFAULT_THRESHOLD_W      = 10
DEFAULT_TRIGGER_DELAY_M  = 1
DEFAULT_START_DELAY_S    = 0
DEFAULT_COST             = 0.0
DEFAULT_NOTIFY_START     = "08:00:00"
DEFAULT_NOTIFY_END       = "22:00:00"
DEFAULT_SCHEDULE         = "00:00:00"

# Storage / runtime
COORDINATOR_UPDATE_INTERVAL = 10
STORAGE_VERSION             = 1
STORAGE_KEY                 = f"{DOMAIN}_data"
EVENT_CYCLE_START           = f"{DOMAIN}_cycle_start"
EVENT_CYCLE_END             = f"{DOMAIN}_cycle_end"

# Week
WEEK_DAYS    = ["lunedi","martedi","mercoledi","giovedi","venerdi","sabato","domenica"]
WEEK_DAYS_EN = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

# Entity suffixes
SFX_POWER        = "potenza_elettrodomestici_w"
SFX_KWH          = "kwh_elettrodomestici"
SFX_VOLUME_M3    = "volume_m3_elettrodomestici"
SFX_MASTER       = "time_on_elettrodomestici"
SFX_STATUS       = "stato_elettrodomestici"
SFX_VERSION      = "versione_elettrodomestici"
SFX_UPDATE       = "aggiornamento_elettrodomestici"
SFX_AC           = "ac_elettrodomestici"
SFX_SCHEDULE     = "programma_elettrodomestici"
SFX_COSTO_SENSOR = "costo_energia_elettrodomestici"   # dedicated cost sensor

SFX_ENERGY_TODAY  = "energy_oggi_elettrodomestici"
SFX_ENERGY_MONTH  = "energy_mese_elettrodomestici"
SFX_ENERGY_YEAR   = "energy_anno_elettrodomestici"
SFX_CICLI_TODAY   = "cicli_oggi_elettrodomestici"
SFX_CICLI_MONTH   = "cicli_mese_elettrodomestici"
SFX_CICLI_YEAR    = "cicli_anno_elettrodomestici"
SFX_CICLI_TOTAL   = "cicli_totale_elettrodomestici"
SFX_TEMPO_TODAY   = "tempo_oggi_elettrodomestici"
SFX_TEMPO_MONTH   = "tempo_mese_elettrodomestici"
SFX_TEMPO_YEAR    = "tempo_anno_elettrodomestici"
SFX_COSTO_TODAY   = "costo_oggi_elettrodomestici"
SFX_COSTO_MONTH   = "costo_mese_elettrodomestici"
SFX_COSTO_YEAR    = "costo_anno_elettrodomestici"
SFX_LAST_CYCLE    = "ultimo_ciclo_elettrodomestici"
SFX_WEEK_PREFIX   = "settimana"

SFX_BTN_MAINT     = "manutenzione_elettrodomestici"
SFX_BTN_RESET     = "reset_contatori_elettrodomestici"

SFX_NUM_SOGLIA    = "soglia_lavoro_elettrodomestici_w"
SFX_NUM_DELAY_OFF = "tempo_innesco_elettrodomestici_m"
SFX_NUM_DELAY_ON  = "avvio_ritardato_elettrodomestici_s"

SFX_TXT_NOME      = "nome_elettrodomestico"
SFX_TXT_MSG       = "messaggio_elettrodomestico"

SFX_SW_SWITCH     = "switch_elettrodomestici"

# Notification switches (per-device toggle, targets come from hub)
SFX_SW_NOTIFY_PUSH      = "notifica_push_elettrodomestici"
SFX_SW_NOTIFY_ALEXA     = "notifica_alexa_elettrodomestici"
SFX_SW_NOTIFY_GOOGLE    = "notifica_google_elettrodomestici"
SFX_SW_NOTIFY_WHATSAPP  = "notifica_whatsapp_elettrodomestici"
SFX_SW_NOTIFY_UPDATE    = "notifica_update_elettrodomestici"

# Vacuum-specific entity suffixes
SFX_VACUUM_BATTERY  = "batteria_vacuum"        # sensor: battery %
SFX_DEVICE_BATTERY  = "batteria_dispositivo"   # sensor: device battery %
SFX_VACUUM_STATUS   = "stato_vacuum"           # sensor: cleaning/docked/...

# Vacuum states considered "active" (cycle running)
# States that mean the vacuum is WORKING (cleaning/moving)
# Using inverse approach: active = anything NOT in VACUUM_INACTIVE_STATES
# This handles all Chinese robot states (smart_cleaning, zone_cleaning, etc.)
VACUUM_INACTIVE_STATES = {
    "docked", "idle", "error", "off",
    "unavailable", "unknown", "standby", "sleep", "charging",
}
# Kept for backwards compat — also includes expanded states
VACUUM_ACTIVE_STATES = {
    "cleaning", "returning", "paused",
    "smart_cleaning", "zone_cleaning", "spot_cleaning",
    "goto_target", "quick_mapping", "fast_mapping",
    "selective_cleaning", "room_cleaning", "auto_cleaning",
}

# Time entities (schedule — time only, no date)
SFX_TIME_AUTO_ON    = "orario_accensione_elettrodomestici"
SFX_TIME_AUTO_OFF   = "orario_spegnimento_elettrodomestici"

# Master sensor attribute names
ATTR_TERMINATO          = "terminato"
ATTR_MANUTENZIONE       = "manutenzione"
ATTR_TEMPO_CICLO        = "tempo_ciclo_elettrodomestici"
ATTR_OGGI               = "Oggi"
ATTR_MESE               = "Mese"
ATTR_ANNO               = "Anno"
ATTR_IERI               = "Ieri"
ATTR_MESE_PRECEDENTE    = "Mese Precedente"
ATTR_ANNO_PRECEDENTE    = "Anno Precedente"
ATTR_CONSUMO_CICLO      = "consumo_ciclo_elettrodomestici"
ATTR_COSTO_CICLO        = "costo_ciclo_elettrodomestici"
ATTR_COSTO_GIORNALIERO  = "costo_consumo_giornaliero_elettrodomestici"
ATTR_COSTO_MENSILE      = "costo_consumo_mensile_elettrodomestici"
ATTR_COSTO_ANNUALE      = "costo_consumo_annuale_elettrodomestici"
ATTR_COSTO_IERI         = "costo_consumo_ieri_elettrodomestici"
ATTR_COSTO_MESE_PREC    = "costo_consumo_mese_precedente_elettrodomestici"
ATTR_COSTO_ANNO_PREC    = "costo_consumo_anno_precedente_elettrodomestici"
ATTR_CICLI_OGGI         = "cicli_oggi"
ATTR_CICLI_MESE         = "cicli_mese"
ATTR_CICLI_ANNO         = "cicli_anno"
ATTR_WEEKLY_STATS       = "statistiche_settimanali"
ATTR_VERSION            = "versione"
ATTR_LAST_RESET         = "ultimo_reset"
ATTR_COSTO_FONTE        = "fonte_costo"
ATTR_PRESET             = "preset"

# ── Irrigation config keys ───────────────────────────────────────────────────
CONF_ZONES              = "zones"           # list of zone dicts [{name, switch, duration_min}]
CONF_ZONE_ORDER         = "zone_order"      # ordered list of zone indices
CONF_FLOW_SENSOR        = "flow_sensor"     # L/min sensor
CONF_PUMP_SENSOR        = "pump_sensor"     # W sensor for pump kWh
CONF_METEO_ENTITY       = "meteo_entity"    # binary_sensor: skip if on
CONF_IRR_SCHEDULE_1     = "irr_schedule_1"  # {time, days, mode} — mode: fixed|sunrise|sunset
CONF_IRR_SCHEDULE_2     = "irr_schedule_2"
CONF_IRR_SCHEDULE_3     = "irr_schedule_3"
ENTRY_TYPE_IRRIGATION   = "irrigation"

# ── Vacuum-specific config keys ─────────────────────────────────────────────────
CONF_POWER_SENSOR_2   = "power_sensor_2"    # optional: second power sensor
CONF_POWER_SHARE      = "power_share"           # fraction of sensor (default 1.0, overridden by auto-share)

# Power group sharing (auto-computed, not user-configured)
POWER_GROUPS_KEY      = "power_groups"              # hass.data[DOMAIN][POWER_GROUPS_KEY]           # fraction of sensor (default 1.0)    # optional: second power sensor (e.g. pump kWh for irrigation)
CONF_VACUUM_ENTITY    = "vacuum_entity"     # vacuum.* — drives cycle state
CONF_BATTERY_SENSOR   = "battery_sensor"    # sensor.* — battery %
