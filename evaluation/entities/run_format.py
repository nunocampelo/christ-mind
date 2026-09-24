"""The on-disk shape of a resolution file, shared by whatever writes and reads it.

A resolution is a partition of the mention universe into entities. It is written
beside the claim runs, one `entity` line per entity, behind a `header` line that
carries the `passages_sha256` of the corpus run it was resolved from -- so a
resolution can be checked for drift against that run before its entities are trusted,
the same discipline as `evaluation/claims/run.py`'s header. Keeping one model means a
renamed or dropped field fails at validation instead of silently as a missing key.

`entity_id` is written for convenience but reading never trusts it: `to_entity`
recomputes the fingerprint from the members, so a hand-edited or older file still
yields the canonical id.
"""

from typing import Literal

from pydantic import BaseModel

from domain.entities.identity import compute_entity_id
from domain.entities.models import Entity


class ResolutionHeader(BaseModel):
    type: Literal["header"] = "header"
    run_id: str
    created_at: str
    resolver: str
    resolver_prompt_version: str | None
    source_run_id: str
    passages_sha256: str
    mentions: int


class EntityLine(BaseModel):
    type: Literal["entity"] = "entity"
    entity_id: str
    mentions: list[str]

    @classmethod
    def from_entity(cls, entity: Entity) -> "EntityLine":
        return cls(entity_id=entity.entity_id, mentions=sorted(entity.mentions))

    def to_entity(self) -> Entity:
        members = frozenset(self.mentions)
        return Entity(entity_id=compute_entity_id(members), mentions=members)
