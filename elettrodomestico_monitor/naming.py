# DESC: Single source of truth for entity_id / unique_id construction.
#       Prevents the class of bugs caused by ad-hoc string concatenation
#       (e.g. the historical "xx1" double-prefix bug).
# VERSION: 5.8.4
# CHANGED: 2026-06-11 (data storica ricostruita — campo assente nell'header
#          originale prima dell'audit v6.1.0)
"""Entity naming helpers.

Every entity_id and unique_id in the integration is built here, so the
slot-prefix convention ("x{slot}") lives in exactly one place. The frontend
reads the resolved slot token from a master-sensor attribute instead of
re-deriving it, closing the gap that produced the double-"x" bug.
"""
from __future__ import annotations

from .const import DOMAIN


def slot_token(slot) -> str:
    """Return the canonical slot token, e.g. 1 → 'x1'.

    Accepts an int, a bare string ('1'), or an already-prefixed string ('x1')
    and always returns a single-prefixed token. This is the function that makes
    'xx1' impossible: passing 'x1' back in still yields 'x1'.
    """
    s = str(slot).strip()
    if s.startswith("x") and s[1:].isdigit():
        return s
    return f"x{s}"


def entity_suffix(sfx: str, slot) -> str:
    """Build the entity_id object-id (without the 'sensor.' domain prefix)."""
    return f"{sfx}_{slot_token(slot)}"


def entity_id(domain: str, sfx: str, slot) -> str:
    """Build a full entity_id, e.g. ('sensor', 'cicli_oggi', 1) → 'sensor.cicli_oggi_x1'."""
    return f"{domain}.{entity_suffix(sfx, slot)}"


def unique_id(instance_id, sfx: str, slot) -> str:
    """Build a globally-unique id, stable across restarts."""
    return f"{DOMAIN}_{instance_id}_{sfx}_{slot_token(slot)}"


# Logical-name → entity_id suffix map. The frontend reads the resolved
# entity_ids from a master-sensor attribute ("eids") built with this, so the
# card never concatenates names itself (this is what kills the doppia-x / name
# mismatch class of bugs at the root).
_APPLIANCE_EIDS = {
    "master":        ("sensor",  "time_on_elettrodomestici"),
    "ac":            ("sensor",  "ac_elettrodomestici"),
    "power":         ("sensor",  "potenza_elettrodomestici_w"),
    "energy_oggi":   ("sensor",  "energy_oggi_elettrodomestici"),
    "tempo_oggi":    ("sensor",  "tempo_oggi_elettrodomestici"),
    "cicli_oggi":    ("sensor",  "cicli_oggi_elettrodomestici"),
    "costo_oggi":    ("sensor",  "costo_oggi_elettrodomestici"),
    "costo_energia": ("sensor",  "costo_energia_elettrodomestici"),
    "programma":     ("sensor",  "programma_elettrodomestici"),
    "ultimo_ciclo":  ("sensor",  "ultimo_ciclo_elettrodomestici"),
    "versione":      ("sensor",  "versione_elettrodomestici"),
    "soglia":        ("number",  "soglia_lavoro_elettrodomestici_w"),
    "tempo_innesco": ("number",  "tempo_innesco_elettrodomestici_m"),
    "avvio_ritardato":("number", "avvio_ritardato_elettrodomestici_s"),
    "soglia_rientro":("number",  "soglia_rientro_vacuum"),
    "manutenzione":  ("button",  "manutenzione_elettrodomestici"),
    "reset":         ("button",  "reset_contatori_elettrodomestici"),
    "switch":        ("switch",  "switch_elettrodomestici"),
    "notify_push":   ("switch",  "notifica_push_elettrodomestici"),
    "notify_alexa":  ("switch",  "notifica_alexa_elettrodomestici"),
    "notify_google": ("switch",  "notifica_google_elettrodomestici"),
    "notify_whatsapp":("switch", "notifica_whatsapp_elettrodomestici"),
    "auto_on":       ("time",    "orario_accensione_elettrodomestici"),
    "auto_off":      ("time",    "orario_spegnimento_elettrodomestici"),
    "batteria":      ("sensor",  "batteria_vacuum"),
    "climate":       ("climate", "elettrodomestici"),
}

_IRRIGATION_EIDS = {
    "master":        ("sensor",  "irrigazione_time_on"),
    "litri_oggi":    ("sensor",  "irrigazione_litri_oggi"),
    "portata":       ("sensor",  "irrigazione_portata"),
    "pompa":         ("sensor",  "irrigazione_pompa_w"),
    "master_switch": ("switch",  "irrigazione_master"),
    "programmazione":("switch",  "irrigazione_programmazione"),
}


def build_eids(slot, *, irrigation: bool = False) -> dict:
    """Return {logical_name: entity_id} for a slot, resolved via naming so the
    frontend can consume entity_ids without ever building strings itself."""
    table = _IRRIGATION_EIDS if irrigation else _APPLIANCE_EIDS
    return {name: entity_id(dom, sfx, slot) for name, (dom, sfx) in table.items()}
