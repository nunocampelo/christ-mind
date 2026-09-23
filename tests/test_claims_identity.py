from pydantic import BaseModel

from domain.claims.identity import claim_signature, compute_claim_id
from domain.claims.models import Attribution, Mode, Polarity, Predicate


class Signature(BaseModel):
    model_config = {"frozen": True}

    source_id: str
    evidence: str
    subject: str
    predicate: Predicate
    object: str | None
    polarity: Polarity
    mode: Mode
    attribution: Attribution


SIGNATURE = Signature(
    source_id="t1-1-20",
    evidence="the Spirit, not the body, is the altar of truth",
    subject="Spirit",
    predicate=Predicate.IS,
    object="altar of truth",
    polarity=Polarity.AFFIRMED,
    mode=Mode.ASSERTION,
    attribution=Attribution.COURSE,
)


def test_same_signature_gives_same_id():
    assert compute_claim_id(**SIGNATURE.model_dump()) == compute_claim_id(**SIGNATURE.model_dump())


def test_id_is_sixteen_hex_chars():
    claim_id = compute_claim_id(**SIGNATURE.model_dump())

    assert len(claim_id) == 16
    assert all(c in "0123456789abcdef" for c in claim_id)


def test_each_signature_field_changes_the_id():
    base = compute_claim_id(**SIGNATURE.model_dump())
    variations = [
        SIGNATURE.model_copy(update={"subject": "body"}),
        SIGNATURE.model_copy(update={"predicate": Predicate.CAUSES}),
        SIGNATURE.model_copy(update={"object": "altar"}),
        SIGNATURE.model_copy(update={"polarity": Polarity.NEGATED}),
        SIGNATURE.model_copy(update={"mode": Mode.NORMATIVE}),
        SIGNATURE.model_copy(update={"attribution": Attribution.EGO}),
        SIGNATURE.model_copy(update={"source_id": "t1-1-21"}),
        SIGNATURE.model_copy(update={"evidence": "the Spirit is the altar of truth"}),
    ]
    ids = {base}
    for sig in variations:
        ids.add(compute_claim_id(**sig.model_dump()))

    assert len(ids) == len(variations) + 1


def test_polarity_alone_distinguishes_claims_sharing_a_quote():
    """The Spirit/body pair: same predicate and object, one affirmed and one
    negated, from the same quote. They must not collide.
    """
    spirit = compute_claim_id(**SIGNATURE.model_dump())
    body = compute_claim_id(
        **SIGNATURE.model_copy(
            update={"subject": "body", "polarity": Polarity.NEGATED}
        ).model_dump()
    )
    body_same_polarity = compute_claim_id(
        **SIGNATURE.model_copy(update={"subject": "body"}).model_dump()
    )

    assert spirit != body
    assert body != body_same_polarity


def test_null_object_differs_from_empty_string_object():
    with_null = compute_claim_id(**SIGNATURE.model_copy(update={"object": None}).model_dump())
    with_empty = compute_claim_id(**SIGNATURE.model_copy(update={"object": ""}).model_dump())

    assert with_null != with_empty


def test_field_boundaries_are_unambiguous():
    left = compute_claim_id(
        **SIGNATURE.model_copy(update={"subject": "a", "object": "bc"}).model_dump()
    )
    right = compute_claim_id(
        **SIGNATURE.model_copy(update={"subject": "ab", "object": "c"}).model_dump()
    )

    assert left != right


def test_signature_joins_fields_with_nul_and_marks_null_object():
    signature = claim_signature(**SIGNATURE.model_dump())

    assert signature.split("\x00") == [
        "t1-1-20",
        "the Spirit, not the body, is the altar of truth",
        "Spirit",
        "is",
        "altar of truth",
        "affirmed",
        "assertion",
        "course",
    ]

    assert "\x00NULL\x00" in claim_signature(**SIGNATURE.model_copy(update={"object": None}).model_dump())
