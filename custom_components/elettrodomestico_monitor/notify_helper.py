# DESC: Centralized multi-channel notification sender, shared by all coordinators.
#       Eliminates the previously-duplicated push/whatsapp/alexa/google logic.
# VERSION: 7.0.3
# CHANGED: 2026-06-11 (data storica ricostruita — campo assente nell'header
#          originale prima dell'audit v6.1.0)
# CHANGED: 2026-10-16 - timeout di sicurezza su tutte le chiamate di
#          notifica (vedi CHANGELOG v7.0.3)
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

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# FIX (2026-10-16, incidente rete notturno — vedi CHANGELOG v7.0.3): nessuna
# chiamata di notifica qui dentro aveva un timeout. Durante un'interruzione
# DNS/rete reale, hass.services.async_call("notify", "send_message", ...)
# può restare in attesa per molti secondi (fino al timeout interno del
# client HTTP) prima di fallire. Questo non causava crash né perdita di
# dati, ma teneva occupato il task del coordinator che invia la notifica
# più del necessario durante un disservizio già in corso. Un timeout fisso
# qui garantisce che una chiamata di notifica non resti mai bloccata
# oltre questo limite, qualunque sia la causa a monte.
_NOTIFY_CALL_TIMEOUT_S = 10


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
    # FIX (audit v7.0.0 — CRITICO): con una finestra che attraversa la
    # mezzanotte (es. 22:00 -> 06:00), 'start' (ancorato a oggi) è sempre
    # maggiore di 'end' (ancorato a oggi), quindi "start <= now <= end" era
    # sempre falso: le notifiche vocali restavano disattivate 24/7 senza
    # alcun errore in log. Se end < start, la finestra si considera "fuori
    # dall'intervallo [end, start)" anziché "dentro [start, end]". Vedi
    # CHANGELOG.md.
    if end < start:
        return now >= start or now <= end
    return start <= now <= end


