from dataclasses import dataclass


@dataclass(frozen=True)
class Entity:
    """A set of surface forms that entity resolution judged to name the same thing.

    An entity is a partition cell over observed mentions, never an invented canonical
    name (see the increment #6 plan): its members are the exact surface forms the
    extractor produced, and picking a human-facing label among them is a presentation
    concern deferred to retrieval. `entity_id` is the content fingerprint from
    `identity.py`, so the same set of members always yields the same id -- an entity
    has no surrogate key.
    """

    entity_id: str
    mentions: frozenset[str]
