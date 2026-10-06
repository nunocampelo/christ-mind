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

import json
from collections.abc import Sequence
from pathlib import Path

from application.extraction.extract_claims import CandidateClaim, anchor_claim
from application.extraction.spans import validate_span
from domain.claims.models import Claim
from domain.claims.serialization import ClaimLine
from domain.derivation.models import DerivedEntry, DerivedGold, DerivedValidationError
from domain.derivation.serialization import DerivedGoldFile
from domain.sources.models import Source


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
    if gold.source_id != source.id:
        raise DerivedValidationError(
            f"gold source {gold.source_id!r} does not match source {source.id!r}"
        )

    for entry in _derived_entries(gold):
        validate_span(source, entry.evidence)
    anchored = [(anchor_claim(source, c), c.evidence) for c in literal_claims]

    gold_file = DerivedGoldFile.from_gold(gold)
    derived_text = gold_file.model_dump_json(indent=2) + "\n"
    literal_text = "".join(_literal_line(claim, evidence) + "\n" for claim, evidence in anchored)

    gold_dir.mkdir(parents=True, exist_ok=True)
    derived_path = gold_dir / f"{source.id}.derived.json"
    literal_path = gold_dir / f"{source.id}.jsonl"
    derived_path.write_text(derived_text)
    literal_path.write_text(literal_text)
    return derived_path, literal_path
