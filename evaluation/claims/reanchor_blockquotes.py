"""One-off: re-anchor claims after the blockquote-merge parser change.

`sources_acim.py` now folds each `>` blockquote into the paragraph that introduces it. That
merge changes some paragraphs' text (shifting `evidence_start`/`evidence_end`) and renumbers
every paragraph after a merged blockquote within its file. The corpus stores absolute
`source_id` + offsets and the runtime trusts them, so this rewrites the affected `claim`
lines deterministically -- re-anchoring each claim's *existing* evidence quote against the
re-parsed source via `anchor_claim` (no LLM). Non-claim lines (failed/rejected) and the
Bible corpus are untouched; the header's `passages_sha256` is refreshed with a note.

The old->new `source_id` map is derived from the parser itself (simulate the pre-merge
per-block numbering against the post-merge numbering), so it stays correct if the corpus
grows more chapters. Affected sections observed: t1-0, t1-1, t2-0, t4-1, t4-3, t4-8.

Run from the repo root:  .venv/bin/python -m evaluation.claims.reanchor_blockquotes
"""

import json
import re
from pathlib import Path

from application.extraction.extract_claims import anchor_claim, parse_candidate
from domain.claims.serialization import ClaimLine
from domain.sources.models import Source
from evaluation.claims.run import _hash_passages
from infrastructure.database.sources_acim import (
    _is_blockquote,
    _parse_frontmatter,
    _parse_ref,
    list_acim_sources,
)
from infrastructure.database.sources_bible import list_bible_sources

_CORPUS = Path("src/infrastructure/database/data/claims/corpus.jsonl")
_ACIM_DIR = Path("src/infrastructure/database/data/acim")


def _source_id_remap() -> dict[str, str]:
    """old source_id -> post-merge source_id, derived by numbering each file's blocks the
    old way (one per block) and the new way (a blockquote shares its intro's number)."""
    remap: dict[str, str] = {}
    for path in sorted(_ACIM_DIR.rglob("*.md")):
        metadata, body = _parse_frontmatter(path.read_text())
        chapter, section = _parse_ref(metadata["ref"])
        blocks = [b for b in re.split(r"\n\s*\n", body) if b.strip()]
        new_number = 0
        for old_index, block in enumerate(blocks, start=1):
            if _is_blockquote(block) and new_number > 0:
                pass  # absorbed into the preceding paragraph; keep new_number
            else:
                new_number += 1
            remap[f"t{chapter}-{section}-{old_index}"] = (
                f"t{chapter}-{section}-{new_number}"
            )
    return remap


def main() -> None:
    remap = _source_id_remap()
    sources: dict[str, Source] = {
        s.id: s for s in (*list_bible_sources(), *list_acim_sources())
    }
    out: list[str] = []
    reanchored = 0

    for line in _CORPUS.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)

        if record.get("type") == "header":
            record["passages_sha256"] = _hash_passages(
                [*list_bible_sources(), *list_acim_sources()]
            )
            record["note"] = "claims re-anchored after blockquote merge; not re-extracted"
            out.append(json.dumps(record, ensure_ascii=False))
            continue

        if record.get("type") != "claim":
            out.append(line)
            continue

        old_id = record["source_id"]
        new_id = remap.get(old_id, old_id)
        if new_id not in sources:
            out.append(line)
            continue

        record["source_id"] = new_id
        candidate = parse_candidate(record)
        claim = anchor_claim(sources[new_id], candidate)
        # Match the original writer's style (json.dumps over model_dump, unicode preserved)
        # rather than model_dump_json's compact separators, so only content -- not
        # formatting -- diffs against the untouched lines.
        rewritten = ClaimLine.from_claim(claim, candidate.evidence).model_dump()
        out.append(json.dumps(rewritten, ensure_ascii=False))
        reanchored += 1

    _CORPUS.write_text("\n".join(out) + "\n")
    print(f"re-anchored {reanchored} claim(s); rewrote {_CORPUS}")


if __name__ == "__main__":
    main()
