"""File-backed claim repository.

Reads the committed corpus claim run bundled under `data/claims/` (promoted from the
evaluation harness's full-corpus extraction run) into `Claim` objects. Each `claim`
line is validated into a `ClaimLine` and reconstructed with `to_claim`, so the app
reads persisted claims without depending on `evaluation/`. Rejected and failed lines in
the run are skipped -- only anchored claims are served. When a real datastore arrives,
this becomes its seed rather than something parsed at import time, behind the same
`list_claims()` signature so `application/` and `domain/` don't change shape.
"""

import json
from pathlib import Path

from domain.claims.models import Claim
from domain.claims.serialization import ClaimLine

_DATA_FILE = Path(__file__).parent / "data" / "claims" / "corpus.jsonl"


def _load_claims() -> tuple[Claim, ...]:
    if not _DATA_FILE.exists():
        raise FileNotFoundError(f"claim data file is missing: {_DATA_FILE}")
    claims = []
    for line in _DATA_FILE.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("type") != "claim":
            continue
        claims.append(ClaimLine.model_validate(record).to_claim())
    return tuple(claims)


_CLAIMS: tuple[Claim, ...] = _load_claims()


def list_claims() -> tuple[Claim, ...]:
    return _CLAIMS
