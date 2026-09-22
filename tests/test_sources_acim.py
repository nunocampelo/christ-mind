from infrastructure.database.sources_acim import list_acim_sources


def test_list_acim_sources_parses_known_paragraph():
    sources = list_acim_sources()

    intro = next(source for source in sources if source.id == "t1-0-1")
    assert intro.book == "ACIM"
    assert intro.chapter == 1
    assert intro.section == 0
    assert intro.paragraph == 1
    assert intro.text.startswith("This is a course in miracles.")


def test_list_acim_sources_covers_chapters_one_through_four():
    sources = list_acim_sources()

    assert {source.chapter for source in sources} == {1, 2, 3, 4}


def test_list_acim_sources_ids_are_unique():
    sources = list_acim_sources()

    ids = [source.id for source in sources]
    assert len(ids) == len(set(ids))
