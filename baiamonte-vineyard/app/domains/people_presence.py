from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


TIMESHEET_PRESENCE_SPECS = (
    ("giancarlo", ("giancarlo", "giancarlo pafumi"), ("person.giancarlo", "device_tracker.iphone_che")),
    ("luca", ("luca", "schiliro", "cognato"), ("person.luca_schiliro_cognato", "device_tracker.luca_iphone")),
    ("sebastian", ("sebastian", "sebastiano", "vinvi", "vinci"), ("person.sebastian_vinvi",)),
    ("mattia", ("mattia",), ("person.mattia",)),
    ("carmella", ("carmela", "carmella"), ("person.carmela", "person.carmella")),
)


def resolve_timesheet_presence_entities(
    worker: str,
    identity_links: Mapping[str, str],
    ha_people: list[dict[str, Any]],
    profiles: Mapping[str, dict[str, Any]],
    match_person: Callable[..., dict[str, Any] | None],
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Resolve a payroll identity to the current HA Person and its trackers."""
    worker_key = worker.casefold()
    selected = next(
        (spec for spec in TIMESHEET_PRESENCE_SPECS if any(alias in worker_key for alias in spec[1])),
        None,
    )
    if not selected:
        return None
    identity_key, aliases, seeded_entities = selected
    linked_entity = identity_links.get(identity_key)
    seeded_person = next((entity for entity in seeded_entities if entity.startswith("person.")), "")
    requested_person = linked_entity or seeded_person
    resolved = match_person(
        {
            "key": identity_key,
            "name": worker,
            "person_entity": requested_person,
            "name_aliases": aliases,
        },
        ha_people,
        profiles.get(requested_person) or {},
    )
    actual_person = str((resolved or {}).get("entity_id") or requested_person)
    attributes = (resolved or {}).get("attributes") or {}
    discovered_trackers = (attributes.get("source"), *(attributes.get("device_trackers") or ()))
    entities = tuple(dict.fromkeys((
        actual_person,
        *(entity for entity in seeded_entities if entity.startswith("device_tracker.")),
        *(entity for entity in discovered_trackers if isinstance(entity, str) and entity.startswith("device_tracker.")),
    )))
    return aliases, entities
