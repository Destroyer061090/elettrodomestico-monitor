# ============================================================
# FILE:    __init__.py
# VERSION: 5.7.23
# DESC:    Integration setup, platform loading, irrigation routing, services registration
# CHANGED: 2026-06-11
# ============================================================
"""Elettrodomestico Monitor v18."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN, ENTRY_TYPE_HUB, ENTRY_TYPE_APPLIANCE, CONF_ENTRY_TYPE, CONF_INSTANCE_ID, ENTRY_TYPE_IRRIGATION, ENTRY_TYPE_DEVICE
from .coordinator import ElettrodomesticoCoordinator
from .irrigation_coordinator import IrrigationCoordinator
from .device_coordinator import DeviceCoordinator
from .update_coordinator import UpdateCheckCoordinator
from .services import async_register_services, async_unregister_services
from .migration import async_migrate_entry as _migrate

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON,
    Platform.NUMBER, Platform.TEXT, Platform.SWITCH, Platform.TIME,
    Platform.VACUUM, Platform.CLIMATE, Platform.SELECT,
]


def _hub_exists(hass):
    return any(e.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB
               for e in hass.config_entries.async_entries(DOMAIN))


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # ── Register static paths ────────────────────────────────────────────────
    from homeassistant.components.http import StaticPathConfig
    component_dir = Path(__file__).parent
    paths = [
        # JS card + www assets at /{DOMAIN}/
        StaticPathConfig(
            url_path=f"/{DOMAIN}",
            path=str(component_dir / "www"),
            cache_headers=True,
        ),
        # icon.png at /brands/{DOMAIN}/ — matches HA frontend icon requests
        StaticPathConfig(
            url_path=f"/brands/{DOMAIN}",
            path=str(component_dir),
            cache_headers=False,  # no cache so icon changes show immediately
        ),
    ]
    # Filter out paths that might already be registered
    to_register = []
    for p in paths:
        try:
            to_register.append(p)
        except Exception:
            pass
    try:
        await hass.http.async_register_static_paths(to_register)
        _LOGGER.debug("Static paths registered for %s", DOMAIN)
    except Exception as ex:
        # Some paths may already be registered — try one by one
        for p in to_register:
            try:
                await hass.http.async_register_static_paths([p])
            except Exception:
                pass

    # ── Auto-register Lovelace resource (scheduled after setup) ─────────────
    hass.async_create_task(_async_register_lovelace_resource(hass))

    return True


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Auto-manage all Lovelace JS resources for this integration."""
    from .const import VERSION
    cards = [
        "elettrodomestico-monitor-card.js",
        "elettrodomestico-dispositivo-card.js",
        "em-stat-table.js",
    ]
    for card_file in cards:
        await _register_one_resource(hass, card_file, VERSION)


