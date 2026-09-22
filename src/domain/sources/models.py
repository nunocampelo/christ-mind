from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    id: str
    reference: str
    text: str
    concepts: tuple[str, ...] = field(default_factory=tuple)
