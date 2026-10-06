import json
from pathlib import Path

import pytest

from application.extraction.extract_claims import CandidateClaim
from application.extraction.spans import AmbiguousEvidenceError, EvidenceNotFoundError
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.claims.serialization import ClaimLine
from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    DerivedValidationError,
    PropositionSig,
    Support,
)
from domain.derivation.serialization import DerivedGoldFile
from domain.sources.models import Source
from evaluation.claims.fidelity.author import (
    Decision,
    DraftError,
    adjudicate,
    load_draft,
    write_gold,
)
from evaluation.claims.gold import load_gold_claims
from infrastructure.database.sources_acim import list_acim_sources

TEXT = (
    "5. The level-adjustment power of the miracle induces the right perception for healing. "
    "Until this has occurred healing cannot be understood. "
    "Forgiveness is an empty gesture unless it entails correction. "
    "Without this, it is essentially judgemental rather than healing."
)
SOURCE = Source(id="t3-1-5", book="acim", chapter=3, text=TEXT, section=1, paragraph=5)


def _condition_entry(source_id: str = "t3-1-5", evidence: str | None = None) -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id=source_id,
        kind=DerivedKind.CONDITION,
        evidence=evidence or "Forgiveness is an empty gesture unless it entails correction.",
        support=Support.LITERAL,
        condition_text="unless it entails correction",
        attaches_to=PropositionSig(
            subject="forgiveness",
            predicate=Predicate.IS,
            object="empty gesture",
            polarity=Polarity.AFFIRMED,
            mode=Mode.CONDITIONAL,
            attribution=Attribution.COURSE,
        ),
    )


def _description_entry() -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.DESCRIPTION,
        evidence="Without this, it is essentially judgemental rather than healing.",
        support=Support.INTERPRETED,
        description_text="judgemental rather than healing",
        describes=compute_annotation_id(_condition_entry()),
    )


def _gold(*entries: DerivedEntry) -> DerivedGold:
    return DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=entries,
    )


def _candidate(evidence: str = "Forgiveness is an empty gesture") -> CandidateClaim:
    return CandidateClaim(
        subject="forgiveness",
        verb_phrase="is an empty gesture",
        object="empty gesture",
        predicate=Predicate.IS,
        polarity=Polarity.AFFIRMED,
        mode=Mode.CONDITIONAL,
        attribution=Attribution.COURSE,
        evidence=evidence,
    )


def test_valid_gold_round_trips_both_layers(tmp_path: Path) -> None:
    gold = _gold(_condition_entry(), _description_entry())
    candidate = _candidate()

    derived_path, literal_path = write_gold(gold, [candidate], SOURCE, tmp_path)

    reloaded = DerivedGoldFile.model_validate_json(derived_path.read_text()).to_gold()
    assert reloaded.source_id == "t3-1-5"
    assert reloaded.literal_status is AuthoringStatus.AUTHORED
    assert reloaded.derived_status is AuthoringStatus.AUTHORED
    assert {e.annotation_id for e in reloaded.shared} == {
        compute_annotation_id(_condition_entry()),
        compute_annotation_id(_description_entry()),
    }

    claims = load_gold_claims(literal_path, [SOURCE])
    assert len(claims) == 1
    assert claims[0].subject == "forgiveness"
    assert claims[0].object == "empty gesture"
    assert SOURCE.text[claims[0].evidence_start : claims[0].evidence_end] == candidate.evidence


def test_round_trip_against_live_corpus_source(tmp_path: Path) -> None:
    """Author against the real `list_acim_sources()` t3-1-5 (not the hardcoded copy), so a
    future corpus edit that moved this text would fail here instead of silently drifting."""
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    candidate = _candidate()

    _, literal_path = write_gold(_gold(_condition_entry()), [candidate], live, tmp_path)

    claims = load_gold_claims(literal_path, list(list_acim_sources()))
    assert len(claims) == 1
    assert live.text[claims[0].evidence_start : claims[0].evidence_end] == candidate.evidence


