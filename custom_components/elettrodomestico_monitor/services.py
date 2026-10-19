# ============================================================
# FILE:    services.py
# VERSION: 7.0.4
# DESC:    Services — export/import, reset, maintenance, irrigation start/stop
# CHANGED: 2026-10-19
# ============================================================
"""Services for Elettrodomestico Monitor."""
from __future__ import annotations
import logging
from pathlib import Path
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service
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

# FIX (HACS review @frenck, 2026-10-19): export/import scrivevano/leggevano
# da /config/www, che Home Assistant serve SENZA autenticazione su /local/ —
# chiunque potesse raggiungere l'istanza poteva scaricare l'export completo
# di tutte le config entry. Spostato in una sottocartella dedicata di
# /config, non servita via HTTP.
_EXPORT_SUBDIR = "elettrodomestico_monitor"


def _sanitize_filename(raw: str) -> str | None:
    """Return just the file name component of `raw`, or None if it contains
    any path component (es. '../', '/', '\\') — impedisce di uscire dalla
    cartella di export passando un 'filename' malevolo al servizio
    import_config (FIX HACS review @frenck, 2026-10-19).

    I separatori vengono controllati esplicitamente invece di affidarsi solo
    a Path(...).name: su un host POSIX (es. la CI, tipicamente Linux) '\\'
    non è un separatore di percorso per pathlib, quindi un filename come
    'sub\\em_export.json' passerebbe inosservato se controllato solo con
    pathlib.
    """
    raw = str(raw or "")
    if not raw or "/" in raw or "\\" in raw:
        return None
    name = Path(raw).name
    if not name or name != raw:
        return None
    return name


