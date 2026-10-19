"""Test per custom_components/elettrodomestico_monitor/notify_helper.py.

Nessun test prima di questa passata (audit v7.0.0) copriva in_notify_window(),
dove viveva un bug critico: con una finestra che attraversa la mezzanotte
(es. 22:00 -> 06:00 — la configurazione più naturale per "notifiche vocali
solo di sera/notte"), il confronto "start <= now <= end" era sempre falso,
perché 'start' (22:00 di oggi) è sempre maggiore di 'end' (06:00 di oggi).
Le notifiche vocali Alexa/Google restavano disattivate 24/7, senza alcun
errore in log — invisibile finché non si nota l'assenza specifica degli
annunci vocali.
"""
from __future__ import annotations

import asyncio
import datetime
import logging

from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.elettrodomestico_monitor.notify_helper import (
    async_send_push,
    in_notify_window,
)


def _hub(start: str, end: str) -> dict:
    return {"notify_start_time": start, "notify_end_time": end}


def test_overnight_window_is_active_late_at_night():
    """FIX (audit v7.0.0, CRITICO): finestra 22:00 -> 06:00, ore 23:30 —
    deve essere considerata DENTRO la finestra (prima del fix: sempre False)."""
    now = datetime.datetime(2026, 1, 1, 23, 30, 0)
    assert in_notify_window(_hub("22:00:00", "06:00:00"), now=now) is True


def test_overnight_window_is_active_just_after_midnight():
    """Stessa finestra 22:00 -> 06:00, ma alle 02:00 del giorno dopo — deve
    restare DENTRO la finestra."""
    now = datetime.datetime(2026, 1, 2, 2, 0, 0)
    assert in_notify_window(_hub("22:00:00", "06:00:00"), now=now) is True


def test_overnight_window_is_inactive_during_the_day():
    """Stessa finestra 22:00 -> 06:00, ma alle 12:00 di giorno — deve
    restare FUORI dalla finestra."""
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    assert in_notify_window(_hub("22:00:00", "06:00:00"), now=now) is False


def test_overnight_window_boundaries_are_inclusive():
    """Ai due estremi esatti (22:00:00 e 06:00:00) la finestra deve
    risultare attiva (confini inclusivi, come per una finestra normale)."""
    hub = _hub("22:00:00", "06:00:00")
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 22, 0, 0)) is True
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 2, 6, 0, 0)) is True


def test_normal_same_day_window_still_works():
    """Non-regressione: una finestra normale (non a cavallo di mezzanotte,
    es. 08:00 -> 22:00) deve continuare a funzionare come prima del fix."""
    hub = _hub("08:00:00", "22:00:00")
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 12, 0, 0)) is True
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 23, 0, 0)) is False
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 6, 0, 0)) is False


def test_00_00_window_disables_filtering():
    """00:00 -> 00:00 è il valore 'nessuna finestra configurata' e deve
    sempre risultare attivo, a qualunque ora."""
    hub = _hub("00:00:00", "00:00:00")
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 3, 0, 0)) is True
    assert in_notify_window(hub, now=datetime.datetime(2026, 1, 1, 15, 0, 0)) is True


# ── async_send_push ───────────────────────────────────────────────────────────
#
# Nessun test prima di questa passata copriva async_send_push() (allora
# _send_push, privata), dove viveva un bug critico segnalato da un utente
# reale: notify.send_message è un dispatcher SEMPRE registrato in HA —
# chiamarlo con un entity_id non più esistente (es. l'app companion iOS
# ri-registrata con un nuovo entity_id) non solleva alcuna eccezione, quindi
# il vecchio codice segnava "sent = True" e la notifica spariva in silenzio,
# senza mai raggiungere i fallback funzionanti. Questi test coprono i 4 casi
# richiesti: entità esistente, entità mancante con fallback mobile_app
# (entità e servizio legacy), entità mancante senza alcun fallback.

async def test_push_delivers_via_send_message_when_entity_exists(hass):
    """Caso base: l'entità target esiste davvero → consegna diretta via
    notify.send_message, nessun fallback necessario."""
    calls = async_mock_service(hass, "notify", "send_message")
    hass.states.async_set("notify.iphone_di_alessandro", "unknown")

    await async_send_push(hass, ["notify.iphone_di_alessandro"], "msg", "title", "test")

    assert len(calls) == 1
    assert calls[0].data.get("entity_id") == "notify.iphone_di_alessandro"
    assert calls[0].data.get("message") == "msg"


async def test_push_falls_back_to_mobile_app_entity_when_target_missing(hass, caplog):
    """FIX (segnalazione utente v7.0.3, CRITICO): l'entità configurata non
    esiste più (app companion ri-registrata) ma notify.mobile_app_<nome>
    esiste sotto il nuovo nome — la notifica deve arrivare lì, non perdersi."""
    caplog.set_level(logging.INFO)
    calls = async_mock_service(hass, "notify", "send_message")
    # notify.iphone_di_alessandro NON viene mai impostata: simula l'entità sparita.
    hass.states.async_set("notify.mobile_app_iphone_di_alessandro", "unknown")

    await async_send_push(hass, ["notify.iphone_di_alessandro"], "msg", "title", "test")

    assert len(calls) == 1
    assert calls[0].data.get("entity_id") == "notify.mobile_app_iphone_di_alessandro"
    assert "consegnato a" in caplog.text


async def test_push_falls_back_to_legacy_mobile_app_service_when_target_missing(hass):
    """Non-regressione: se esiste solo il SERVIZIO legacy
    notify.mobile_app_<nome> (non l'entità), la consegna deve comunque
    passare da lì — comportamento già presente prima di questo fix."""
    legacy_calls = async_mock_service(hass, "notify", "mobile_app_iphone_di_alessandro")
    # Nessuna entità notify.* impostata: né il target originale né l'entità mobile_app_*.

    await async_send_push(hass, ["notify.iphone_di_alessandro"], "msg", "title", "test")

    assert len(legacy_calls) == 1
    assert legacy_calls[0].data.get("message") == "msg"


async def test_push_warns_without_raising_when_no_fallback_exists(hass, caplog):
    """Destinatario mancante e nessuna alternativa trovata (né entità né
    servizio legacy): deve solo loggare un warning, mai sollevare
    un'eccezione — la causa originale del 'Task exception was never
    retrieved' segnalato dall'utente."""
    await async_send_push(hass, ["notify.destinatario_fantasma"], "msg", "title", "test")

    assert "non trovato" in caplog.text


async def test_push_times_out_without_hanging_on_slow_network(hass, caplog, monkeypatch):
    """FIX (2026-10-16, incidente rete notturno — vedi CHANGELOG v7.0.3):
    durante un'interruzione DNS/rete reale una chiamata notify.send_message
    può restare "appesa" per molti secondi. Qui riduciamo il timeout a un
    valore minuscolo e registriamo un servizio deliberatamente lento, per
    verificare che async_send_push ritorni comunque (loggando un warning)
    invece di restare bloccata o propagare l'eccezione di timeout."""
    import custom_components.elettrodomestico_monitor.notify_helper as notify_helper
    monkeypatch.setattr(notify_helper, "_NOTIFY_CALL_TIMEOUT_S", 0.05)

    async def _slow_send_message(call):
        await asyncio.sleep(2)

    hass.services.async_register("notify", "send_message", _slow_send_message)
    hass.states.async_set("notify.iphone_di_alessandro", "unknown")

    await async_send_push(hass, ["notify.iphone_di_alessandro"], "msg", "title", "test")

    assert "oltre" in caplog.text
