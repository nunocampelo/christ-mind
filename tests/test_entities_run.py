from evaluation.entities.gold import GoldPair
from evaluation.entities.run import LexicalBaseline, score


def test_baseline_merges_normalised_equal_pairs_only():
    gold = [
        GoldPair("ego", "the ego", same=True),  # normalise-equal -> merged, tp
        GoldPair("God's Will", "Will of God", same=True),  # not equal -> apart, fn
        GoldPair("God", "Son of God", same=False),  # not equal -> apart, ok
    ]

    report = score(LexicalBaseline(), gold)

    assert report.score.true_positives == 1
    assert report.score.false_negatives == 1
    assert report.score.false_positives == 0
