from domain.entities.identity import compute_entity_id
from domain.entities.models import Entity
from evaluation.entities.gold import GoldPair
from evaluation.entities.score import PairScore, blocking_recall, score_pairs


def _entity(*mentions: str) -> Entity:
    members = frozenset(mentions)
    return Entity(entity_id=compute_entity_id(members), mentions=members)


def test_scores_tp_fp_fn_from_the_partition():
    entities = [_entity("ego", "the ego"), _entity("fear"), _entity("mind")]
    gold = [
        GoldPair("ego", "the ego", same=True),  # merged, gold same -> tp
        GoldPair("fear", "mind", same=True),  # apart, gold same -> fn
        GoldPair("ego", "fear", same=False),  # apart, gold different -> ok
    ]

    report = score_pairs(entities, gold)

    assert report.score == PairScore(true_positives=1, false_positives=0, false_negatives=1)
    assert report.score.recall == 0.5


def test_a_wrong_merge_of_a_different_pair_is_a_false_positive():
    entities = [_entity("God", "Son of God")]
    gold = [GoldPair("God", "Son of God", same=False)]

    report = score_pairs(entities, gold)

    assert report.score == PairScore(true_positives=0, false_positives=1, false_negatives=0)
    assert report.score.precision == 0.0


def test_blocking_recall_flags_a_same_pair_the_blocker_never_proposes():
    # "God's Will"/"Will of God": heads "will" and "god", so the blocker misses it;
    # "ego"/"the ego" share a normalised form, so it is proposed.
    gold = [
        GoldPair("ego", "the ego", same=True),
        GoldPair("God's Will", "Will of God", same=True),
    ]

    assert blocking_recall(gold) == 0.5


def test_blocking_recall_ignores_different_pairs():
    gold = [GoldPair("ego", "the ego", same=True), GoldPair("God", "Son of God", same=False)]

    # Only the one same-pair counts, and the blocker proposes it.
    assert blocking_recall(gold) == 1.0
