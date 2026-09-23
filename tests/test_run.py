import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from application.extraction.extract_claims import CandidateClaim, ExtractionFailedError
from domain.claims.models import Claim
from domain.sources.models import Source
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.run import GOLD_FILES, Split, run
from infrastructure.database.sources_acim import list_acim_sources

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)


class GoldEchoExtractor:
    """Returns exactly the gold claims, so any score below perfect is a bug in
    the runner's plumbing rather than in an extractor.
    """

    def __init__(self, gold: Sequence[Claim], sources: Sequence[Source]):
        texts = {source.id: source.text for source in sources}
        self._by_source: dict[str, list[CandidateClaim]] = {}
        for claim in gold:
            evidence = texts[claim.source_id][claim.evidence_start : claim.evidence_end]
            self._by_source.setdefault(claim.source_id, []).append(
                CandidateClaim(
                    subject=claim.subject,
                    verb_phrase=claim.verb_phrase,
                    object=claim.object,
                    predicate=claim.predicate,
                    polarity=claim.polarity,
                    mode=claim.mode,
                    attribution=claim.attribution,
                    evidence=evidence,
                )
            )

    def extract(self, source: Source) -> Sequence[CandidateClaim]:
        return self._by_source.get(source.id, [])


def _gold(split: Split, sources: Sequence[Source]) -> list[Claim]:
    return [c for path in GOLD_FILES[split] for c in load_gold_claims(path, sources)]


def _read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_echoing_the_dev_gold_scores_perfectly(tmp_path: Path):
    sources = list_acim_sources()
    gold = _gold(Split.DEV, sources)

    outcome = run(
        GoldEchoExtractor(gold, sources), "echo", Split.DEV, sources, tmp_path, NOW
    )

    assert outcome.report is not None
    assert outcome.report.strict.true_positives == len(gold)
    assert outcome.report.strict.precision == outcome.report.strict.recall == 1.0
    assert outcome.result.rejected == ()


def test_run_file_has_header_then_one_line_per_claim(tmp_path: Path):
    sources = list_acim_sources()
    gold = _gold(Split.DEV, sources)

    outcome = run(
        GoldEchoExtractor(gold, sources), "echo", Split.DEV, sources, tmp_path, NOW
    )

    assert outcome.path == tmp_path / "20260923T120000Z.jsonl"
    header, *rest = _read_lines(outcome.path)
    assert header["type"] == "header"
    assert header["extractor"] == "echo"
    assert header["split"] == "dev"
    assert header["prompt_version"] is None
    assert len(rest) == len(gold)
    assert {line["type"] for line in rest} == {"claim"}
    crucifixion = next(line for line in rest if line["subject"] == "crucifixion")
    assert crucifixion["evidence"] == "The crucifixion did NOT establish the Atonement."


def test_claim_lines_lead_with_the_human_scannable_fields(tmp_path: Path):
    sources = list_acim_sources()
    gold = _gold(Split.DEV, sources)

    outcome = run(
        GoldEchoExtractor(gold, sources), "echo", Split.DEV, sources, tmp_path, NOW
    )

    _, first_claim, *_ = _read_lines(outcome.path)
    assert list(first_claim) == [
        "type",
        "claim_id",
        "source_id",
        "subject",
        "verb_phrase",
        "object",
        "predicate",
        "polarity",
        "mode",
        "attribution",
        "evidence",
        "evidence_start",
        "evidence_end",
    ]


def test_holdout_runs_only_the_holdout_passages(tmp_path: Path):
    sources = list_acim_sources()
    extractor = GoldEchoExtractor(_gold(Split.DEV, sources), sources)

    outcome = run(extractor, "echo", Split.HOLDOUT, sources, tmp_path, NOW)

    assert outcome.result.claims == ()
    assert outcome.report is not None
    assert outcome.report.strict.false_negatives == len(
        _gold(Split.HOLDOUT, sources)
    )


def test_hashes_change_only_when_passages_or_gold_change(tmp_path: Path):
    sources = list_acim_sources()
    extractor = GoldEchoExtractor([], sources)

    first = run(extractor, "a", Split.DEV, sources, tmp_path / "a", NOW)
    second = run(extractor, "b", Split.DEV, sources, tmp_path / "b", NOW)
    holdout = run(extractor, "c", Split.HOLDOUT, sources, tmp_path / "c", NOW)

    [first_header] = _read_lines(first.path)
    [second_header] = _read_lines(second.path)
    [holdout_header] = _read_lines(holdout.path)
    for key in ("passages_sha256", "gold_sha256"):
        assert first_header[key] == second_header[key]
        assert first_header[key] != holdout_header[key]


def test_corpus_run_targets_every_source_and_is_unscored(tmp_path: Path):
    sources = list_acim_sources()
    extractor = GoldEchoExtractor(_gold(Split.DEV, sources), sources)

    outcome = run(extractor, "echo", Split.CORPUS, sources, tmp_path, NOW)

    assert outcome.report is None
    header, *rest = _read_lines(outcome.path)
    assert header["split"] == "corpus"
    assert header["score"] is None
    assert header["gold_sha256"] == ""
    claim_lines = [line for line in rest if line["type"] == "claim"]
    covered = {line["source_id"] for line in claim_lines}
    dev_ids = {c.source_id for c in _gold(Split.DEV, sources)}
    assert dev_ids <= covered
    assert covered <= {source.id for source in sources}


def test_failed_sources_are_written_to_the_run_file(tmp_path: Path):
    class AlwaysFails:
        def extract(self, source: Source) -> Sequence[CandidateClaim]:
            raise ExtractionFailedError("unusable response")

    outcome = run(
        AlwaysFails(), "fails", Split.HOLDOUT, list_acim_sources(), tmp_path, NOW
    )

    header, *rest = _read_lines(outcome.path)
    assert header["failed_sources"] == 5
    assert {line["type"] for line in rest} == {"failed"}
