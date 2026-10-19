"""Test per custom_components/elettrodomestico_monitor/services.py.

Revisione HACS (@frenck) sulla pull request di submission, 2026-10-19:
- i servizi di configurazione erano richiamabili da qualunque utente, non
  solo admin (fix: homeassistant.helpers.service.async_register_admin_service
  — già testato upstream in home-assistant/core, non replicato qui);
- import_config univa 'filename' al percorso senza alcun controllo, quindi
  un valore come '../../secrets.yaml' usciva dalla cartella di export.

Questi test coprono la sanificazione del filename, sia a livello di
funzione pura (_sanitize_filename) sia end-to-end sul servizio registrato.
"""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.elettrodomestico_monitor.const import DOMAIN
from custom_components.elettrodomestico_monitor.services import (
    _sanitize_filename,
    async_register_services,
)


@pytest.mark.parametrize("raw", [
    "../em_export.json",
    "../../secrets.yaml",
    "sub/em_export.json",
    "sub\\em_export.json",
    "/etc/passwd",
    "",
])
def test_sanitize_filename_rejects_anything_with_a_path_component(raw):
    """FIX (revisione HACS @frenck, CRITICO): qualunque valore con un
    separatore di percorso (o vuoto) deve essere rifiutato — altrimenti
    import_config può uscire dalla cartella di export."""
    assert _sanitize_filename(raw) is None


def test_sanitize_filename_accepts_a_bare_filename():
    """Non-regressione: il flusso normale (nome file semplice) continua a
    funzionare."""
    assert _sanitize_filename("em_export.json") == "em_export.json"
    assert _sanitize_filename("em_export_261019.json") == "em_export_261019.json"


async def test_import_config_refuses_path_traversal_filename(hass):
    """Verifica end-to-end: il servizio import_config, chiamato con un
    filename malevolo, si ferma prima di toccare qualunque file e notifica
    l'errore invece di tentare la lettura."""
    notif_calls = async_mock_service(hass, "persistent_notification", "create")
    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN, "import_config", {"filename": "../../secrets.yaml"}, blocking=True)

    assert len(notif_calls) == 1
    assert "non valido" in notif_calls[0].data.get("message", "")
