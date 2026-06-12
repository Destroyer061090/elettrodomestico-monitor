# ============================================================
# FILE:    update_coordinator.py
# VERSION: 5.0.0
# DESC:    Update coordinator — GitHub release checker
# CHANGED: 2026-06-11
# ============================================================
"""Update coordinator for Elettrodomestico Monitor.

Checks GitHub releases API every UPDATE_CHECK_INTERVAL_H hours.
Creates/updates a sensor in the Hub device showing available version.
"""
from __future__ import annotations
import logging
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

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"GitHub API returned {resp.status}")
                data = await resp.json()
        except Exception as exc:
            raise UpdateFailed(f"GitHub check failed: {exc}") from exc

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
        return {
            "latest_version":   self.latest_version,
            "current_version":  VERSION,
            "update_available": self.update_available,
            "release_url":      self.release_url,
            "release_notes":    self.release_notes,
        }

    @staticmethod
    def _is_newer(latest: str, current: str) -> bool:
        """Return True if latest > current using semantic version comparison."""
        def _parts(v: str) -> tuple[int, ...]:
            try:
                return tuple(int(x) for x in v.split("."))
            except ValueError:
                return (0,)
        return _parts(latest) > _parts(current)
