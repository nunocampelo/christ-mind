"""Static probe: can the lexical retrieval layer, as currently configured, reach a
required claim from the question's own vocabulary at all?

A property of gold + corpus + retrieval config, not of a run. Two failure classes
depend on it: `A` means the lexical channel can retrieve the required claim from
plausible tokens of the question -- so a miss is a mapper/ranking problem -- while
`B` means no plausible lexical query reaches it -- the miss needs semantic
retrieval. The classifier in `classify.py` combines this with the run's retrieval
trace to decide A vs. B vs. C for each failed required id.

`plausible_query_terms` is deliberately narrow: only the question's own content
tokens and light variants, never surface forms of the required claim itself.
Otherwise reachability is trivially true and the probe stops discriminating.

Bumping `REACHABILITY_VERSION` marks a semantics change so archived run artifacts
carrying an older label are known to have been produced by a different probe.
"""

import re
from collections.abc import Iterable

from application.retrieval.find_claims import find_claims_batch

REACHABILITY_VERSION = 1

# Function words plus a few question/discourse-marker tokens ("say", "than",
# "means") that carry no retrieval signal on their own -- keeping them would
# populate the plausible-term set with bigrams like "the than others" and
# artificially inflate what "plausible" covers.
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "at", "for", "with", "by", "from",
    "and", "or", "but", "not", "no",
    "this", "that", "these", "those",
    "it", "its", "i", "you", "he", "she", "we", "they", "them", "me", "my",
    "your", "his", "her", "our", "their",
    "what", "which", "who", "whom", "when", "where", "why", "how",
    "does", "do", "did", "will", "would", "should", "could", "can", "may",
    "might", "must",
    "about", "as", "if", "so", "yes",
    "some", "any", "all", "each", "every",
    "one", "two",
    "say", "says", "said", "than", "means", "mean",
})

# Words start with a letter and may contain interior hyphens or apostrophes
# ("right-mindedness", "god's") -- but not trailing punctuation.
_WORD_RE = re.compile(r"[a-z](?:[a-z'\-]*[a-z])?")


def _content_tokens(question: str) -> list[str]:
    return [t for t in _WORD_RE.findall(question.lower()) if t not in _STOPWORDS]


def plausible_query_terms(question: str) -> list[str]:
    """Terms a plausible mapper could emit from `question` alone: content unigrams,
    contiguous bigrams, and each with a leading `"the "`. Order-preserving; no
    duplicates. This is the ceiling of what lexical retrieval can be asked to reach
    without peeking at the required claim's surface form."""
    tokens = _content_tokens(question)
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        if term and term not in seen:
            seen.add(term)
            terms.append(term)

    for token in tokens:
        add(token)
    for left, right in zip(tokens, tokens[1:]):
        add(f"{left} {right}")
    for term in list(terms):
        add(f"the {term}")
    return terms


def is_lexically_reachable(claim_id: str, question: str, limit: int = 12) -> bool:
    """True if any plausible query for `question` retrieves `claim_id` in `find_claims`
    top-`limit`. `limit` defaults to the same `global_limit` the agent's seeded batch
    uses, so the probe measures the same ceiling the agent's own retrieval sees.

    Two probes are tried: each plausible term individually (a maximally-generous
    single-query mapper) and the whole set as a round-robin batch (mirroring the
    agent's seeded `find_claims_batch`). If either surfaces the claim, it counts as
    reachable -- the probe answers "can lexical retrieval reach this at all", not
    "does the current mapper reach it".
    """
    terms = plausible_query_terms(question)
    if not terms:
        return False
    for term in terms:
        batch = find_claims_batch([term], limit_per_query=limit, global_limit=limit)
        if any(c.claim_id == claim_id for c in batch):
            return True
    batch = find_claims_batch(terms, limit_per_query=5, global_limit=limit)
    return any(c.claim_id == claim_id for c in batch)


def classify_reachability(
    claim_ids: Iterable[str], question: str, limit: int = 12
) -> dict[str, bool]:
    """Map each id to its lexical-reachability. A convenience wrapper -- the run-time
    classifier is the one caller today."""
    return {cid: is_lexically_reachable(cid, question, limit) for cid in claim_ids}
