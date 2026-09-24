"""The serialized (on-disk / wire) shape of an `Entity`.

One `entity` line per resolved entity: its member surface forms. It lives in
`domain/entities/` rather than the evaluation harness so `infrastructure/` can read a
persisted resolution without depending on `evaluation/`, symmetric with
`domain/claims/serialization.py`'s `ClaimLine`.

`entity_id` is written for convenience but reading never trusts it: `to_entity`
recomputes the fingerprint from the members, so a hand-edited or older file still
yields the canonical id.
"""

from typing import Literal

from pydantic import BaseModel

from domain.entities.identity import compute_entity_id
from domain.entities.models import Entity


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
