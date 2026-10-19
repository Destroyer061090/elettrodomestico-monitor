"""Test per custom_components/elettrodomestico_monitor/vacuum.py.

Segnalazione utente v7.0.3: l'entità vacuum "proxy" di Elettrodomestico
Monitor inoltrava comandi al robot reale (self._vacuum_eid) senza mai
controllare che fosse disponibile — con un robot Tuya/localtuya offline
(batteria scarica, WiFi instabile), Home Assistant logga solo un warning
generico "Referenced entities ... are missing or not currently available"
(senza alcun riferimento a EM), il comando si perde e il proxy non segnala
nulla. In più: il proxy restava "disponibile" in HA anche a robot spento
(ereditava la disponibilità dal coordinator EM, non dal robot reale), e il
controllo di rientro automatico per batteria scarica confrontava lo stato
del robot con un'allowlist fissa case-sensitive che non riconosce gli
stati estesi dei robot cinesi/Tuya (smart_cleaning, zone_cleaning, ecc.),
già gestiti correttamente altrove in questo stesso file (vedi `activity`).
"""
from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.elettrodomestico_monitor.const import (
    CONF_BATTERY_SENSOR,
    CONF_ENTRY_TYPE,
    CONF_INSTANCE_ID,
    CONF_PRESET,
    CONF_SLOT,
    CONF_VACUUM_ENTITY,
    CONF_VACUUM_RETURN_PCT,
    DOMAIN,
    ENTRY_TYPE_APPLIANCE,
)
from custom_components.elettrodomestico_monitor.coordinator import (
    ElettrodomesticoCoordinator,
)
from custom_components.elettrodomestico_monitor.vacuum import _VacuumEntity


def _make_vacuum_entity(hass, *, vacuum_eid="vacuum.k2", battery_eid="",
                         return_pct=None, instance_id="vac_test", slot="1"):
    data = {
        CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE,
        CONF_INSTANCE_ID: instance_id,
        CONF_SLOT: slot,
        CONF_PRESET: "vacuum",
        CONF_VACUUM_ENTITY: vacuum_eid,
        CONF_BATTERY_SENSOR: battery_eid,
    }
    if return_pct is not None:
        data[CONF_VACUUM_RETURN_PCT] = return_pct
    entry = MockConfigEntry(domain=DOMAIN, data=data, title=instance_id)
    entry.add_to_hass(hass)
    coord = ElettrodomesticoCoordinator(hass, entry)
    ent = _VacuumEntity(coord, entry, "K2", slot)
    ent.hass = hass  # normalmente assegnato dalla entity platform di HA
    return ent


# ── D1: _call_vacuum non deve inoltrare comandi a un robot non disponibile ──

async def test_call_vacuum_delivers_when_robot_available(hass):
    """Caso base: il robot è disponibile → il comando viene inoltrato."""
    calls = async_mock_service(hass, "vacuum", "start")
    hass.states.async_set("vacuum.k2", "docked")
    ent = _make_vacuum_entity(hass)

    await ent._call_vacuum("start")

    assert len(calls) == 1
    assert calls[0].data.get("entity_id") == "vacuum.k2"


async def test_call_vacuum_skipped_when_robot_unavailable(hass, caplog):
    """FIX (segnalazione utente v7.0.3, D1): il robot è 'unavailable'
    (tipico per un robot Tuya con WiFi/batteria scarica) — il comando NON
    deve essere inoltrato, e deve comparire solo un log INFO con prefisso
    [EM x<slot>], mai il warning generico di HA su un'entità mancante."""
    calls = async_mock_service(hass, "vacuum", "start")
    hass.states.async_set("vacuum.k2", "unavailable")
    ent = _make_vacuum_entity(hass, slot="211")

    await ent._call_vacuum("start")

    assert calls == []
    assert "[EM x211]" in caplog.text
    assert "ignorato" in caplog.text


async def test_call_vacuum_skipped_when_entity_does_not_exist(hass):
    """L'entità vacuum configurata non esiste affatto in hass.states
    (es. integrazione del robot non ancora caricata, o rimossa) — stesso
    comportamento sicuro di 'unavailable': nessuna chiamata a servizio."""
    calls = async_mock_service(hass, "vacuum", "start")
    # vacuum.k2 non viene mai impostata.
    ent = _make_vacuum_entity(hass)

    await ent._call_vacuum("start")

    assert calls == []


# ── D2: available deve rispecchiare lo stato del robot reale ───────────────

async def test_proxy_is_available_when_robot_is_available(hass):
    hass.states.async_set("vacuum.k2", "cleaning")
    ent = _make_vacuum_entity(hass)
    assert ent.available is True


async def test_proxy_is_unavailable_when_robot_is_unavailable(hass):
    """FIX (segnalazione utente v7.0.3, D2): senza questa property il proxy
    restava 'disponibile' in HA a prescindere dallo stato del robot reale
    (ereditava la disponibilità dal coordinator EM, non dal robot)."""
    hass.states.async_set("vacuum.k2", "unavailable")
    ent = _make_vacuum_entity(hass)
    assert ent.available is False


async def test_proxy_is_available_when_no_vacuum_entity_configured(hass):
    """Nessuna entità vacuum configurata: non c'è nulla da rispecchiare,
    il proxy resta disponibile (coerente con 'activity' che in questo
    stesso caso ritorna IDLE invece di None)."""
    ent = _make_vacuum_entity(hass, vacuum_eid="")
    assert ent.available is True


# ── Punto 4: rientro per batteria scarica con stati robot non standard ─────

async def test_battery_return_fires_for_non_standard_cleaning_state(hass):
    """FIX (segnalazione utente v7.0.3): prima il controllo confrontava lo
    stato del robot con un'allowlist fissa ("cleaning","running","on") —
    uno stato esteso Tuya/cinese come "smart_cleaning" (già riconosciuto
    come 'ciclo attivo' altrove in questo file) non faceva scattare il
    rientro, lasciando il robot senza alcuna rete di sicurezza fino a
    scaricarsi del tutto durante la pulizia."""
    async_mock_service(hass, "vacuum", "return_to_base")
    hass.states.async_set("vacuum.k2", "smart_cleaning")
    hass.states.async_set("sensor.batteria_k2", "15")
    ent = _make_vacuum_entity(hass, battery_eid="sensor.batteria_k2", return_pct=20)

    ent._check_battery_return()
    await hass.async_block_till_done()

    assert ent._return_armed is False  # il rientro è scattato


async def test_battery_return_does_not_fire_when_robot_docked(hass):
    """Non-regressione: col robot già 'docked' (fermo) il rientro non deve
    scattare, a prescindere dal livello di batteria."""
    hass.states.async_set("vacuum.k2", "docked")
    hass.states.async_set("sensor.batteria_k2", "10")
    ent = _make_vacuum_entity(hass, battery_eid="sensor.batteria_k2", return_pct=20)

    ent._check_battery_return()

    assert ent._return_armed is True  # mai scattato
