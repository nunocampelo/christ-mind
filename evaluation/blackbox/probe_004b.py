"""One-off diagnostic: bring up the live stack, ask only the mind-of-god-004b question,
and dump the full AgentAnswer (prose + cited claims + inferred chains + diagnostics) so we
can see what it surfaced instead of the gold-acceptable claims. Not part of the suite."""

import os

from infrastructure.config.env import load_env

from evaluation.blackbox.client import A2AAgentClient
from evaluation.blackbox.harness import live_stack

load_env()

QUESTION = "How does God think? What is the Mind of God?"
ACCEPTABLE = {
    "efdccd0ac72007aa",
    "eb3114c3c10e65c7",
    "f99fd11eb731987c",
    "53c77a24b278b916",
    "ab816dad26ee5551",
}


def main() -> None:
    agent_url = os.environ.get("AGENT_URL", "http://127.0.0.1:8766")
    with live_stack(agent_url=agent_url) as url:
        client = A2AAgentClient(url)
        response = client.ask(QUESTION)

    print("=== ANSWER ===")
    print(response.answer)
    print("\n=== CITED CLAIMS ===")
    cited_ids = set()
    for c in response.cited_claims:
        cid = getattr(c, "claim_id", None) or getattr(c, "id", None)
        cited_ids.add(cid)
        print(f"- {cid}: {getattr(c, 'text', c)!r}")
    print("\n=== INFERRED CHAINS ===")
    for ch in response.inferred_chains:
        print(f"- {ch}")
    print("\n=== CITATION DIAGNOSTICS ===")
    print(response.citation_diagnostics)
    print("\n=== OVERLAP WITH GOLD-ACCEPTABLE ===")
    print(f"acceptable:  {sorted(ACCEPTABLE)}")
    print(f"cited:       {sorted(x for x in cited_ids if x)}")
    print(f"intersection: {sorted(ACCEPTABLE & cited_ids)}")


if __name__ == "__main__":
    main()
