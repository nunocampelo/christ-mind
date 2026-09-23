import json
from pathlib import Path

from evaluation.claims.corpus_survey import survey


def _claim(
    source_id: str,
    subject: str,
    verb_phrase: str,
    predicate: str,
    attribution: str,
    evidence: str,
) -> dict[str, object]:
    return {
        "type": "claim",
        "source_id": source_id,
        "subject": subject,
        "verb_phrase": verb_phrase,
        "object": None,
        "predicate": predicate,
        "polarity": "affirmed",
        "mode": "assertion",
        "attribution": attribution,
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


def test_lists_ego_candidates_with_their_evidence(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _claim("t4-1", "ego", "believes", "other", "ego", "the ego believes it"),
            _claim("t1-1", "love", "is", "is", "course", "love is all"),
        ],
    )

    text = survey(run)

    assert "ego: 1 claims across 1 sources" in text
    assert "[t4-1] ego | other" in text
    assert "the ego believes it" in text


def test_tallies_other_verbs_by_normalised_phrase_and_source_count(tmp_path: Path):
    run = _write_run(
        tmp_path,
        [
            _claim("t1-1", "a", "The believes", "other", "course", "x"),
            _claim("t2-1", "b", "believes", "other", "course", "y"),
            _claim("t3-1", "c", "causes", "causes", "course", "z"),
        ],
    )

    text = survey(run)

    # "The believes" normalises to "believes" (leading determiner dropped), so
    # the two `other` claims collapse to one verb spanning two sources; the
    # `causes` claim is not an `other` verb and is excluded.
    assert "2  (2 sources)  'believes'" in text
    assert "'causes'" not in text
