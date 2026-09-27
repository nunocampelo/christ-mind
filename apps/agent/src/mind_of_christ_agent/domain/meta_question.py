"""Detects a question whose subject is *the Course itself* -- where the Course is the object
of inquiry ("what is the Course about?"), not a source of guidance for some other question
("what does the Course say about forgiveness?", "how can the Course help me with fear?").

Such a question maps to the Course's *contents* (love, forgiveness, Atonement...) but never
to the corpus itself, so the thesis passage (t1-0-1, which ranks first for the query
"course") is never searched. `meta_query_terms` returns the one supplemental query that
closes that gap -- always the canonical retrieval term "course", never the referent's own
words ("teaching" does not surface t1-0-1). It returns [] for everything else, deliberately
narrow: a false positive would inject Course-meta claims into a content or outside-corpus
answer that should not have them.
"""

import re

# The canonical retrieval term. Every recognized corpus-referent maps to this, because it is
# the term that actually surfaces the thesis passage -- detection and the effective query are
# separate concerns.
_COURSE_TERM = "course"

# The corpus naming itself: "the Course", "this course/teaching", "A Course in Miracles".
_REFERENT = r"(?:the course|this course|this teaching|a course in miracles|acim)"

# Meta = the referent is the SUBJECT of an is/about/purpose/teach question. Patterns anchor
# at end-of-string (allowing a trailing "?") so a content question that appends a separate
# topic -- "what does the Course teach ABOUT the mind", "what does the Course say about
# forgiveness", "the Course's position ON forgiveness" -- cannot match: the trailing topic
# breaks the end anchor.
_END = r"\s*[.?!]*$"
_META_PATTERNS = tuple(
    re.compile(p)
    for p in (
        rf"\bwhat(?:'s| is)\s+{_REFERENT}(?:\s+all)?\s+about{_END}",  # ...(all) about?
        rf"\bwhat(?:'s| is)\s+{_REFERENT}{_END}",                     # what is the Course?
        rf"\bwhat\s+is\s+the\s+(?:purpose|aim|point)\s+of\s+{_REFERENT}{_END}",
        rf"\bwhat\s+does\s+{_REFERENT}\s+teach{_END}",                # teach? (no topic after)
        rf"\bwhat\s+(?:is|are)\s+{_REFERENT}(?:'s)?\s+(?:purpose|aim|message){_END}",
        rf"\btell\s+me\s+about\s+{_REFERENT}{_END}",
    )
)

# Even if a framing pattern matched, these mark a question that is really about material
# outside the corpus (history/authorship/workbook), which must decline, not get a course
# search.
_OUTSIDE_MARKERS = re.compile(
    r"\b(transcrib|author|wrote|written|year|workbook|lesson|history|published|publish)\w*"
)


def is_meta_question(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if _OUTSIDE_MARKERS.search(normalized):
        return False
    return any(pattern.search(normalized) for pattern in _META_PATTERNS)


def meta_query_terms(text: str) -> list[str]:
    """The supplemental seed query for a question about the Course itself: ["course"] when
    the Course is the object of inquiry, [] otherwise."""
    return [_COURSE_TERM] if is_meta_question(text) else []
