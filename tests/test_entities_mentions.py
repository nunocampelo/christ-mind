import json
from pathlib import Path

from evaluation.entities.mentions import (
    Mention,
    block_by_normalization,
    collect_mentions,
    survey,
)


def _claim(
    source_id: str,
    subject: str,
    object: str | None,
    evidence: str,
) -> dict[str, object]:
    return {
        "type": "claim",
        "source_id": source_id,
        "subject": subject,
        "verb_phrase": "is",
        "object": object,
        "predicate": "is",
        "polarity": "affirmed",
        "mode": "assertion",
        "attribution": "course",
        "evidence": evidence,
        "evidence_start": 0,
        "evidence_end": len(evidence),
    }


def _write_run(tmp_path: Path, claims: list[dict[str, object]]) -> Path:
    lines: list[dict[str, object]] = [{"type": "header", "split": "corpus"}, *claims]
    path = tmp_path / "run.jsonl"
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    )
    return path


def test_collect_mentions_pools_subject_and_object_and_counts_sources(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _claim("t1-1", "the ego", "fear", "the ego is fear"),
            _claim("t2-1", "love", "the ego", "love undoes the ego"),
            _claim("t2-1", "love", None, "love is"),
        ],
    )
    from evaluation.entities.mentions import _load_claims

    mentions = {m.text: m for m in collect_mentions(_load_claims(run))}

    assert mentions["the ego"] == Mention(
        text="the ego", occurrences=2, source_ids=frozenset({"t1-1", "t2-1"})
    )
    assert mentions["love"].occurrences == 2
    assert mentions["fear"].occurrences == 1
    # object None never becomes a mention
    assert None not in mentions


def test_block_by_normalization_groups_determiner_variants(tmp_path: Path):
    mentions = [
        Mention("the ego", 3, frozenset({"t1-1"})),
        Mention("ego", 1, frozenset({"t2-1"})),
        Mention("love", 5, frozenset({"t3-1"})),
    ]

    blocks = block_by_normalization(mentions)

    assert {m.text for m in blocks["ego"]} == {"the ego", "ego"}
    assert {m.text for m in blocks["love"]} == {"love"}


def test_survey_reports_universe_size_and_free_floor(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _claim("t1-1", "the ego", "fear", "the ego is fear"),
            _claim("t2-1", "ego", "love", "ego fears love"),
        ],
    )

    text = survey(run)

    # "the ego"/"ego" collapse to one block; "fear" and "love" stay singletons.
    assert "mention universe: 4 distinct surface forms, 4 occurrences" in text
    assert "3 blocks" in text
    assert "2 singleton blocks" in text
    assert "1 multi-member blocks collapsing 2 surface forms" in text
    assert "'the ego'" in text and "'ego'" in text