async def _notify_unknown_entry(hass: HomeAssistant, service: str, entry_id: str) -> None:
    """Surface an unknown entry_id visibly instead of a silent no-op.

    FIX (audit v7.0.0, medio): reset_sensors/set_maintenance/irrigation_*
    tornavano "successo" a chi chiamava il servizio (automazione/script)
    anche con un entry_id inesistente — solo un warning in log, mai
    visibile in UI, a differenza di export/import/remove_all che notificano
    sempre l'errore.
    """
    await hass.services.async_call("persistent_notification", "create", {
        "message": (f"⚠️ Servizio `{service}` non eseguito\n\n"
                    f"Nessun device trovato con `entry_id`: `{entry_id}`\n\n"
                    f"Il device è stato rimosso o ricreato? Controlla l'entry_id "
                    f"usato nell'automazione/script."),
        "title": "Elettrodomestico Monitor — entry_id non trovato",
        "notification_id": f"em_unknown_entry_{service}",
    })


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
            # FIX (audit v7.0.0, medio): prima era un no-op silenzioso — il
            # servizio riportava comunque "successo" a chi lo chiamava
            # (automazione/script), che non aveva modo di accorgersi che
            # l'entry_id non esisteva più (es. device rimosso e ricreato).
            _LOGGER.warning("[EM] reset_sensors: entry_id %s not found", eid)
            await _notify_unknown_entry(hass, "reset_sensors", eid)

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
            await _notify_unknown_entry(hass, "set_maintenance", eid)

    # ── export_config ─────────────────────────────────────────────────────────
    async def _export(call: ServiceCall):
        """Export all device configs to /config/elettrodomestico_monitor/em_export.json"""
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

        # FIX (richiesta utente v7.0.2): oltre al file fisso "em_export.json"
        # (che import_config continua a cercare di default — non lo
        # tocchiamo, per non rompere il flusso "esporta poi importa"),
        # scriviamo anche una copia con la data ("em_export_YYMMDD.json") per
        # tenere uno storico degli export senza sovrascriverli ogni volta.
        dated_name = f"em_export_{_dt.datetime.now().strftime('%y%m%d')}.json"
        out       = Path(hass.config.path(_EXPORT_SUBDIR, "em_export.json"))
        out_dated = Path(hass.config.path(_EXPORT_SUBDIR, dated_name))
        n   = len(export["devices"])

        def _write():
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                payload = _j.dumps(export, indent=2, ensure_ascii=False)
                out.write_text(payload, encoding="utf-8")
                out_dated.write_text(payload, encoding="utf-8")
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
            _LOGGER.info("[EM Export] %d devices → %s + %s (%d bytes)", n, out, out_dated, file_size)
            abs_path = await hass.async_add_executor_job(lambda: str(out.resolve()))
            # FIX (HACS review @frenck, 2026-10-19): non più in /config/www
            # (servita senza autenticazione su /local/) — il file va ora
            # recuperato da un file manager/addon Samba sulla cartella
            # /config, non da un URL pubblico.
            msg   = (f"✅ Export completato: **{n} device**\n\n"
                     f"📁 Percorso assoluto: `{abs_path}`\n"
                     f"📦 Dimensione: {file_size} bytes\n"
                     f"🗓️ Copia datata: `{_EXPORT_SUBDIR}/{dated_name}`\n\n"
                     f"ℹ️ Il file NON è più accessibile da un URL pubblico "
                     f"(per sicurezza): recuperalo con un file manager o "
                     f"l'addon Samba, nella cartella `/config/{_EXPORT_SUBDIR}/`.")
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
        """Import device configs from /config/elettrodomestico_monitor/em_export.json.
        Updates existing devices (matched by slot) or creates new ones.
        """
        import json as _j

        raw_filename = call.data.get("filename", "em_export.json")
        # FIX (HACS review @frenck, 2026-10-19 — CRITICO): 'filename' veniva
        # unito al percorso senza alcun controllo, quindi un valore come
        # '../../secrets.yaml' usciva dalla cartella di export. Accettiamo
        # solo un nome file semplice (nessun separatore di percorso).
        filename = _sanitize_filename(raw_filename)
        if filename is None:
            _LOGGER.error("[EM Import] filename non valido (deve essere un nome file semplice): %s", raw_filename)
            await hass.services.async_call("persistent_notification", "create", {
                "message": (f"❌ Nome file non valido: `{raw_filename}`\n\n"
                            f"Usa solo il nome del file (es. `em_export.json`), senza percorsi."),
                "title":   "Elettrodomestico Monitor — Import Error",
                "notification_id": "em_import",
            })
            return

        src = Path(hass.config.path(_EXPORT_SUBDIR, filename))

        def _read():
            # FIX (HACS review @frenck, 2026-10-19): src.exists() veniva
            # chiamato direttamente nel coroutine async (I/O bloccante sul
            # event loop). Spostato nell'executor insieme alla lettura.
            if not src.exists():
                raise FileNotFoundError(str(src))
            with open(src, encoding="utf-8") as f:
                return _j.load(f)

        # FIX (audit v7.0.0, alto): un json.load senza gestione di
        # JSONDecodeError, e nessuna verifica che il file fosse un oggetto
        # con una chiave "devices" a lista, facevano crashare il servizio
        # con un traceback opaco invece di un messaggio d'errore leggibile.
        try:
            data = await hass.async_add_executor_job(_read)
        except FileNotFoundError:
            _LOGGER.error("[EM Import] File not found: %s", src)
            await hass.services.async_call("persistent_notification", "create", {
                "message": f"❌ File non trovato: `/config/{_EXPORT_SUBDIR}/{filename}`\n\nEsegui prima l'Export.",
                "title":   "Elettrodomestico Monitor — Import Error",
                "notification_id": "em_import",
            })
            return
        except Exception as ex:
            _LOGGER.error("[EM Import] File JSON non valido: %s — %s", src, ex)
            await hass.services.async_call("persistent_notification", "create", {
                "message": (f"❌ File di import non valido: `/config/{_EXPORT_SUBDIR}/{filename}`\n\n"
                            f"Errore: `{ex}`\n\nVerifica che sia un export "
                            f"generato da **export_config** e non sia stato modificato."),
                "title":   "Elettrodomestico Monitor — Import Error",
                "notification_id": "em_import",
            })
            return

        if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
            _LOGGER.error("[EM Import] Struttura file inattesa (atteso oggetto con chiave 'devices' a lista): %s", src)
            await hass.services.async_call("persistent_notification", "create", {
                "message": (f"❌ Struttura del file non valida: `/config/{_EXPORT_SUBDIR}/{filename}`\n\n"
                            f"Atteso un oggetto JSON con una chiave `devices` (lista).\n"
                            f"Verifica che sia un export generato da **export_config**."),
                "title":   "Elettrodomestico Monitor — Import Error",
                "notification_id": "em_import",
            })
            return

        updated = created = skipped = 0

        for dev in data.get("devices", []):
            if not isinstance(dev, dict):
                skipped += 1
                continue
            slot      = dev.get("slot")
            new_data  = dev.get("data", {})
            new_title = dev.get("title", "")

            try:
                slot = int(slot)
            except (TypeError, ValueError):
                _LOGGER.error("[EM Import] Invalid slot: %s", slot)
                skipped += 1
                continue

            if not isinstance(new_data, dict) or not new_data:
                skipped += 1
                continue

            # Comparazione robusta: alcune entry più vecchie possono avere
            # CONF_SLOT salvato come stringa — evitiamo un mismatch di tipo
            # str/int che farebbe "matches" sempre vuoto e duplicherebbe lo
            # slot (audit v7.0.0, alto).
            def _slot_of(e):
                try:
                    return int(e.data.get(CONF_SLOT))
                except (TypeError, ValueError):
                    return None

            matches = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if (e.data.get(CONF_ENTRY_TYPE) in (ENTRY_TYPE_APPLIANCE, ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE)
                    or e.data.get("entry_type") in ("irrigation", "device"))
                and _slot_of(e) == slot
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
                # Create new device via import flow. async_step_import now
                # rejects a colliding slot on its own (audit v7.0.0, alto) —
                # inspect the flow result instead of assuming success just
                # because async_init didn't raise.
                try:
                    result = await hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "import"},
                        data=new_data,
                    )
                    if result.get("type") == "create_entry":
                        _LOGGER.info("[EM Import] Created x%s: %s", slot, new_title)
                        created += 1
                    else:
                        _LOGGER.error(
                            "[EM Import] x%s (%s) non creato: %s",
                            slot, new_title, result.get("reason", result.get("type")))
                        skipped += 1
                except Exception as e:
                    _LOGGER.error("[EM Import] Error creating x%s: %s", slot, e)
                    skipped += 1

        await hass.services.async_call("persistent_notification", "create", {
            "message": (f"✅ Import completato\n\n"
                        f"- Aggiornati: **{updated}** device\n"
                        f"- Creati: **{created}** device\n"
                        f"- Saltati: **{skipped}** device\n\n"
                        # FIX (audit v7.0.0, minore): ogni entry registra già
                        # un update_listener che ricarica automaticamente al
                        # salvataggio, e le entry nuove vengono avviate da HA
                        # da sole — il vecchio messaggio spingeva a un
                        # riavvio completo non necessario.
                        f"ℹ️ Le modifiche sono già attive: i device aggiornati si "
                        f"ricaricano automaticamente, quelli nuovi si avviano da soli."),
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
            await _notify_unknown_entry(hass, "irrigation_start", eid)

    async def _irr_stop(call: ServiceCall):
        eid   = call.data["entry_id"]
        coord = hass.data.get(DOMAIN, {}).get(eid)
        if coord and hasattr(coord, 'stop_cycle'):
            await coord.stop_cycle()
        else:
            _LOGGER.warning("[EM] irrigation.stop: entry %s not found", eid)
            await _notify_unknown_entry(hass, "irrigation_stop", eid)

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
            # FIX (HACS review @frenck, 2026-10-19 — CRITICO): tutti questi
            # servizi creano/modificano/eliminano config entry o esportano i
            # dati di ogni device; registrati con async_register, erano
            # richiamabili da QUALSIASI utente, non solo gli admin.
            async_register_admin_service(hass, DOMAIN, name, handler, schema=schema)
            _LOGGER.debug("[EM] Service registered (admin-only): %s.%s", DOMAIN, name)


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove all services."""
    for name in ("reset_sensors", "reset_all_sensors", "set_maintenance", "export_config", "import_config",
                  "remove_all_devices", "irrigation_start", "irrigation_stop"):
        if hass.services.has_service(DOMAIN, name):
            hass.services.async_remove(DOMAIN, name)
