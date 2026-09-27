"""Detects a bare-subject definitional question ("what is the ego?", "describe salvation")
and returns its subject as a supplemental retrieval term.

Such a question is *about a concept*, and its subject noun is the term that actually surfaces
the concept's definition -- yet the mapper maps it to situational themes and never searches
the subject itself, so the definition is reachable but never queried (the agent then
prematurely abstains). This returns the subject as one extra seed query, a sibling of
`meta_question.meta_query_terms` (which does the same for the Course itself).

Deliberately narrow: fires only on bare "what is X / describe X / define X" framings, never on
how/application, relationship, or content-*about* questions. No corpus check is needed -- a
subject the corpus lacks yields an empty `find_claims` and so contributes nothing to the seed
batch (round-robin is fair per query), and this stays a pure syntactic detector rather than
reaching across into the retrieval layer.
"""

import re

# Bare-subject definitional framings. Anchored start-to-end so a trailing topic or clause
# ("what does the Course say about X", "what is the ego doing to me") does not match as a
# definitional subject. Captures the subject after an optional leading article.
_SUBJECT = r"(?P<subject>.+?)"
_END = r"\s*[.?!]*\s*$"
_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        rf"^\s*what(?:'s| is| are)\s+(?:the\s+|a\s+|an\s+)?{_SUBJECT}{_END}",
        rf"^\s*(?:describe|define)\s+(?:the\s+|a\s+|an\s+)?{_SUBJECT}{_END}",
    )
)

# Framings that look definitional but aren't a bare subject: a "what is X" whose tail is a
# relational/possessive/verb clause rather than a concept name. These break the bare-subject
# reading, so the extracted "subject" would be a phrase, not a term -- reject them.
_NON_SUBJECT_TAIL = re.compile(
    r"\b(about|doing|saying|mean(?:s|ing)?\s+(?:to|for|when)|related|between|"
    r"help(?:ing)?|for\s+me|position\s+on|view\s+on|say\s+about)\b",
    re.IGNORECASE,
)


def concept_query_terms(text: str) -> list[str]:
    """The supplemental seed query for a bare-subject definitional question: `["<subject>"]`
    (e.g. `["ego"]` for "What is the ego?"), or `[]` when the text isn't one."""
    normalized = " ".join(text.split())
    for pattern in _PATTERNS:
        match = pattern.match(normalized)
        if not match:
            continue
        subject = match.group("subject").strip()
        if not subject or _NON_SUBJECT_TAIL.search(subject):
            return []
        return [subject.lower()]
    return []
