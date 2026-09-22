from pydantic import BaseModel


class SourceResult(BaseModel):
    id: str
    book: str
    chapter: int
    text: str
    verse: int | None
    section: int | None
    paragraph: int | None
    concepts: list[str]