async def async_send_push(hass: HomeAssistant, targets: list, message: str,
                           title: str, log_id: str) -> None:
    """Send a push notification to each target, with fallbacks.

    Tries notify.send_message against the target ENTITY (HA 2024.8+ entity
    style) only if that entity still exists; otherwise falls back to the
    legacy notify.<service> and notify.mobile_app_<service> services, and
    finally to the notify.mobile_app_<service> entity if one exists. Public
    (no leading underscore) so other modules — e.g. update_coordinator.py —
    can reuse this single implementation instead of duplicating it.

    FIX (segnalazione utente v7.0.3, CRITICO): notify.send_message è un
    dispatcher SEMPRE registrato in HA — has_service("notify",
    "send_message") verifica solo che quel servizio generico esista, non
    che l'entità target (`t`) esista davvero. Chiamarlo con un entity_id
    non più valido (es. l'app companion iOS ri-registrata con un nuovo
    entity_id) non solleva alcuna eccezione — HA logga solo "entità
    mancante" a livello core — quindi `sent` diventava True e la notifica
    spariva in silenzio, senza mai raggiungere i fallback funzionanti qui
    sotto. Ora si tenta send_message SOLO se l'entità esiste davvero in
    hass.states, e si prova anche l'entità notify.mobile_app_<nome> (non
    solo il servizio legacy) come ultimo fallback — copre esattamente il
    caso segnalato: vecchia entità sparita, nuova entità mobile_app_<nome>
    presente sotto nuovo nome dopo la ri-registrazione dell'app.
    """
    for raw in (targets or []):
        t = str(raw).strip()
        if not t:
            continue
        sent = False

        if t.startswith("notify.") and hass.states.get(t) is not None:
            try:
                await asyncio.wait_for(
                    hass.services.async_call(
                        "notify", "send_message",
                        {"entity_id": t, "message": message, "title": title}),
                    timeout=_NOTIFY_CALL_TIMEOUT_S)
                sent = True
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "[%s] push send_message verso %s oltre %ds (rete/DNS lenti?)",
                    log_id, t, _NOTIFY_CALL_TIMEOUT_S)
            except Exception as ex:  # noqa: BLE001 - best-effort channel
                _LOGGER.debug("[%s] push send_message failed for %s: %s", log_id, t, ex)

        if not sent:
            svc_name = t.split(".", 1)[1] if "." in t else t
            for svc in (svc_name, f"mobile_app_{svc_name}"):
                if hass.services.has_service("notify", svc):
                    try:
                        await asyncio.wait_for(
                            hass.services.async_call(
                                "notify", svc, {"title": title, "message": message}),
                            timeout=_NOTIFY_CALL_TIMEOUT_S)
                        sent = True
                        break
                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            "[%s] push notify.%s oltre %ds (rete/DNS lenti?)",
                            log_id, svc, _NOTIFY_CALL_TIMEOUT_S)
                    except Exception as ex:  # noqa: BLE001
                        _LOGGER.warning("[%s] push notify.%s failed: %s", log_id, svc, ex)

            if not sent:
                fallback_entity = f"notify.mobile_app_{svc_name}"
                if fallback_entity != t and hass.states.get(fallback_entity) is not None:
                    try:
                        await asyncio.wait_for(
                            hass.services.async_call(
                                "notify", "send_message",
                                {"entity_id": fallback_entity, "message": message, "title": title}),
                            timeout=_NOTIFY_CALL_TIMEOUT_S)
                        sent = True
                        _LOGGER.info(
                            "[%s] push: destinatario '%s' non trovato, consegnato a '%s'",
                            log_id, t, fallback_entity)
                    except asyncio.TimeoutError:
                        _LOGGER.warning(
                            "[%s] push send_message fallback verso %s oltre %ds (rete/DNS lenti?)",
                            log_id, fallback_entity, _NOTIFY_CALL_TIMEOUT_S)
                    except Exception as ex:  # noqa: BLE001
                        _LOGGER.debug(
                            "[%s] push send_message fallback failed for %s: %s",
                            log_id, fallback_entity, ex)

        if not sent:
            _LOGGER.warning("[%s] push: destinatario '%s' non trovato", log_id, t)


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
        await async_send_push(hass, hub.get("push_targets"), message, title, log_id)

    if whatsapp and hub.get("whatsapp_entity"):
        try:
            # FIX (audit v7.0.0, medio): input_text ha un limite 'max'
            # (default HA 100, massimo 255). Senza troncamento, un messaggio
            # più lungo faceva fallire set_value con vol.Invalid, catturato
            # sotto e solo loggato — la notifica WhatsApp spariva senza
            # alcun segnale visibile. Ora tronchiamo al limite dichiarato
            # dall'entità (se disponibile) prima di inviare.
            wa_value = message
            st = hass.states.get(hub["whatsapp_entity"])
            max_len = st.attributes.get("max") if st else None
            if isinstance(max_len, (int, float)) and max_len > 0 and len(wa_value) > max_len:
                _LOGGER.debug(
                    "[%s] whatsapp message troncato da %d a %d caratteri (limite input_text)",
                    log_id, len(wa_value), int(max_len))
                wa_value = wa_value[:int(max_len)]
            await asyncio.wait_for(
                hass.services.async_call(
                    "input_text", "set_value",
                    {"entity_id": hub["whatsapp_entity"], "value": wa_value}),
                timeout=_NOTIFY_CALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            _LOGGER.warning("[%s] whatsapp oltre %ds (rete/DNS lenti?)", log_id, _NOTIFY_CALL_TIMEOUT_S)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] whatsapp failed: %s", log_id, ex)

    if in_win and alexa and hub.get("alexa_targets"):
        try:
            await asyncio.wait_for(
                hass.services.async_call(
                    "notify", "alexa_media",
                    {"target": hub["alexa_targets"], "message": speak,
                     "data": {"type": "announce", "method": "spoken"}}),
                timeout=_NOTIFY_CALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            _LOGGER.warning("[%s] alexa oltre %ds (rete/DNS lenti?)", log_id, _NOTIFY_CALL_TIMEOUT_S)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] alexa failed: %s", log_id, ex)

    if in_win and google and hub.get("google_targets"):
        try:
            await asyncio.wait_for(
                hass.services.async_call(
                    "tts", "google_translate_say",
                    {"entity_id": hub["google_targets"], "message": speak}),
                timeout=_NOTIFY_CALL_TIMEOUT_S)
        except asyncio.TimeoutError:
            _LOGGER.warning("[%s] google oltre %ds (rete/DNS lenti?)", log_id, _NOTIFY_CALL_TIMEOUT_S)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("[%s] google failed: %s", log_id, ex)
