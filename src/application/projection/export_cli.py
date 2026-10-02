"""Thin export command: build the graph projection from the live repositories and write
the committed artifact + print a coverage report (plan 0030, increment B).

    python -m application.projection.export_cli \
        --out apps/web/public/graph/projection.json

Repository access and I/O live here; the projection and artifact modules stay pure so
they are unit-tested without touching disk or the real corpus. Re-running against an
unchanged snapshot rewrites a byte-identical file.
"""

import argparse
import sys
from pathlib import Path

from application.projection.artifact import build_artifact, serialize
from application.projection.build_projection import build_projection
from application.retrieval.evidence import EvidenceResolutionError
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention, list_entities


def _coverage_report(claim_count: int, artifact_counts) -> str:
    c = artifact_counts
    reasons = "\n".join(
        f"      {reason.value}: {count}"
        for reason, count in sorted(c.non_projectable_by_reason.items())
    )
    accounted = c.edges + c.non_projectable
    return (
        f"input claims:        {claim_count}\n"
        f"drawn edges:         {c.edges}\n"
        f"non-projectable:     {c.non_projectable}\n"
        f"{reasons}\n"
        f"accounted (edges+np):{accounted}"
        f"  {'OK' if accounted == claim_count else 'MISMATCH'}\n"
        f"nodes:               {c.nodes} "
        f"({c.catalogued_nodes} catalogued, {c.uncatalogued_nodes} uncatalogued; "
        f"{c.merged_nodes} merged >1 expr)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the graph projection artifact.")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="destination JSON path (e.g. apps/web/public/graph/projection.json)",
    )
    args = parser.parse_args(argv)

    claims = list_claims()
    entities = list_entities()
    projection = build_projection(claims, entity_for_mention)

    try:
        artifact = build_artifact(
            projection,
            claim_count=len(claims),
            resolution_entity_count=len(entities),
            source_count=_source_count(),
        )
    except EvidenceResolutionError as e:
        raise SystemExit(f"export failed: {e}") from e

    accounted = artifact.counts.edges + artifact.counts.non_projectable
    if accounted != len(claims):
        raise SystemExit(
            f"export failed: coverage mismatch, {accounted} accounted vs {len(claims)} input claims"
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(serialize(artifact), encoding="utf-8")

    print(f"wrote {args.out}  (schema {artifact.metadata.schema_version}, "
          f"content {artifact.metadata.content_hash[:12]})")
    print(_coverage_report(len(claims), artifact.counts))
    return 0


def _source_count() -> int:
    from infrastructure.database.sources import list_sources

    return len(list_sources())


if __name__ == "__main__":
    sys.exit(main())
