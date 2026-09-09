# ============================================================
# FILE:    services.py
# VERSION: 5.7.1
# DESC:    Services — export/import, reset, maintenance, irrigation start/stop
# CHANGED: 2026-06-11
# ============================================================
"""Services for Elettrodomestico Monitor."""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import (
    DOMAIN, CONF_ENTRY_TYPE, CONF_SLOT, CONF_APPLIANCE_NAME, CONF_PRESET,
    ENTRY_TYPE_HUB, ENTRY_TYPE_APPLIANCE, VERSION,
    ENTRY_TYPE_DEVICE,
)

try:
    from .const import ENTRY_TYPE_IRRIGATION
except ImportError:
    ENTRY_TYPE_IRRIGATION = "irrigation"

_LOGGER = logging.getLogger(__name__)


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all services. Safe to call multiple times."""

    # ── reset_sensors ─────────────────────────────────────────────────────────
    _S = vol.Schema({vol.Required("entry_id"): cv.string})

    async def _reset(call: ServiceCall):
        eid   = call.data["entry_id"]
        coord = hass.data.get(DOMAIN, {}).get(eid)
        if coord:
            await coord.async_reset_counters()
        else:
            _LOGGER.warning("[EM] reset_sensors: entry_id %s not found", eid)

    # ── reset_all_sensors ─────────────────────────────────────────────────────
    # One-shot reset of every device's counters (hub excluded). Iterates all
    # registered coordinators, skipping the hub's special data keys and anything
    # that doesn't expose async_reset_counters.
    _RA = vol.Schema({})

    async def _reset_all(call: ServiceCall):
        store = hass.data.get(DOMAIN, {})
        # Skip the hub's bookkeeping keys (not real device coordinators)
        skip_keys = {"hub_entry_id", "update_coordinator"}
        hub_entry_id = store.get("hub_entry_id")
        done = 0
        failed = 0
        for key, coord in list(store.items()):
            if key in skip_keys or key == hub_entry_id:
                continue
            reset = getattr(coord, "async_reset_counters", None)
            if reset is None or not callable(reset):
                continue
            try:
                await reset()
                done += 1
            except Exception as ex:  # noqa: BLE001 - keep resetting the others
                failed += 1
                _LOGGER.warning("[EM] reset_all_sensors: errore su %s: %s", key, ex)
        _LOGGER.info("[EM] reset_all_sensors: %d device azzerati, %d falliti", done, failed)


    # ── set_maintenance ───────────────────────────────────────────────────────
    _M = vol.Schema({
        vol.Required("entry_id"): cv.string,
        vol.Optional("note", default=""): cv.string,
    })

    async def _maint(call: ServiceCall):
        eid   = call.data["entry_id"]
        note  = call.data.get("note", "")
        coord = hass.data.get(DOMAIN, {}).get(eid)
        if coord:
            await coord.async_set_maintenance(note)
        else:
            _LOGGER.warning("[EM] set_maintenance: entry_id %s not found", eid)

    # ── export_config ─────────────────────────────────────────────────────────
    async def _export(call: ServiceCall):
        """Export all device configs to /config/www/em_export.json"""
        import json as _j
        import datetime as _dt
        from pathlib import Path

        entries = hass.config_entries.async_entries(DOMAIN)
        export = {
            "version":     VERSION,
            "exported_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "hub":         None,
            "devices":     [],
        }

        for entry in entries:
            d = dict(entry.data)
            if d.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
                export["hub"] = {"title": entry.title, "data": d}
            elif d.get(CONF_ENTRY_TYPE) in (ENTRY_TYPE_APPLIANCE, ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE) or \
                    d.get("entry_type") in ("irrigation", "device"):
                # Clean export data: remove auto-computed/legacy fields
                _EXPORT_EXCLUDE = {"power_share", "_pending_hub"}
                clean_d = {k: v for k, v in d.items() if k not in _EXPORT_EXCLUDE}
                export["devices"].append({
                    "entry_id":   entry.entry_id,
                    "title":      entry.title,
                    "slot":       d.get(CONF_SLOT),
                    "name":       d.get(CONF_APPLIANCE_NAME),
                    "preset":     d.get(CONF_PRESET),
                    "entry_type": d.get(CONF_ENTRY_TYPE) or d.get("entry_type", "appliance"),
                    "data":       clean_d,
                })

        export["devices"].sort(key=lambda x: int(x.get("slot") or 0))

        out = Path(hass.config.path("www", "em_export.json"))
        n   = len(export["devices"])

        def _write():
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "w", encoding="utf-8") as f:
                    _j.dump(export, f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                _LOGGER.error("[EM Export] Write error: %s", e)
                return False

        ok = await hass.async_add_executor_job(_write)

        # Double-check file exists after write
        file_exists = await hass.async_add_executor_job(lambda: out.exists())
        file_size   = await hass.async_add_executor_job(
            lambda: out.stat().st_size if out.exists() else 0)

        if ok and file_exists:
            _LOGGER.info("[EM Export] %d devices → %s (%d bytes)", n, out, file_size)
            abs_path = await hass.async_add_executor_job(lambda: str(out.resolve()))
            msg   = (f"✅ Export completato: **{n} device**\n\n"
                     f"📁 Percorso assoluto: `{abs_path}`\n"
                     f"📦 Dimensione: {file_size} bytes\n"
                     f"🌐 Scaricabile da: `/local/em_export.json`\n\n"
                     f"ℹ️ Se non vedi il file nel tuo file browser, "
                     f"controlla che punti alla stessa cartella `/config` di HA. "
                     f"Puoi anche scaricarlo dall'URL `/local/em_export.json`.")
            title = "Elettrodomestico Monitor — Export"
        else:
            _LOGGER.error("[EM Export] File NOT created! ok=%s exists=%s path=%s",
                          ok, file_exists, out)
            msg   = (f"❌ Export fallito\n\n"
                     f"ok={ok}, file_exists={file_exists}\n"
                     f"Percorso tentato: `{out}`\n"
                     f"Controlla i log HA per dettagli")
            title = "Elettrodomestico Monitor — Export ERROR"

        await hass.services.async_call("persistent_notification", "create", {
            "message": msg, "title": title, "notification_id": "em_export",
        })

    # ── import_config ─────────────────────────────────────────────────────────
    _I = vol.Schema({
        vol.Optional("filename", default="em_export.json"): cv.string,
    })

    async def _import(call: ServiceCall):
        """Import device configs from /config/www/em_export.json.
        Updates existing devices (matched by slot) or creates new ones.
        """
        import json as _j
        from pathlib import Path

        filename = call.data.get("filename", "em_export.json")
        src      = Path(hass.config.path("www", filename))

        if not src.exists():
            _LOGGER.error("[EM Import] File not found: %s", src)
            await hass.services.async_call("persistent_notification", "create", {
                "message": f"❌ File non trovato: `/config/www/{filename}`\n\nEsegui prima l'Export.",
                "title":   "Elettrodomestico Monitor — Import Error",
                "notification_id": "em_import",
            })
            return

        def _read():
            with open(src, encoding="utf-8") as f:
                return _j.load(f)

        data    = await hass.async_add_executor_job(_read)
        updated = created = skipped = 0

        for dev in data.get("devices", []):
            slot      = dev.get("slot")
            new_data  = dev.get("data", {})
            new_title = dev.get("title", "")

            try:
                slot = int(slot)
            except Exception:
                _LOGGER.error("[EM Import] Invalid slot: %s", slot)
                skipped += 1
                continue

            if not new_data:
                skipped += 1
                continue

            matches = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if (e.data.get(CONF_ENTRY_TYPE) in (ENTRY_TYPE_APPLIANCE, ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE)
                    or e.data.get("entry_type") in ("irrigation", "device"))
                and e.data.get(CONF_SLOT) == slot
            ]

            if matches:
                # Update existing device
                entry  = matches[0]
                merged = dict(entry.data)
                merged.update(new_data)
                hass.config_entries.async_update_entry(
                    entry, title=new_title or entry.title, data=merged)
                _LOGGER.info("[EM Import] Updated x%s: %s → %s",
                             slot, entry.title, new_title)
                updated += 1
            else:
                # Create new device via import flow
                try:
                    await hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=new_data,
                    )
                    _LOGGER.info("[EM Import] Created x%s: %s", slot, new_title)
                    created += 1
                except Exception as e:
                    _LOGGER.error("[EM Import] Error creating x%s: %s", slot, e)
                    skipped += 1

        await hass.services.async_call("persistent_notification", "create", {
            "message": (f"✅ Import completato\n\n"
                        f"- Aggiornati: **{updated}** device\n"
                        f"- Creati: **{created}** device\n"
                        f"- Non trovati: **{skipped}** device\n\n"
                        f"⚠️ Riavvia HA per applicare le modifiche."),
            "title":   "Elettrodomestico Monitor — Import",
            "notification_id": "em_import",
        })
        _LOGGER.info("[EM Import] Done: updated=%d created=%d skipped=%d",
                     updated, created, skipped)

    # ── remove_all_devices ───────────────────────────────────────────────────
    async def _remove_all(call: ServiceCall):
        """Remove ALL appliance entries, keeping only the Hub."""
        entries = hass.config_entries.async_entries(DOMAIN)
        removed = 0
        for entry in entries:
            et = entry.data.get(CONF_ENTRY_TYPE) or entry.data.get("entry_type", "")
            if et in (ENTRY_TYPE_APPLIANCE, ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE, "device"):
                await hass.config_entries.async_remove(entry.entry_id)
                _LOGGER.info("[EM] Removed device: %s", entry.title)
                removed += 1

        await hass.services.async_call("persistent_notification", "create", {
            "message": (f"🗑️ Rimossi **{removed}** device\n\n"
                        f"L'Hub è rimasto invariato.\n"
                        f"Puoi ora usare **import_config** per riconfigurare."),
            "title":   "Elettrodomestico Monitor — Remove All",
            "notification_id": "em_remove_all",
        })
        _LOGGER.info("[EM] remove_all_devices: removed %d entries", removed)

    # ── Irrigation services ──────────────────────────────────────────────────
    _IZ = vol.Schema({
        vol.Required("entry_id"): cv.string,
        vol.Optional("zone_idx"): vol.Coerce(int),
    })

    async def _irr_start(call: ServiceCall):
        eid   = call.data["entry_id"]
        zone  = call.data.get("zone_idx")
        coord = hass.data.get(DOMAIN, {}).get(eid)
        if coord and hasattr(coord, 'start_cycle'):
            await coord.start_cycle(zone_idx=zone)
        else:
            _LOGGER.warning("[EM] irrigation.start: entry %s not found or not irrigation", eid)

    async def _irr_stop(call: ServiceCall):
        eid   = call.data["entry_id"]
        coord = hass.data.get(DOMAIN, {}).get(eid)
        if coord and hasattr(coord, 'stop_cycle'):
            await coord.stop_cycle()
        else:
            _LOGGER.warning("[EM] irrigation.stop: entry %s not found", eid)

    # ── Register all ──────────────────────────────────────────────────────────
    services = {
        "reset_sensors":      (_reset, _S),
        "reset_all_sensors":  (_reset_all, _RA),
        "set_maintenance":    (_maint, _M),
        "export_config":      (_export, vol.Schema({})),
        "import_config":      (_import, _I),
        "remove_all_devices": (_remove_all, vol.Schema({})),
        "irrigation_start":   (_irr_start, _IZ),
        "irrigation_stop":    (_irr_stop,  vol.Schema({vol.Required("entry_id"): cv.string})),
    }
    for name, (handler, schema) in services.items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema)
            _LOGGER.debug("[EM] Service registered: %s.%s", DOMAIN, name)


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all services."""
    for name in ("reset_sensors", "reset_all_sensors", "set_maintenance", "export_config", "import_config",
                  "remove_all_devices", "irrigation_start", "irrigation_stop"):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
