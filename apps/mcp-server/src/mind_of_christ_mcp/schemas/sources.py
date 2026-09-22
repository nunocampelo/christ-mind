from pydantic import BaseModel


class SourceResult(BaseModel):
    id: str
    reference: str
    text: str
    concepts: list[str]
