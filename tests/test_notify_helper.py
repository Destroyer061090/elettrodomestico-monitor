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

import datetime

from custom_components.elettrodomestico_monitor.notify_helper import (
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
