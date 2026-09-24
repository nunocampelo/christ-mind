"""File-backed entity-resolution repository.

Reads the committed resolution bundled under `data/resolutions/` (promoted from the
evaluation harness) into `Entity` objects, one per `entity` line via `to_entity`. The
header line is skipped -- the app reads the partition, not the run's provenance. Exposes
the partition and a `surface_form -> entity_id` index (the same mapping the pair scorer
builds) so callers can resolve a mention to its entity. When a real datastore arrives,
this becomes its seed behind the same signatures so `application/` doesn't change shape.

The promoted file is currently the baseline (lexical-only) resolution; swapping it for
the LLM full-corpus resolution is a data change here, not a code change.
"""

import json
from pathlib import Path

from domain.entities.models import Entity
from domain.entities.serialization import EntityLine

_DATA_FILE = Path(__file__).parent / "data" / "resolutions" / "baseline.jsonl"


def _load_resolution() -> tuple[Entity, ...]:
    if not _DATA_FILE.exists():
        raise FileNotFoundError(f"resolution data file is missing: {_DATA_FILE}")
    entities = []
    for line in _DATA_FILE.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") != "entity":
            continue
        entities.append(EntityLine.model_validate(record).to_entity())
    return tuple(entities)


_ENTITIES: tuple[Entity, ...] = _load_resolution()
_ENTITY_ID_BY_MENTION: dict[str, str] = {
    mention: entity.entity_id
    for entity in _ENTITIES
    for mention in entity.mentions
}


def list_entities() -> tuple[Entity, ...]:
    return _ENTITIES


def entity_for_mention(mention: str) -> Entity | None:
    """The entity a surface form belongs to, or None if the form isn't in the
    resolution (it was never a subject/object the resolver saw)."""
    entity_id = _ENTITY_ID_BY_MENTION.get(mention)
    if entity_id is None:
        return None
    return next(e for e in _ENTITIES if e.entity_id == entity_id)
