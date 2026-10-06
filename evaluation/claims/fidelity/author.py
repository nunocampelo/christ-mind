"""Validated write path for a passage's fidelity gold -- the safe "save" the interactive
authoring front-end (built next, on top of this) calls once the author has drafted entries.

It never decides what the gold is: it takes drafted typed entries (a `DerivedGold` plus the
literal `CandidateClaim`s) and either writes both sidecars in the shape the existing loaders
read back, or rejects the draft loudly. Every derived and literal evidence quote is anchored
against the real source (`validate_span`, reused through `anchor_claim` for literals), and the
bundle runs `check_gold` -- the same checks the loader/scorer use, so a foreign source, a
duplicate, a missing or ambiguous quote fails here instead of corrupting the benchmark.
Validation of both layers completes before either file is written, so a mid-draft failure
leaves nothing half-written.
"""

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from application.extraction.extract_claims import (
    CandidateClaim,
    anchor_claim,
    parse_candidate,
)
from application.extraction.spans import EvidenceError, validate_span
from domain.claims.models import Claim
from domain.claims.serialization import ClaimLine
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    DerivedValidationError,
    PropositionSig,
    Variant,
)
from domain.derivation.serialization import DerivedGoldFile
from domain.sources.models import Source
from infrastructure.database.claims import list_claims
from infrastructure.database.sources_acim import list_acim_sources

DRAFTS_DIR = Path(__file__).parent / "drafts"
GOLD_DIR = Path(__file__).parent / "gold"


def _derived_entries(gold: DerivedGold) -> list[DerivedEntry]:
    entries = list(gold.shared)
    for variant in gold.variants:
        entries.extend(variant.entries)
    return entries


def _literal_line(claim: Claim, evidence: str) -> str:
    """One literal `.jsonl` line, in the shape `load_gold_claims` reads back: a `ClaimLine`
    carrying `source_id`. The written `claim_id`/offsets are advisory -- `anchor_claim`
    recomputes them on load -- but writing through `ClaimLine` keeps the on-disk shape
    identical to every other claim writer."""
    return json.dumps(ClaimLine.from_claim(claim, evidence).model_dump())


def write_gold(
    gold: DerivedGold,
    literal_claims: Sequence[CandidateClaim],
    source: Source,
    gold_dir: Path,
) -> tuple[Path, Path]:
    """Validate the drafted gold against `source`, then write both sidecars under `gold_dir`.

    Returns the `(derived_path, literal_path)` written. Raises before writing anything if a
    derived or literal evidence quote is not a unique substring of `source.text`
    (`EvidenceNotFoundError` / `AmbiguousEvidenceError`), or the bundle is malformed
    (`DerivedValidationError` from `check_gold`, run inside `DerivedGoldFile.from_gold`).

    The all-or-nothing guarantee covers *validation* failure only: every check runs before
    either write. The two writes are sequential, so an OS-level fault on the second (disk
    full, permission) can orphan the first file -- true two-file IO atomicity is out of scope
    here (a bad `.jsonl` re-anchors and fails loudly on load, not silently)."""
    derived_text, literal_text = _validate_and_render(gold, literal_claims, source)

    gold_dir.mkdir(parents=True, exist_ok=True)
    derived_path = gold_dir / f"{source.id}.derived.json"
    literal_path = gold_dir / f"{source.id}.jsonl"
    derived_path.write_text(derived_text)
    literal_path.write_text(literal_text)
    return derived_path, literal_path


def _validate_and_render(
    gold: DerivedGold, literal_claims: Sequence[CandidateClaim], source: Source
) -> tuple[str, str]:
    """Run every check (source ownership, each derived + literal span, the bundle) and build
    both file payloads -- raising before anything is produced if the draft is invalid. Shared
    by `write_gold` and the `--dry-run` path so a rehearsal validates on the exact same path
    the real write does."""
    if gold.source_id != source.id:
        raise DerivedValidationError(
            f"gold source {gold.source_id!r} does not match source {source.id!r}"
        )
    for entry in _derived_entries(gold):
        validate_span(source, entry.evidence)
    anchored = [(anchor_claim(source, c), c.evidence) for c in literal_claims]

    derived_text = DerivedGoldFile.from_gold(gold).model_dump_json(indent=2) + "\n"
    literal_text = "".join(_literal_line(claim, evidence) + "\n" for claim, evidence in anchored)
    return derived_text, literal_text


class DraftError(ValueError):
    """A drafts file is missing, unparseable, or not a valid draft envelope. Raised loudly so
    a bad path never degrades into an empty draft that looks like 'the author accepted
    nothing'."""


class Decision(StrEnum):
    ACCEPT = "accept"
    SKIP = "skip"