def test_literal_line_is_byte_identical_to_claimline_serializer(tmp_path: Path) -> None:
    candidate = _candidate()
    _, literal_path = write_gold(_gold(_condition_entry()), [candidate], SOURCE, tmp_path)

    from application.extraction.extract_claims import anchor_claim

    expected = json.dumps(
        ClaimLine.from_claim(anchor_claim(SOURCE, candidate), candidate.evidence).model_dump()
    )
    assert literal_path.read_text() == expected + "\n"


def test_derived_evidence_not_in_source_raises_and_writes_nothing(tmp_path: Path) -> None:
    bad = _condition_entry(evidence="a quote that does not appear in the passage")
    with pytest.raises(EvidenceNotFoundError):
        write_gold(_gold(bad), [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_derived_evidence_ambiguous_raises(tmp_path: Path) -> None:
    ambiguous = _condition_entry(evidence="healing")  # occurs twice in TEXT
    with pytest.raises(AmbiguousEvidenceError):
        write_gold(_gold(ambiguous), [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_foreign_source_entry_raises(tmp_path: Path) -> None:
    foreign = _condition_entry(source_id="t9-9-9")
    gold = DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(foreign,),
    )
    with pytest.raises(DerivedValidationError):
        write_gold(gold, [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_gold_source_mismatch_raises(tmp_path: Path) -> None:
    other = Source(id="t1-1-1", book="acim", chapter=1, text=TEXT)
    with pytest.raises(DerivedValidationError):
        write_gold(_gold(_condition_entry()), [], other, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_duplicate_bundle_entry_raises(tmp_path: Path) -> None:
    dup = _condition_entry()
    gold = _gold(dup, _condition_entry())  # same recomputed id
    with pytest.raises(DerivedValidationError):
        write_gold(gold, [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_literal_candidate_with_bad_span_raises(tmp_path: Path) -> None:
    bad = _candidate(evidence="not a substring of this source")
    with pytest.raises(EvidenceNotFoundError):
        write_gold(_gold(_condition_entry()), [bad], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_literal_candidate_ambiguous_raises(tmp_path: Path) -> None:
    ambiguous = _candidate(evidence="healing")  # occurs more than once in TEXT
    with pytest.raises(AmbiguousEvidenceError):
        write_gold(_gold(_condition_entry()), [ambiguous], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_mid_bundle_failure_leaves_both_files_absent(tmp_path: Path) -> None:
    good = _condition_entry()
    bad = _condition_entry(evidence="this quote is nowhere in the passage")
    gold = _gold(good, bad)
    with pytest.raises(EvidenceNotFoundError):
        write_gold(gold, [_candidate()], SOURCE, tmp_path)
    assert not (tmp_path / "t3-1-5.derived.json").exists()
    assert not (tmp_path / "t3-1-5.jsonl").exists()
    assert list(tmp_path.iterdir()) == []


# --- interactive front-end: adjudicate (pure) ---------------------------------------------


def _ided_gold(*entries: DerivedEntry) -> DerivedGold:
    """Entries with their annotation_id filled in (the shape adjudicate indexes against)."""
    with_ids = tuple(
        DerivedEntry(**{**e.__dict__, "annotation_id": compute_annotation_id(e)}) for e in entries
    )
    return DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.UNAUTHORED,
        derived_status=AuthoringStatus.UNAUTHORED,
        shared=with_ids,
    )


def test_adjudicate_accepts_selected_and_flips_to_authored() -> None:
    cond, desc = _condition_entry(), _description_entry()
    gold = _ided_gold(cond, desc)
    decisions = {gold.shared[0].annotation_id: Decision.ACCEPT, gold.shared[1].annotation_id: Decision.SKIP}

    result = adjudicate(gold, [], decisions, [])

    assert result.gold.derived_status is AuthoringStatus.AUTHORED
    assert [e.evidence for e in result.gold.shared] == [cond.evidence]
    assert result.nothing_accepted is False


def test_adjudicate_zero_accepted_stays_unauthored() -> None:
    gold = _ided_gold(_condition_entry())
    result = adjudicate(gold, [_candidate()], {gold.shared[0].annotation_id: Decision.SKIP}, [Decision.SKIP])

    assert result.nothing_accepted is True
    assert result.gold.derived_status is AuthoringStatus.UNAUTHORED
    assert result.gold.shared == ()
    assert result.literal_claims == ()


def test_adjudicate_default_is_skip_for_unnamed_entry() -> None:
    gold = _ided_gold(_condition_entry(), _description_entry())
    result = adjudicate(gold, [], {gold.shared[0].annotation_id: Decision.ACCEPT}, [])
    assert [e.evidence for e in result.gold.shared] == [_condition_entry().evidence]


def test_adjudicate_literal_decisions_are_per_entry() -> None:
    gold = _ided_gold(_condition_entry())
    a, b = _candidate(), _candidate(evidence="healing cannot be understood")
    result = adjudicate(
        gold, [a, b], {gold.shared[0].annotation_id: Decision.ACCEPT}, [Decision.ACCEPT, Decision.SKIP]
    )
    assert [c.evidence for c in result.literal_claims] == [a.evidence]


def test_accepted_subset_that_strands_describes_link_is_rejected(tmp_path: Path) -> None:
    """Skipping the condition the description points at leaves a dangling describes link; the
    accepted subset must be rejected on write, not silently written."""
    cond, desc = _condition_entry(), _description_entry()
    gold = _ided_gold(cond, desc)
    result = adjudicate(
        gold, [], {gold.shared[0].annotation_id: Decision.SKIP, gold.shared[1].annotation_id: Decision.ACCEPT}, []
    )
    with pytest.raises(ValueError):  # describes-link / check_gold rejection
        write_gold(result.gold, result.literal_claims, SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


# --- interactive front-end: draft loading -------------------------------------------------


def test_load_draft_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(DraftError):
        load_draft("t3-1-5", drafts_dir=tmp_path)


def test_load_draft_malformed_json_raises(tmp_path: Path) -> None:
    (tmp_path / "t3-1-5.draft.json").write_text("{ not valid json")
    with pytest.raises(DraftError):
        load_draft("t3-1-5", drafts_dir=tmp_path)


def test_load_committed_draft_round_trips(tmp_path: Path) -> None:
    """The committed t3-1-5 draft loads, adjudicates-accept-all, and writes gold that reloads."""
    gold, literal = load_draft("t3-1-5")
    assert gold.derived_status is AuthoringStatus.UNAUTHORED  # draft stays unauthored on disk
    decisions = {e.annotation_id: Decision.ACCEPT for e in gold.shared}
    result = adjudicate(gold, literal, decisions, [Decision.ACCEPT] * len(literal))

    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    derived_path, literal_path = write_gold(result.gold, result.literal_claims, live, tmp_path)
    reloaded = DerivedGoldFile.model_validate_json(derived_path.read_text()).to_gold()
    assert reloaded.derived_status is AuthoringStatus.AUTHORED
    assert len(reloaded.shared) == len(gold.shared)
    assert len(load_gold_claims(literal_path, list(list_acim_sources()))) == len(literal)


# --- interactive front-end: the shell ------------------------------------------------------


def _scripted_reader(keys: list[str]):
    it = iter(keys)

    def read(_prompt: str) -> str:
        return next(it)

    return read


def test_run_interactive_quit_stops_and_accepts_nothing_before_it() -> None:
    from evaluation.claims.fidelity.author import _run_interactive

    gold, literal = load_draft("t3-1-5")
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    out: list[str] = []
    # quit immediately on the first derived entry
    result = _run_interactive(live, gold, literal, _scripted_reader(["q"]), out.append)

    assert result.nothing_accepted is True
    assert result.gold.derived_status is AuthoringStatus.UNAUTHORED
    assert any("Source t3-1-5" in line for line in out)
    assert any("anchored" in line for line in out)


def test_run_interactive_accept_all_then_write(tmp_path: Path) -> None:
    from evaluation.claims.fidelity.author import _run_interactive

    gold, literal = load_draft("t3-1-5")
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    keys = ["a"] * (len(gold.shared) + len(literal))
    result = _run_interactive(live, gold, literal, _scripted_reader(keys), lambda _s: None)

    derived_path, _ = write_gold(result.gold, result.literal_claims, live, tmp_path)
    assert DerivedGoldFile.model_validate_json(derived_path.read_text()).to_gold().derived_status is AuthoringStatus.AUTHORED


def test_main_unknown_source_raises() -> None:
    from evaluation.claims.fidelity.author import main

    with pytest.raises(DraftError):
        main(["--source", "nonexistent-source"])


def test_accepted_bad_span_entry_still_rejected_through_write(tmp_path: Path) -> None:
    """The 0041->0042 seam: a bad-span entry accepted via adjudicate must still raise through
    write_gold and leave nothing written -- the front-end must not bypass the core."""
    bad = _condition_entry(evidence="this quote is nowhere in the passage")
    gold = _ided_gold(bad)
    result = adjudicate(gold, [], {gold.shared[0].annotation_id: Decision.ACCEPT}, [])
    with pytest.raises(EvidenceNotFoundError):
        write_gold(result.gold, result.literal_claims, SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_adjudicate_sets_each_layer_status_independently() -> None:
    """Accepting derived-only must leave the empty literal layer UNAUTHORED (and vice versa),
    not couple both statuses to a single flag."""
    gold = _ided_gold(_condition_entry())
    cand = _candidate()

    derived_only = adjudicate(gold, [cand], {gold.shared[0].annotation_id: Decision.ACCEPT}, [Decision.SKIP])
    assert derived_only.gold.derived_status is AuthoringStatus.AUTHORED
    assert derived_only.gold.literal_status is AuthoringStatus.UNAUTHORED

    literal_only = adjudicate(gold, [cand], {gold.shared[0].annotation_id: Decision.SKIP}, [Decision.ACCEPT])
    assert literal_only.gold.literal_status is AuthoringStatus.AUTHORED
    assert literal_only.gold.derived_status is AuthoringStatus.UNAUTHORED


def test_run_interactive_quit_in_literal_loop_keeps_derived_drops_literal() -> None:
    from evaluation.claims.fidelity.author import _run_interactive

    gold, literal = load_draft("t3-1-5")
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    # accept both derived entries, then quit at the first literal prompt
    keys = ["a"] * len(gold.shared) + ["q"]
    result = _run_interactive(live, gold, literal, _scripted_reader(keys), lambda _s: None)

    assert len(result.accepted_ids) == len(gold.shared)
    assert result.literal_claims == ()


def test_run_interactive_unknown_key_defaults_to_skip() -> None:
    from evaluation.claims.fidelity.author import _run_interactive

    gold, literal = load_draft("t3-1-5")
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    keys = ["xyz", ""] + ["s"] * (len(gold.shared) + len(literal))
    result = _run_interactive(live, gold, literal, _scripted_reader(keys), lambda _s: None)

    assert result.nothing_accepted is True


def test_render_entry_shows_each_kind_content() -> None:
    """The author must see what an entry MEANS, not just its kind + quote (an occurrence must
    name its concept + scope, a requirement its reframed proposition, a reference its
    referent) -- otherwise accept/skip is blind."""
    from evaluation.claims.fidelity.author import _render_entry

    occ = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.OCCURRENCE,
        evidence="unless it entails correction",
        support=Support.INTERPRETED,
        base_concept="forgiveness",
        scope="lacking correction",
    )
    rendered = _render_entry(occ, SOURCE, {})
    assert "forgiveness" in rendered
    assert "lacking correction" in rendered
    assert "unless it entails correction" in rendered  # evidence still shown
    assert "interpreted" in rendered

    req = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.REQUIREMENT,
        evidence="Forgiveness is an empty gesture unless it entails correction.",
        support=Support.INTERPRETED,
        reframed_proposition=PropositionSig(
            subject="forgiveness",
            predicate=Predicate.REQUIRES,
            object="correction",
            polarity=Polarity.AFFIRMED,
            mode=Mode.CONDITIONAL,
            attribution=Attribution.COURSE,
        ),
    )
    req_rendered = _render_entry(req, SOURCE, {})
    assert "forgiveness" in req_rendered
    assert "requires" in req_rendered
    assert "correction" in req_rendered


def test_render_entry_shows_span_error_without_crashing() -> None:
    from evaluation.claims.fidelity.author import _render_entry

    bad = _condition_entry(evidence="a quote that is not in the passage")
    rendered = _render_entry(bad, SOURCE, {})
    assert "SPAN ERROR" in rendered


def test_render_candidate_shows_polarity_mode_attribution() -> None:
    """A literal claim's polarity/mode/attribution are part of its identity (a conditional read
    as an assertion, or a dropped negation, is a different claim), so the author must see them,
    not just subject + verb phrase."""
    from evaluation.claims.fidelity.author import _render_candidate

    conditional = CandidateClaim(
        subject="forgiveness",
        verb_phrase="is an empty gesture",
        object="empty gesture",
        predicate=Predicate.IS,
        polarity=Polarity.AFFIRMED,
        mode=Mode.CONDITIONAL,
        attribution=Attribution.COURSE,
        evidence="Forgiveness is an empty gesture unless it entails correction.",
    )
    rendered = _render_candidate(conditional)
    assert "conditional" in rendered
    assert "affirmed" in rendered
    assert "course" in rendered
    assert "forgiveness" in rendered

    negated = CandidateClaim(
        subject="healing",
        verb_phrase="cannot be understood",
        object=None,
        predicate=Predicate.OTHER,
        polarity=Polarity.NEGATED,
        mode=Mode.CONDITIONAL,
        attribution=Attribution.COURSE,
        evidence="Until this has occurred healing cannot be understood.",
    )
    neg_rendered = _render_candidate(negated)
    assert "NOT" in neg_rendered  # negation visible
    assert "(no object)" in neg_rendered  # object-less shown explicitly, not blank


def test_render_description_names_target_reading_not_raw_id() -> None:
    """A description must show the READING of the entry it describes, not a bare fingerprint,
    so the author isn't asked to map a hex id back to an entry in their head."""
    from evaluation.claims.fidelity.author import _render_entry

    occ = DerivedEntry(
        annotation_id=compute_annotation_id(
            DerivedEntry(
                annotation_id="",
                source_id="t3-1-5",
                kind=DerivedKind.OCCURRENCE,
                evidence="unless it entails correction",
                support=Support.INTERPRETED,
                base_concept="forgiveness",
                scope="lacking correction",
            )
        ),
        source_id="t3-1-5",
        kind=DerivedKind.OCCURRENCE,
        evidence="unless it entails correction",
        support=Support.INTERPRETED,
        base_concept="forgiveness",
        scope="lacking correction",
    )
    desc = _description_entry()  # describes the condition id by default; repoint at the occurrence
    desc = DerivedEntry(**{**desc.__dict__, "describes": occ.annotation_id})

    rendered = _render_entry(desc, SOURCE, {occ.annotation_id: occ})
    assert "forgiveness" in rendered  # target's reading, surfaced
    assert "lacking correction" in rendered
    assert occ.annotation_id not in rendered  # the raw id is NOT shown when resolvable
