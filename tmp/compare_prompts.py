"""Runs the AI Core extractor N times against the current working-tree prompt,
scores each against the dev gold set in memory, and prints the true-positive
distribution. Does not write to evaluation/runs/. Invoked once per prompt
version by the caller (which swaps prompt.py between runs).
"""

import statistics
import sys

from application.extraction.extract_claims import extract_claims
from application.extraction.prompt import PROMPT_VERSION
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.run import GOLD_FILES, Split
from evaluation.claims.score import score_claims
from infrastructure.database.sources_acim import list_acim_sources
from infrastructure.llm.anthropic_proxy import make_extractor

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5

sources = list_acim_sources()
gold = [c for p in GOLD_FILES[Split.DEV] for c in load_gold_claims(p, sources)]
gold_ids = {c.source_id for c in gold}
targets = [s for s in sources if s.id in gold_ids]

tps = []
for i in range(N):
    extractor = make_extractor()
    result = extract_claims(targets, extractor)
    report = score_claims(result.claims, gold)
    tp = report.loose.true_positives
    tps.append(tp)
    print(
        f"  run {i + 1}: loose tp {tp}  "
        f"P {report.loose.precision:.3f} R {report.loose.recall:.3f}  "
        f"rej {len(result.rejected)} fail {len(result.failed_source_ids)}",
        flush=True,
    )

mean = statistics.mean(tps)
stdev = statistics.stdev(tps) if len(tps) > 1 else 0.0
print(
    f"PROMPT v{PROMPT_VERSION}: gold={len(gold)}  "
    f"tp mean {mean:.1f}  stdev {stdev:.2f}  min {min(tps)}  max {max(tps)}"
)
