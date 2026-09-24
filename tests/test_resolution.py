from collections.abc import Sequence

from application.resolution.prompt import (
    PromptedResolver,
    SYSTEM_PROMPT,
    parse_response,
    user_prompt,
)
from application.resolution.resolve_entities import (
    CandidatePair,
    PairVerdict,
    ResolutionFailedError,
    candidate_pairs,
    resolve,
)
from domain.entities.models import Entity


class StubResolver:
    """Judges pairs from a canned same/different map, keyed on the frozenset of the
    pair's two forms so call order and left/right order don't matter."""

    def __init__(self, same: set[frozenset[str]]):
        self._same = same
        self.seen: list[CandidatePair] = []

    def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
        self.seen = list(pairs)
        return [
            PairVerdict(pair=p, same=frozenset({p.left, p.right}) in self._same)
            for p in pairs
        ]


def _by_members(entities: Sequence[Entity]) -> set[frozenset[str]]:
    return {e.mentions for e in entities}


def test_candidate_pairs_block_on_normalisation_and_head_token():
    pairs = candidate_pairs(["the ego", "ego", "the false ego", "love"])
    members = {frozenset({p.left, p.right}) for p in pairs}

    # "the ego"/"ego" share a normalised form; all three ego forms share head "ego".
    assert frozenset({"the ego", "ego"}) in members
    assert frozenset({"ego", "the false ego"}) in members
    assert frozenset({"the ego", "the false ego"}) in members
    # "love" shares nothing, so it is in no pair.
    assert not any("love" in m for m in members)


def test_head_token_blocking_misses_possessive_modifiers():
    # "the ego's wish" normalises to "ego's wish", head token "wish" (the apostrophe
    # is not stripped), so it does NOT block with "ego". This is a known blocking-
    # recall gap the step-3 pair gold measures with cross-block same-pairs; recorded
    # so a later blocking change is a deliberate decision, not an accident.
    pairs = candidate_pairs(["ego", "the ego's wish"])

    assert pairs == []


def test_candidate_pairs_are_not_all_pairs():
    # Four unrelated head tokens -> zero candidate pairs, not the 6 all-pairs.
    assert candidate_pairs(["love", "fear", "time", "peace"]) == []


def test_transitive_closure_merges_a_chain_into_one_entity():
    resolver = StubResolver(
        same={
            frozenset({"the ego", "ego"}),
            frozenset({"ego", "the false ego"}),
        }
    )

    result = resolve(["the ego", "ego", "the false ego", "love"], resolver)

    assert not result.failed
    assert frozenset({"the ego", "ego", "the false ego"}) in _by_members(
        result.entities
    )
    # An unmatched mention is its own singleton entity, not dropped.
    assert frozenset({"love"}) in _by_members(result.entities)


def test_a_different_verdict_leaves_forms_in_separate_entities():
    resolver = StubResolver(same=set())

    result = resolve(["ego", "the ego"], resolver)

    assert _by_members(result.entities) == {frozenset({"ego"}), frozenset({"the ego"})}


def test_verdict_naming_a_mention_outside_the_pair_is_rejected():
    class WanderingResolver:
        def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
            return [PairVerdict(pair=CandidatePair("fear", "the ego"), same=True)]

    result = resolve(["ego", "the ego"], WanderingResolver())

    assert len(result.rejected) == 1
    # The invented merge is not applied: the two real forms stay separate.
    assert _by_members(result.entities) == {frozenset({"ego"}), frozenset({"the ego"})}


def test_resolution_failure_is_recorded_not_raised():
    class FailingResolver:
        def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
            raise ResolutionFailedError("bad json")

    result = resolve(["ego", "the ego"], FailingResolver())

    assert result.failed
    assert result.entities == ()


def test_parse_response_matches_swapped_left_right_to_the_presented_pair():
    pairs = [CandidatePair("ego", "the ego")]
    reply = '{"verdicts": [{"left": "the ego", "right": "ego", "same": true}]}'

    verdicts = parse_response(reply, pairs)

    assert verdicts == [PairVerdict(pair=pairs[0], same=True)]


def test_parse_response_rejects_non_json():
    try:
        parse_response("not json", [])
    except ResolutionFailedError:
        pass
    else:
        raise AssertionError("expected ResolutionFailedError")


def test_prompted_resolver_skips_the_model_on_no_pairs():
    def complete(system: str, user: str) -> str:
        raise AssertionError("model should not be called with no pairs")

    assert PromptedResolver(complete).judge([]) == []


def test_user_prompt_lists_both_forms_and_system_prompt_states_the_rules():
    text = user_prompt([CandidatePair("ego", "the ego's wish")])

    assert '"ego"' in text and '"the ego\'s wish"' in text
    assert "same thing" in SYSTEM_PROMPT.lower()