class DraftFile(BaseModel):
    """On-disk draft envelope: the two halves `write_gold` consumes. The `derived` half is a
    full `DerivedGoldFile` (validated at load -- a malformed draft fails here, not silently);
    `literal` is the candidate-claim records `parse_candidate` reads. Stored UNAUTHORED; the
    AUTHORED flip happens only for the accepted subset in `adjudicate`."""

    derived: DerivedGoldFile
    # Raw records straight to `parse_candidate` (which takes `object` and validates each
    # field); not typed further here because this is the one parse-boundary transient.
    literal: list[object]


@dataclass(frozen=True)
class AdjudicationResult:
    """The outcome of walking the draft with the author's decisions. `nothing_accepted` keeps
    'author accepted nothing' distinct from 'authored an empty gold': the caller writes
    nothing and the layer stays UNAUTHORED rather than fabricating an AUTHORED-empty sidecar."""

    gold: DerivedGold
    literal_claims: tuple[CandidateClaim, ...]
    accepted_ids: tuple[str, ...]
    nothing_accepted: bool


def _ordered_entries(gold: DerivedGold) -> list[DerivedEntry]:
    """Shared entries first, then each variant's in declared order -- the stable order the
    decisions index against, so a decision binds to the same entry every run."""
    return _derived_entries(gold)


def load_draft(source_id: str, drafts_dir: Path = DRAFTS_DIR) -> tuple[DerivedGold, list[CandidateClaim]]:
    path = drafts_dir / f"{source_id}.draft.json"
    if not path.exists():
        raise DraftError(f"no draft file for source {source_id!r} at {path}")
    try:
        draft = DraftFile.model_validate_json(path.read_text())
    except ValueError as e:
        raise DraftError(f"draft file for {source_id!r} is not a valid draft") from e
    literal = [parse_candidate(record) for record in draft.literal]
    return draft.derived.to_gold(), literal


def _status(has_entries: bool) -> AuthoringStatus:
    return AuthoringStatus.AUTHORED if has_entries else AuthoringStatus.UNAUTHORED


def adjudicate(
    gold: DerivedGold,
    literal_claims: Sequence[CandidateClaim],
    derived_decisions: dict[str, Decision],
    literal_decisions: Sequence[Decision],
) -> AdjudicationResult:
    """Apply per-entry accept/skip decisions, returning the accepted gold and literal claims.
    Pure -- no I/O, and no validation of its own: the accepted subset is validated by the
    caller through `write_gold`/`_validate_and_render` (which run `check_gold`), so a skip that
    strands a `describes` link or a variant bundle is rejected there, not here. Decisions
    default to SKIP for any id not named. Each layer's status is flipped to AUTHORED only if
    that layer actually gained entries -- so accepting derived-only leaves the empty literal
    layer UNAUTHORED (and vice versa), the independent-layer distinction the runner relies on."""
    accepted_shared = tuple(
        e for e in gold.shared if derived_decisions.get(e.annotation_id) is Decision.ACCEPT
    )
    accepted_variants = tuple(
        Variant(
            variant_id=v.variant_id,
            entries=tuple(
                e for e in v.entries if derived_decisions.get(e.annotation_id) is Decision.ACCEPT
            ),
        )
        for v in gold.variants
    )
    accepted_variants = tuple(v for v in accepted_variants if v.entries)
    accepted_literal = tuple(
        c
        for c, d in zip(literal_claims, literal_decisions, strict=False)
        if d is Decision.ACCEPT
    )
    accepted_ids = tuple(e.annotation_id for e in accepted_shared) + tuple(
        e.annotation_id for v in accepted_variants for e in v.entries
    )

    nothing = not accepted_ids and not accepted_literal
    accepted = DerivedGold(
        source_id=gold.source_id,
        literal_status=_status(bool(accepted_literal)),
        derived_status=_status(bool(accepted_ids)),
        shared=accepted_shared,
        variants=accepted_variants,
        exhaustive=gold.exhaustive,
    )
    return AdjudicationResult(
        gold=accepted,
        literal_claims=accepted_literal,
        accepted_ids=accepted_ids,
        nothing_accepted=nothing,
    )


def _sig_text(sig: PropositionSig | None) -> str:
    if sig is None:
        return "?"
    neg = "NOT " if sig.polarity.value == "negated" else ""
    obj = f" {sig.object}" if sig.object is not None else ""
    return f"{sig.subject} {neg}{sig.predicate.value}{obj} ({sig.mode.value})"


