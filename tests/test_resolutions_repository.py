import json
from pathlib import Path

import pytest

import infrastructure.database.resolutions as resolutions_module
from infrastructure.database.resolutions import entity_for_mention, list_entities


def test_list_entities_loads_the_partition():
    entities = list_entities()

    assert len(entities) > 0
    assert all(len(e.entity_id) == 16 for e in entities)


def test_entity_for_mention_resolves_a_merged_form():
    entity = entity_for_mention("the EGO")

    assert entity is not None
    assert "ego" in entity.mentions


def test_entity_for_an_unknown_form_is_none():
    assert entity_for_mention("this form is not in the corpus at all") is None


def test_only_entity_lines_are_loaded(tmp_path: Path, monkeypatch):
    data = tmp_path / "resolution.jsonl"
    data.write_text(
        "\n".join(
            json.dumps(line)
            for line in [
                {"type": "header", "run_id": "SRC", "entities": 1},
                {"type": "entity", "entity_id": "x", "mentions": ["ego", "the ego"]},
            ]
        )
    )
    monkeypatch.setattr(resolutions_module, "_DATA_FILE", data)

    entities = resolutions_module._load_resolution()

    assert len(entities) == 1
    assert entities[0].mentions == frozenset({"ego", "the ego"})


def test_missing_data_file_fails_loudly(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(resolutions_module, "_DATA_FILE", tmp_path / "absent.jsonl")

    with pytest.raises(FileNotFoundError, match="resolution data file is missing"):
        resolutions_module._load_resolution()
