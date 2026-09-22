"""File-backed ACIM source repository.

Parses the markdown chapter files bundled under `data/acim/` (copied from the
cmi-acim `_text/` corpus, currently chapters 1-4) into `Source` objects at
import time. Each file is one chapter section: a `---`-delimited frontmatter
block (`ref: T<chapter>.<section>`) followed by paragraphs separated by
blank lines, one `Source` per paragraph. When a real datastore arrives, this
becomes the seed data for it rather than something parsed at import time.
"""

import re
from pathlib import Path

from domain.sources.models import Source

_DATA_DIR = Path(__file__).parent / "data" / "acim"
_REF_PATTERN = re.compile(r"^T(\d+)\.(\d+)$")


def _parse_frontmatter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        raise ValueError("chapter file has no --- frontmatter block")
    _, frontmatter_block, body = raw.split("---", 2)
    metadata = {}
    for line in frontmatter_block.strip().splitlines():
        key, _, value = line.partition(":")
        metadata[key.strip()] = value.strip()
    return metadata, body


def _clean_paragraph(raw: str) -> str:
    lines = [line.strip().lstrip(">").strip() for line in raw.splitlines()]
    text = " ".join(line for line in lines if line)
    text = text.replace("<br/>", " ")
    text = re.sub(r"\*{1,3}", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_ref(ref: str) -> tuple[int, int]:
    match = _REF_PATTERN.match(ref)
    if not match:
        raise ValueError("unrecognized ref format: expected 'T<chapter>.<section>'")
    chapter, section = match.groups()
    return int(chapter), int(section)


def _parse_chapter_file(path: Path) -> tuple[Source, ...]:
    metadata, body = _parse_frontmatter(path.read_text())
    chapter, section = _parse_ref(metadata["ref"])
    paragraphs = [block for block in re.split(r"\n\s*\n", body) if block.strip()]

    sources = []
    for number, paragraph in enumerate(paragraphs, start=1):
        text = _clean_paragraph(paragraph)
        if not text:
            continue
        sources.append(
            Source(
                id=f"t{chapter}-{section}-{number}",
                book="ACIM",
                chapter=chapter,
                section=section,
                paragraph=number,
                text=text,
            )
        )
    return tuple(sources)


def _load_acim_sources() -> tuple[Source, ...]:
    sources: list[Source] = []
    for path in sorted(_DATA_DIR.rglob("*.md")):
        sources.extend(_parse_chapter_file(path))
    return tuple(sources)


_SOURCES: tuple[Source, ...] = _load_acim_sources()


def list_acim_sources() -> tuple[Source, ...]:
    return _SOURCES
