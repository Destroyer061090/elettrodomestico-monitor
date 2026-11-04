"""Test per custom_components/elettrodomestico_monitor/__init__.py.

FIX (segnalazione utente, 2026-10-27 — CRITICO): _register_one_resource
(registrazione automatica della risorsa Lovelace della card) iterava
direttamente su dict di Home Assistant dentro hass.data mentre un altro
task poteva modificarli in parallelo durante l'avvio — "RuntimeError:
dictionary changed size during iteration", mai catturato perché la
funzione gira dentro un hass.async_create_task non atteso (compariva nel
log come "Task exception was never retrieved"). Due fix distinti, coperti
qui: (1) le iterazioni sui dict di hass.data ora scattano una copia con
list(...); (2) l'intera chiamata è avvolta in un wrapper che intercetta
qualunque eccezione residua e la logga invece di lasciarla propagare.

CORREZIONE (segnalazione utente, 2026-10-29 — CRITICO): la prima versione
del fix sopra rimandava la registrazione con
`hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, lambda _event:
hass.async_create_task(...))`. Una lambda sync non è né una coroutine né
marcata @callback, quindi HA la esegue in un thread dell'executor —
chiamare hass.async_create_task da lì non è thread-safe ("calls
hass.async_create_task from a thread other than the event loop"), la
coroutine non veniva mai attesa ("coroutine ... was never awaited") e la
risorsa non veniva mai registrata. Corretto con l'helper ufficiale
`homeassistant.helpers.start.async_at_started`, che usa internamente
hass.async_run_hass_job e garantisce l'esecuzione sul event loop sia a HA
già avviato sia in fase di avvio. Qui testato end-to-end (non più evitato
come nella nota precedente) perché async_setup() si è dimostrato
affidabile nel harness di test — lo esercitano già implicitamente tutti i
test di test_integration.py tramite hass.config_entries.async_setup().
"""
from __future__ import annotations

import homeassistant.components.lovelace.resources as lovelace_resources
from homeassistant.core import CoreState
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.elettrodomestico_monitor as em
from custom_components.elettrodomestico_monitor.const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_TYPE_HUB,
)


class _FakeResourceCollection:
    """Sostituisce ResourceStorageCollection: niente storage reale, solo
    i tre metodi che _register_one_resource chiama."""

    def __init__(self):
        self.created: list[dict] = []

    async def async_load(self):
        pass

    def async_items(self):
        return []

    async def async_create_item(self, data):
        self.created.append(data)


async def test_register_one_resource_finds_collection_nested_two_levels_deep(hass, monkeypatch):
    """La ricerca di ResourceStorageCollection dentro hass.data è annidata
    fino a 2 livelli di dict — qui ora tutti convertiti a list(...) per il
    fix del RuntimeError. Verifica che la logica di ricerca continui a
    trovare la collection anche nel caso più annidato."""
    monkeypatch.setattr(lovelace_resources, "ResourceStorageCollection", _FakeResourceCollection)
    fake = _FakeResourceCollection()
    hass.data["qualche_integrazione"] = {"livello2": fake}

    await em._register_one_resource(hass, "elettrodomestico-monitor-card.js", "7.0.8")

    assert len(fake.created) == 1
    assert fake.created[0]["url"] == "/elettrodomestico_monitor/elettrodomestico-monitor-card.js?v=7.0.8"


async def test_register_one_resource_finds_collection_at_top_level(hass, monkeypatch):
    """Non-regressione: il caso più comune (chiave 'lovelace' o
    'lovelace_storage' diretta) deve continuare a funzionare."""
    monkeypatch.setattr(lovelace_resources, "ResourceStorageCollection", _FakeResourceCollection)
    fake = _FakeResourceCollection()
    hass.data["lovelace_storage"] = fake

    await em._register_one_resource(hass, "elettrodomestico-monitor-card.js", "7.0.8")

    assert len(fake.created) == 1


async def test_register_lovelace_resource_safely_catches_and_logs_instead_of_raising(hass, monkeypatch, caplog):
    """FIX (segnalazione utente, 2026-10-27 — CRITICO): questa funzione è
    sempre lanciata con hass.async_create_task, mai attesa dal chiamante —
    un'eccezione al suo interno comparirebbe come 'Task exception was
    never retrieved' invece di un errore diagnosticabile. Deve
    intercettarla e loggare un warning con prefisso [EM], mai propagarla."""

    async def _boom(hass_):
        raise RuntimeError("dictionary changed size during iteration")

    monkeypatch.setattr(em, "_async_register_lovelace_resource", _boom)

    await em._register_lovelace_resource_safely(hass)  # non deve sollevare

    assert "[EM]" in caplog.text
    assert "registrazione risorsa card fallita" in caplog.text


# ── Schedulazione via async_at_started (correzione 2026-10-29) ───────────────

async def test_lovelace_resource_registration_runs_without_thread_errors(hass, caplog, monkeypatch):
    """CORREZIONE (segnalazione utente, 2026-10-29 — CRITICO): con HA già
    avviato (es. un reload dell'integrazione), async_at_started deve
    invocare _register_lovelace_resource_safely direttamente sul event
    loop — mai più 'calls hass.async_create_task from a thread other than
    the event loop' o 'was never awaited', i sintomi esatti della lambda
    sync usata nel fix precedente."""
    calls = []

    async def _spy(hass_):
        calls.append(hass_)

    monkeypatch.setattr(em, "_register_lovelace_resource_safely", _spy)
    hass.set_state(CoreState.running)

    hub_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}, title="Hub Globale")
    hub_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(hub_entry.entry_id)
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert "thread other than the event loop" not in caplog.text
    assert "never awaited" not in caplog.text


async def test_lovelace_resource_registration_is_scheduled_only_once(hass, monkeypatch):
    """Il flag in hass.data[DOMAIN] deve impedire una doppia
    schedulazione se async_setup viene invocato più di una volta (reload
    anomalo del componente)."""
    calls = []

    async def _spy(hass_):
        calls.append(hass_)

    monkeypatch.setattr(em, "_register_lovelace_resource_safely", _spy)
    hass.set_state(CoreState.running)

    await em.async_setup(hass, {})
    await em.async_setup(hass, {})
    await hass.async_block_till_done()

    assert len(calls) == 1
