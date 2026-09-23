import pytest

from application.extraction.extract_claims import CandidateClaim, ExtractionFailedError
from application.extraction.prompt import (
    SYSTEM_PROMPT,
    PromptedClaimExtractor,
    parse_response,
)
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.sources.models import Source

SOURCE = Source(id="t1-1-6", book="ACIM", chapter=1, text="6. Miracles are natural.")

CLAIM_JSON = (
    '{"subject": "miracles", "verb_phrase": "are", "object": "natural", '
    '"predicate": "is", "polarity": "affirmed", "mode": "assertion", '
    '"attribution": "course", "evidence": "Miracles are natural."}'
)
NATURAL = CandidateClaim(
    subject="miracles",
    verb_phrase="are",
    object="natural",
    predicate=Predicate.IS,
    polarity=Polarity.AFFIRMED,
    mode=Mode.ASSERTION,
    attribution=Attribution.COURSE,
    evidence="Miracles are natural.",
)


@pytest.mark.parametrize(
    "enum", [Predicate, Polarity, Mode, Attribution], ids=lambda e: e.__name__
)
def test_system_prompt_offers_every_allowed_value(
    enum: type[Predicate | Polarity | Mode | Attribution],
):
    assert all(f'"{member.value}"' in SYSTEM_PROMPT for member in enum)


@pytest.mark.parametrize(
    "response",
    [
        f'{{"claims": [{CLAIM_JSON}]}}',
        f'```json\n{{"claims": [{CLAIM_JSON}]}}\n```',
        f'```\n{{"claims": [{CLAIM_JSON}]}}\n```',
        # The model sometimes repeats the "claims": [ header inside the array;
        # the claim objects are well-formed, so the duplicated header is repaired.
        f'{{"claims": [\n  "claims": [\n    {CLAIM_JSON}\n]}}',
        f'```json\n{{"claims": [\n  "claims": [\n    {CLAIM_JSON}\n]}}\n```',
    ],
    ids=["bare", "json-fence", "plain-fence", "dup-header", "dup-header-fenced"],
)
def test_parse_response_reads_claims(response: str):
    assert parse_response(response) == [NATURAL]


def test_parse_response_accepts_no_claims():
    assert parse_response('{"claims": []}') == []


@pytest.mark.parametrize(
    "response",
    [
        "Here are the claims: none",
        f"[{CLAIM_JSON}]",
        '{"claims": "none"}',
        '{"claims": [{"subject": "miracles"}]}',
        '{"claims": [' + CLAIM_JSON.replace('"is"', '"is_not"') + "]}",
        '{"claims": [' + CLAIM_JSON.replace('"natural",', "3,", 1) + "]}",
    ],
    ids=[
        "not-json",
        "bare-list",
        "claims-not-list",
        "missing-fields",
        "unknown-predicate",
        "object-not-string",
    ],
)
def test_parse_response_fails_the_source_on_unusable_replies(response: str):
    with pytest.raises(ExtractionFailedError):
        parse_response(response)


def test_prompted_extractor_sends_system_prompt_and_passage():
    calls: list[tuple[str, str]] = []

    def complete(system: str, user: str) -> str:
        calls.append((system, user))
        return f'{{"claims": [{CLAIM_JSON}]}}'

    candidates = PromptedClaimExtractor(complete).extract(SOURCE)

    assert candidates == [NATURAL]
    [(system, user)] = calls
    assert system == SYSTEM_PROMPT
    assert "t1-1-6" in user
    assert SOURCE.text in user
