# ============================================================
# FILE:    update_coordinator.py
# VERSION: 5.8.6
# DESC:    Update coordinator — GitHub release checker
# CHANGED: 2026-06-11
# ============================================================
"""Update coordinator for Elettrodomestico Monitor.

Checks GitHub releases API every UPDATE_CHECK_INTERVAL_H hours.
Creates/updates a sensor in the Hub device showing available version.
"""
from __future__ import annotations
import logging
import asyncio
import aiohttp
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, VERSION, GITHUB_API_URL, UPDATE_CHECK_INTERVAL_H

_LOGGER = logging.getLogger(__name__)


class UpdateCheckCoordinator(DataUpdateCoordinator):
    """Polls GitHub releases API for the latest version."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass, _LOGGER,
            name=f"{DOMAIN}_update_check",
            update_interval=timedelta(hours=UPDATE_CHECK_INTERVAL_H),
        )
        self.latest_version:  str  = VERSION
        self.release_url:     str  = ""
        self.release_notes:   str  = ""
        self.update_available: bool = False
        self._notified_version: str = ""   # last version we already notified about

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    # Non-200 (e.g. rate limit) — keep previous data quietly.
                    _LOGGER.debug("GitHub update check returned %s", resp.status)
                    return self.data or {}
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as exc:
            # Network/DNS/timeout errors are expected when offline — this is not
            # a real failure, so log at debug level and keep the previous result
            # instead of raising (which HA would surface as an error).
            _LOGGER.debug("GitHub update check skipped (offline?): %s", exc)
            return self.data or {}
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("GitHub update check failed: %s", exc)
            return self.data or {}

        # tag_name is typically "v4.5.1" or "4.5.1"
        tag = data.get("tag_name", VERSION).lstrip("v")
        self.latest_version   = tag
        self.release_url      = data.get("html_url", "")
        self.release_notes    = data.get("body", "")[:500]   # truncate for attribute
        self.update_available = self._is_newer(tag, VERSION)

        _LOGGER.debug(
            "Update check: installed=%s latest=%s available=%s",
            VERSION, tag, self.update_available,
        )

        # One-shot push notification when a NEW update is first detected,
        # only if the hub-level "Notifica Aggiornamenti" switch is ON.
        if self.update_available and tag != self._notified_version:
            await self._notify_update(tag)
        return {
            "latest_version":   self.latest_version,
            "current_version":  VERSION,
            "update_available": self.update_available,
            "release_url":      self.release_url,
            "release_notes":    self.release_notes,
        }

    async def _notify_update(self, tag: str) -> None:
        """Send a single push notification about an available update.
        Respects the hub switch.notifica_update_elettrodomestici_hub toggle."""
        # Read the hub update-notify switch (single source of truth)
        sw = self.hass.states.get("switch.notifica_update_elettrodomestici_hub")
        if sw is not None and sw.state != "on":
            return  # notifications disabled by user
        try:
            from .hub import get_hub_config
            hub = get_hub_config(self.hass)
        except Exception:
            return
        targets = hub.get("push_targets") or []
        if not targets:
            return
        title = "📦 Elettrodomestico Monitor"
        message = f"Aggiornamento disponibile: v{tag}"
        for t in targets:
            t = str(t).strip()
            sent = False
            try:
                if self.hass.services.has_service("notify", "send_message"):
                    await self.hass.services.async_call(
                        "notify", "send_message",
                        {"entity_id": t, "message": message, "title": title})
                    sent = True
            except Exception:
                pass
            if not sent:
                svc = t.split(".", 1)[1] if "." in t else t
                for cand in (svc, f"mobile_app_{svc}"):
                    if self.hass.services.has_service("notify", cand):
                        try:
                            await self.hass.services.async_call(
                                "notify", cand, {"message": message, "title": title})
                            break
                        except Exception as ex:
                            _LOGGER.warning("Update notify failed (%s): %s", cand, ex)
        self._notified_version = tag
        _LOGGER.info("Update notification sent for v%s", tag)

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Return True if latest > current using semantic version comparison."""
        def _parts(v: str) -> tuple[int, ...]:
            try:
                return tuple(int(x) for x in v.split("."))
            except ValueError:
                return (0,)
        return _parts(latest) > _parts(current)
