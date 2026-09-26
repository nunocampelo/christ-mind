"""The one definition of an inline citation marker, shared by the orchestrator (which
validates markers against the gathered claims) and any eval that inspects answer prose.

A marker is a claim_id in square brackets written immediately after the statement it
supports -- `God is the Giver of life. [t1-1-4]`. The model is told to emit the exact
claim_id it was given; this module only reads them back out. It never edits the prose --
rendering markers as superscripts is the web client's job, and validation is soft (the
orchestrator records violations, it does not reject the answer).
"""

import re

# A claim_id as it appears in the corpus/tool results: id chars only, no whitespace, so a
# bracketed span containing spaces (ordinary prose in brackets) is not mistaken for one.
_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._-]*)\]")


def extract_markers(text: str) -> list[str]:
    """Every bracketed claim_id in `text`, in order of appearance, duplicates kept.

    Order and multiplicity are preserved so a caller can tell how many times a claim was
    cited, not just whether it was; dedupe at the call site when only membership matters.
    """
    return _MARKER.findall(text)
