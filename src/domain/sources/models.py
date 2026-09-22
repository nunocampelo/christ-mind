from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    id: str
    book: str
    chapter: int
    text: str
    verse: int | None = None
    section: int | None = None
    paragraph: int | None = None
    concepts: tuple[str, ...] = field(default_factory=tuple)
