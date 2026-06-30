# DESC: Centralized multi-channel notification sender, shared by all coordinators.
#       Eliminates the previously-duplicated push/whatsapp/alexa/google logic.
# VERSION: 5.7.0
"""Shared notification helper.

A single async function sends a notification across the enabled channels
(push, whatsapp, alexa, google), applying the hub's notify time-window to the
voice channels (alexa/google). All channels are best-effort: a failure on one
never blocks the others.

This is intentionally a plain function (not a mixin) so it has no hidden state
and is trivial to unit-test: pass a hass, the hub config dict, a channels dict,
and the message strings.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)


def _parse_time(t: str) -> tuple[int, int]:
    """Parse 'HH:MM[:SS]' → (hour, minute). Returns (0, 0) on bad input."""
    try:
        parts = str(t).split(":")
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError, TypeError):
        return 0, 0


def in_notify_window(hub: dict[str, Any], now=None) -> bool:
    """True if `now` falls within the hub's notify start/end window.

    A 00:00→00:00 window is treated as "always on" (disabled filtering),
    matching the historical behaviour of the integration.
    """
    now = now or dt_util.now()
    sh, sm = _parse_time(hub.get("notify_start_time", "00:00:00"))
    eh, em = _parse_time(hub.get("notify_end_time", "00:00:00"))
    if (sh, sm) == (0, 0) and (eh, em) == (0, 0):
        return True
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= now <= end


async def _send_push(hass: HomeAssistant, targets: list, message: str,
                     title: str, log_id: str) -> None:
    """Send a push notification to each target, with fallbacks.

    Tries notify.send_message (HA 2024.8+ entity style) first, then falls back
    to the legacy notify.<service> and notify.mobile_app_<service> services.
    """
    for raw in (targets or []):
        t = str(raw).strip()
        if not t:
            continue
        sent = False
        try:
            if hass.services.has_service("notify", "send_message"):
                await hass.services.async_call(
                    "notify", "send_message",
                    {"entity_id": t, "message": message, "title": title})
                sent = True
        except Exception as ex:  # noqa: BLE001 - best-effort channel
            _LOGGER.debug("[%s] push send_message failed for %s: %s", log_id, t, ex)
        if not sent:
            svc_name = t.split(".", 1)[1] if "." in t else t
            for svc in (svc_name, f"mobile_app_{svc_name}"):
                if hass.services.has_service("notify", svc):
                    try:
                        await hass.services.async_call(
                            "notify", svc, {"title": title, "message": message})
                        sent = True
                        break
                    except Exception as ex:  # noqa: BLE001
                        _LOGGER.warning("[%s] push notify.%s failed: %s", log_id, svc, ex)
        if not sent:
            _LOGGER.warning("[%s] push: could not deliver to '%s'", log_id, t)


async def async_send_notification(
    hass: HomeAssistant,
    hub: dict[str, Any],
    *,
    message: str,
    title: str,
    speak: str | None = None,
    push: bool = False,
    whatsapp: bool = False,
    alexa: bool = False,
    google: bool = False,
    log_id: str = "EM",
) -> None:
    """Send `message` over every enabled channel. Best-effort, never raises.

    Args:
        hass:     Home Assistant instance.
        hub:      Hub config dict (push_targets, whatsapp_entity, alexa_targets,
                  google_targets, notify_start_time, notify_end_time).
        message:  Notification body (used for push/whatsapp).
        title:    Notification title (push).
        speak:    Spoken text for voice channels; defaults to `message`.
        push/whatsapp/alexa/google: per-channel enable flags (already resolved
                  by the caller from its own switches).
        log_id:   Identifier used in log lines (usually the instance id).
    """
    speak = speak or message
    in_win = in_notify_window(hub)

    if push:
        await _send_push(hass, hub.get("push_targets"), message, title, log_id)

    if whatsapp and hub.get("whatsapp_entity"):
        try:
            await hass.services.async_call(
                "input_text", "set_value",
                {"entity_id": hub["whatsapp_entity"], "value": message})
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] whatsapp failed: %s", log_id, ex)

    if in_win and alexa and hub.get("alexa_targets"):
        try:
            await hass.services.async_call(
                "notify", "alexa_media",
                {"target": hub["alexa_targets"], "message": speak,
                 "data": {"type": "announce", "method": "spoken"}})
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] alexa failed: %s", log_id, ex)

    if in_win and google and hub.get("google_targets"):
        try:
            await hass.services.async_call(
                "tts", "google_translate_say",
                {"entity_id": hub["google_targets"], "message": speak})
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] google failed: %s", log_id, ex)
