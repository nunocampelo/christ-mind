"""Detects a question that asks HOW an entity acts or relates ("how does God think?",
"what is the Mind of God?") and returns a structured probe naming the target entity and
the aspect asked about -- the auto-seed for the `entity_relation` channel.

Siblings `concept_question`/`meta_question` return bare supplemental query terms because
their target is a `find_claims` keyword search. This channel is different: it resolves an
*entity* and ranks by an *aspect*, two separate values the retrieval tool takes as separate
arguments. So this returns a `RelationalProbe(target, aspect, reason)` struct rather than a
flat term -- the shape a future query planner would also emit, so it can replace this
syntactic detector without the orchestrator's seed path or the retrieval channel changing.

Deliberately narrow (narrow-first, per the A/B interpretability goal): fires only on the two
explicit shapes above, never on a bare "what is X" (that's `concept_question`'s definitional
job) or any other framing. A false positive would route a non-relational question through
the aspect-weighted channel; a miss just means the channel isn't auto-seeded and the LLM may
still reach it. The detector is pure syntax -- it never resolves the entity or touches the
corpus; `describe_entity` does the resolution across the MCP boundary.
"""

import re
from dataclasses import dataclass

# Surface verbs/nouns -> the aspect key `_ASPECT_FAMILIES` (ranking.py) expands. The aspect
# is WHERE to look, not an assertion of synonymy: "think"/"know"/"mind" all ask about the
# thinking aspect, whose stem family the ranker owns. A verb not here yields no aspect, and
# the probe falls back to entity-participation ranking (empty aspect set) rather than
# guessing -- the question still routes to the entity, just unweighted.
_ASPECT_OF: dict[str, str] = {
    "think": "thinking",
    "thinks": "thinking",
    "thought": "thinking",
    "know": "thinking",
    "knows": "thinking",
    "mind": "thinking",
    "create": "creating",
    "creates": "creating",
    "make": "creating",
    "makes": "creating",
    "give": "creating",
    "gives": "creating",
    "extend": "creating",
    "extends": "creating",
    "will": "willing",
    "wills": "willing",
    "intend": "willing",
    "intends": "willing",
    "choose": "willing",
    "chooses": "willing",
    "love": "loving",
    "loves": "loving",
    "care": "loving",
    "cares": "loving",
}

# "how does X <verb>?" -- X is the target, the verb maps to an aspect. The target is
# non-greedy up to the verb so "how does the ego attack" captures "the ego", not "the ego
# attack". A leading article is kept in the captured target: describe_entity resolves
# surface forms, so "the ego" and "ego" both land on the same entity.
_HOW_DOES = re.compile(
    r"^\s*how\s+(?:does|do)\s+(?P<target>.+?)\s+(?P<verb>[a-z]+)\s*[.?!]*\s*$",
    re.IGNORECASE,
)

# "what is the Mind/Will of X?" -- a possessive construction naming an entity through one
# of its aspects. The aspect word itself ("mind", "will") names the aspect; X is the target.
_ASPECT_OF_X = re.compile(
    r"^\s*what(?:'s| is)\s+the\s+(?P<aspect_word>mind|will|thought|thoughts|love)"
    r"\s+of\s+(?P<target>.+?)\s*[.?!]*\s*$",
    re.IGNORECASE,
)

# Aspect-naming nouns in the possessive shape -> the same aspect keys. "mind"/"thought" ask
# about thinking, "will" about willing, "love" about loving.
_POSSESSIVE_ASPECT: dict[str, str] = {
    "mind": "thinking",
    "thought": "thinking",
    "thoughts": "thinking",
    "will": "willing",
    "love": "loving",
}


@dataclass(frozen=True)
class RelationalProbe:
    """A routing instruction for the `entity_relation` channel: seed `describe_entity` with
    `target` (the mention to resolve) and `aspects` (what the question asks about, possibly
    empty when the verb maps to no known aspect). `reason` records why the probe fired, for
    the retrieval trace -- it travels with the seed, it is not a stored inference."""

    target: str
    aspects: tuple[str, ...]
    reason: str


def _probe_clause(clause: str) -> RelationalProbe | None:
    match = _HOW_DOES.match(clause)
    if match:
        target = match.group("target").strip()
        verb = match.group("verb").strip().lower()
        if not target:
            return None
        aspect = _ASPECT_OF.get(verb)
        aspects = (aspect,) if aspect is not None else ()
        return RelationalProbe(
            target=target, aspects=aspects, reason=f"how-does: {verb}"
        )

    match = _ASPECT_OF_X.match(clause)
    if match:
        target = match.group("target").strip()
        aspect_word = match.group("aspect_word").strip().lower()
        if not target:
            return None
        aspect = _POSSESSIVE_ASPECT[aspect_word]
        return RelationalProbe(
            target=target, aspects=(aspect,), reason=f"aspect-of: {aspect_word}"
        )

    return None


def relational_probe(text: str) -> RelationalProbe | None:
    """The relational probe for a "how does X <verb>?" / "what is the Mind of X?" question,
    or None when the text is neither shape. Pure syntax: the target is returned as written
    (article kept) for `describe_entity` to resolve; aspects name the ranking weight.

    A prompt may carry more than one sentence ("How does God think? What is the Mind of
    God?"), so each clause is matched independently and the first that yields a probe wins
    -- the patterns stay single-clause anchored (so a trailing clause can't be swallowed
    into the target) while a multi-sentence prompt still routes."""
    for clause in re.split(r"[.?!]+", " ".join(text.split())):
        clause = clause.strip()
        if not clause:
            continue
        probe = _probe_clause(clause)
        if probe is not None:
            return probe
    return None