async def _register_one_resource(hass: HomeAssistant, card_file: str, VERSION: str) -> None:
    url_current = f"/{DOMAIN}/{card_file}?v={VERSION}"
    card_stem = card_file.replace(".js", "")

    try:
        from homeassistant.components.lovelace.resources import ResourceStorageCollection
    except ImportError:
        _LOGGER.info("[EM] Add resource manually: %s", url_current)
        return

    resource_collection = None
    for data_key in ["lovelace", "lovelace_storage"]:
        data = hass.data.get(data_key)
        if data is None:
            continue
        if isinstance(data, ResourceStorageCollection):
            resource_collection = data
            break
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, ResourceStorageCollection):
                    resource_collection = v
                    break
        if resource_collection:
            break

    if resource_collection is None:
        for val in hass.data.values():
            if isinstance(val, ResourceStorageCollection):
                resource_collection = val
                break
            if isinstance(val, dict):
                for subval in val.values():
                    if isinstance(subval, ResourceStorageCollection):
                        resource_collection = subval
                        break
                    if isinstance(subval, dict):
                        for subsubval in subval.values():
                            if isinstance(subsubval, ResourceStorageCollection):
                                resource_collection = subsubval
                                break
            if resource_collection:
                break

    if resource_collection is None:
        _LOGGER.info(
            "[EM] Risorsa da aggiungere manualmente (dashboard in modalita YAML): "
            "URL='%s' tipo='Modulo JavaScript'. Questo e' normale e non e' un errore.",
            url_current)
        return

    try:
        await resource_collection.async_load()
    except Exception:
        pass

    existing = list(resource_collection.async_items())
    current_ok = False
    to_delete  = []

    for item in existing:
        url = item.get("url", "")
        is_ours = (f"/{DOMAIN}/{card_stem}" in url or f"/local/{card_stem}" in url)
        if is_ours:
            if url == url_current:
                current_ok = True
            else:
                to_delete.append(item)

    for item in to_delete:
        try:
            await resource_collection.async_delete_item(item["id"])
            _LOGGER.info("[EM] Removed stale: %s", item.get("url"))
        except Exception as ex:
            _LOGGER.warning("[EM] Remove failed %s: %s", item.get("url"), ex)

    if not current_ok:
        try:
            await resource_collection.async_create_item({
                "res_type": "module",
                "url": url_current,
            })
            _LOGGER.info("[EM] ✅ Lovelace resource registered: %s", url_current)
        except Exception as ex:
            _LOGGER.warning("[EM] Registration failed: %s. Add manually: %s", ex, url_current)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    # Run non-destructive migration check on every startup
    # Migration errors must NEVER block setup — devices must always load
    try:
        await _migrate(hass, entry)
    except Exception as ex:
        _LOGGER.warning("[EM] Migration warning for '%s': %s — continuing setup", entry.title, ex)

    pending = entry.data.get("_pending_hub")
    if pending and not _hub_exists(hass):
        clean = {k: v for k, v in entry.data.items() if k != "_pending_hub"}
        hass.config_entries.async_update_entry(entry, data=clean)
        hass.async_create_task(_bootstrap_hub(hass, pending))

    # ── Irrigation device ────────────────────────────────────────────────────
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or        entry.data.get("entry_type") == "irrigation":
        coord = IrrigationCoordinator(hass, entry)
        try:
            await coord.async_setup()
            await coord.async_config_entry_first_refresh()
        except Exception as exc:
            raise ConfigEntryNotReady(f"Irrigation setup failed: {exc}") from exc
        hass.data[DOMAIN][entry.entry_id] = coord
        # Register irrigation-specific platforms
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TIME, Platform.TEXT, Platform.BUTTON])
        await async_register_services(hass)
        entry.async_on_unload(entry.add_update_listener(_reload))
        _LOGGER.info("Irrigation '%s' avviata.", entry.title)
        return True

    # ── Battery Device ───────────────────────────────────────────────────────
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or \
            entry.data.get("entry_type") == "device":
        coord = DeviceCoordinator(hass, entry)
        try:
            await coord.async_init()
            await coord.async_config_entry_first_refresh()
        except Exception as exc:
            raise ConfigEntryNotReady(f"Device setup failed: {exc}") from exc
        hass.data[DOMAIN][entry.entry_id] = coord
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TEXT, Platform.BUTTON])
        await async_register_services(hass)
        entry.async_on_unload(entry.add_update_listener(_reload))
        _LOGGER.info("Dispositivo '%s' avviato.", entry.title)
        return True

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        hass.data[DOMAIN]["hub_entry_id"] = entry.entry_id
        if "update_coordinator" not in hass.data[DOMAIN]:
            upd = UpdateCheckCoordinator(hass)
            try: await upd.async_config_entry_first_refresh()
            except Exception: pass
            hass.data[DOMAIN]["update_coordinator"] = upd
        await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON])
        # Register services at hub level so export/import work even with no devices
        await async_register_services(hass)
        entry.async_on_unload(entry.add_update_listener(_reload))
        _LOGGER.info("Hub Globale avviato.")
        return True

    coord = ElettrodomesticoCoordinator(hass, entry)
    try:
        await coord.async_setup()
        await coord.async_config_entry_first_refresh()
    except Exception as exc:
        raise ConfigEntryNotReady(f"Setup failed: {exc}") from exc

    hass.data[DOMAIN][entry.entry_id] = coord
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_reload))
    _LOGGER.info("Device '%s' avviato.", entry.title)
    return True


async def _bootstrap_hub(hass, hub_data):
    if _hub_exists(hass): return
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "hub_import"}, data=hub_data)


async def _reload(hass, entry): await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Irrigation: only unload its own platforms
    if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_IRRIGATION or
            entry.data.get("entry_type") == "irrigation"):
        coord = hass.data[DOMAIN].get(entry.entry_id)
        ok = await hass.config_entries.async_unload_platforms(
            entry, [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TIME, Platform.TEXT, Platform.BUTTON])
        if ok and coord:
            await coord.async_unload()
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return ok

    if (entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_DEVICE or
            entry.data.get("entry_type") == "device"):
        ok = await hass.config_entries.async_unload_platforms(
            entry, [Platform.SENSOR, Platform.SWITCH, Platform.NUMBER, Platform.TEXT, Platform.BUTTON])
        if ok:
            hass.data[DOMAIN].pop(entry.entry_id, None)
        return ok

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB:
        await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR, Platform.SWITCH, Platform.BUTTON])
        hass.data[DOMAIN].pop("hub_entry_id", None)
        if not _hub_exists(hass): hass.data[DOMAIN].pop("update_coordinator", None)
        return True
    coord = hass.data[DOMAIN].get(entry.entry_id)
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok and coord:
        await coord.async_unload()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not [k for k in hass.data[DOMAIN] if k not in ("hub_entry_id","update_coordinator")]:
            await async_unregister_services(hass)
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:

    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_HUB: return
    from .storage import ElettrodomesticoStorage
    iid = entry.data.get(CONF_INSTANCE_ID)
    if iid: await ElettrodomesticoStorage(hass, iid).async_reset()
