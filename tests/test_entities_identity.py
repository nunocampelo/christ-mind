from domain.entities.identity import compute_entity_id, entity_signature
from domain.entities.models import Entity
from evaluation.entities.run_format import EntityLine


def test_id_is_independent_of_member_order():
    assert compute_entity_id(["the ego", "ego", "his ego"]) == compute_entity_id(
        ["his ego", "the ego", "ego"]
    )


def test_id_is_sixteen_hex_chars():
    entity_id = compute_entity_id(["ego", "the ego"])

    assert len(entity_id) == 16
    assert all(c in "0123456789abcdef" for c in entity_id)


def test_distinct_member_sets_give_distinct_ids():
    assert compute_entity_id(["ego", "the ego"]) != compute_entity_id(
        ["ego", "the ego", "fear"]
    )


def test_member_boundaries_are_unambiguous():
    assert compute_entity_id(["ab", "c"]) != compute_entity_id(["a", "bc"])


def test_signature_sorts_and_joins_with_nul():
    assert entity_signature(["the ego", "ego"]).split("\x00") == ["ego", "the ego"]


def test_entity_line_round_trip_recomputes_id():
    entity = Entity(
        entity_id=compute_entity_id(["ego", "the ego"]),
        mentions=frozenset({"ego", "the ego"}),
    )

    restored = EntityLine.from_entity(entity).to_entity()

    assert restored == entity


def test_entity_line_ignores_a_wrong_written_id():
    line = EntityLine(entity_id="0000000000000000", mentions=["ego", "the ego"])

    restored = line.to_entity()

    assert restored.entity_id == compute_entity_id(["ego", "the ego"])