def _reading(entry: DerivedEntry, by_id: dict[str, DerivedEntry]) -> str:
    """The entry's actual interpretive content, so the author adjudicates what the entry
    *means*, not just its kind + quote. Each kind surfaces its own meaningful fields; a
    DESCRIPTION names the reading of the entry it describes, not that entry's raw id."""
    match entry.kind:
        case DerivedKind.OCCURRENCE:
            return f"{entry.base_concept!r} qualified as {entry.scope!r}"
        case DerivedKind.DESCRIPTION:
            target = by_id.get(entry.describes or "")
            of = f"[{target.kind}] {_reading(target, by_id)}" if target else entry.describes
            return f"{entry.description_text!r} describes {of}"
        case DerivedKind.REQUIREMENT:
            return f"reframed as requirement: {_sig_text(entry.reframed_proposition)}"
        case DerivedKind.RESOLVED_REFERENCE:
            if entry.referent is None:
                return f"{entry.mention!r} -> left unresolved"
            return f"{entry.mention!r} -> {entry.referent!r}"
        case DerivedKind.CONDITION:
            return f"condition {entry.condition_text!r} on {_sig_text(entry.attaches_to)}"


def _render_entry(entry: DerivedEntry, source: Source, by_id: dict[str, DerivedEntry]) -> str:
    try:
        start, end = validate_span(source, entry.evidence)
        span = f"anchored [{start}:{end}] -> {source.text[start:end]!r}"
    except EvidenceError as e:
        span = f"SPAN ERROR: {e}"
    return (
        f"[{entry.kind}] {_reading(entry, by_id)}  ({entry.support})\n"
        f"    evidence {entry.evidence!r}\n    {span}"
    )


def _render_candidate(candidate: CandidateClaim) -> str:
    """A literal claim shown with the qualifiers the author is approving -- polarity and mode
    are part of the claim's identity (a dropped 'not' or a conditional read as an assertion is
    a different claim), so they must be visible, not hidden behind the verb phrase alone."""
    neg = "NOT " if candidate.polarity.value == "negated" else ""
    obj = candidate.object if candidate.object is not None else "(no object)"
    return (
        f"[literal] {candidate.subject} | {neg}{candidate.predicate.value} | {obj}  "
        f"({candidate.polarity.value}/{candidate.mode.value}/{candidate.attribution.value})\n"
        f"    says {candidate.verb_phrase!r}\n"
        f"    evidence {candidate.evidence!r}"
    )


def _run_interactive(
    source: Source,
    gold: DerivedGold,
    literal_claims: Sequence[CandidateClaim],
    read: Callable[[str], str],
    write: Callable[[str], object],
) -> AdjudicationResult:
    extracted = [c for c in list_claims() if c.source_id == source.id]
    write(f"Source {source.id}: {source.text}\n")
    write(f"({len(extracted)} extracted literal claims available as reference)\n")

    entries = _ordered_entries(gold)
    by_id = {e.annotation_id: e for e in entries}
    derived_decisions: dict[str, Decision] = {}
    literal_decisions: list[Decision] = []
    quit_early = False
    for entry in entries:
        write(_render_entry(entry, source, by_id))
        key = read("accept / skip / quit [a/s/q]? ").strip().lower()
        if key == "q":
            quit_early = True
            break
        derived_decisions[entry.annotation_id] = (
            Decision.ACCEPT if key == "a" else Decision.SKIP
        )

    if not quit_early:
        for candidate in literal_claims:
            write(_render_candidate(candidate))
            key = read("accept / skip / quit [a/s/q]? ").strip().lower()
            if key == "q":
                break
            literal_decisions.append(Decision.ACCEPT if key == "a" else Decision.SKIP)

    return adjudicate(gold, literal_claims, derived_decisions, literal_decisions)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Interactively author fidelity gold for one passage.")
    parser.add_argument("--source", required=True, help="source id, e.g. t3-1-5")
    parser.add_argument("--dry-run", action="store_true", help="adjudicate + validate, write nothing")
    args = parser.parse_args(argv)

    sources = {s.id: s for s in list_acim_sources()}
    source = sources.get(args.source)
    if source is None:
        raise DraftError(f"unknown source {args.source!r}")

    gold, literal_claims = load_draft(args.source)
    result = _run_interactive(source, gold, literal_claims, input, print)

    if result.nothing_accepted:
        print("Nothing accepted; leaving the layer unauthored, writing nothing.")
        return

    if args.dry_run:
        _validate_and_render(result.gold, result.literal_claims, source)
        print(
            f"[dry-run] {len(result.accepted_ids)} derived + "
            f"{len(result.literal_claims)} literal accepted; validated, nothing written."
        )
        return

    derived_path, literal_path = write_gold(result.gold, result.literal_claims, source, GOLD_DIR)
    print(f"Wrote {derived_path} and {literal_path}")


if __name__ == "__main__":
    main()
