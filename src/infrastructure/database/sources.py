"""Stub in-memory source repository.

Placeholder for a real database-backed repository. Content is public-domain
KJV text, chosen only to exercise the retrieval path end to end -- not a
vetted or complete corpus. When a real datastore arrives, it should sit
behind the same `list_sources` signature so `application/retrieval` doesn't
need to change shape -- only what backs it.
"""

from domain.sources.models import Source

_SOURCES: tuple[Source, ...] = (
    Source(
        id="matt-5-7",
        reference="Matthew 5:7 (KJV)",
        text="Blessed are the merciful: for they shall obtain mercy.",
        concepts=("mercy", "forgiveness"),
    ),
    Source(
        id="matt-6-14-15",
        reference="Matthew 6:14-15 (KJV)",
        text=(
            "For if ye forgive men their trespasses, your heavenly Father "
            "will also forgive you: But if ye forgive not men their "
            "trespasses, neither will your Father forgive your trespasses."
        ),
        concepts=("forgiveness",),
    ),
    Source(
        id="matt-5-5",
        reference="Matthew 5:5 (KJV)",
        text="Blessed are the meek: for they shall inherit the earth.",
        concepts=("humility",),
    ),
    Source(
        id="phil-2-3",
        reference="Philippians 2:3 (KJV)",
        text=(
            "Let nothing be done through strife or vainglory; but in "
            "lowliness of mind let each esteem other better than themselves."
        ),
        concepts=("humility",),
    ),
    Source(
        id="1cor-13-4-5",
        reference="1 Corinthians 13:4-5 (KJV)",
        text=(
            "Charity suffereth long, and is kind; charity envieth not; "
            "charity vaunteth not itself, is not puffed up, Doth not "
            "behave itself unseemly, seeketh not her own, is not easily "
            "provoked, thinketh no evil."
        ),
        concepts=("love", "patience"),
    ),
    Source(
        id="rom-12-19",
        reference="Romans 12:19 (KJV)",
        text=(
            "Dearly beloved, avenge not yourselves, but rather give place "
            "unto wrath: for it is written, Vengeance is mine; I will "
            "repay, saith the Lord."
        ),
        concepts=("forgiveness", "patience"),
    ),
)


def list_sources() -> tuple[Source, ...]:
    return _SOURCES
