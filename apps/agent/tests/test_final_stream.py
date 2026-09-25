"""Unit tests for the streaming `final`-value extractor: it must reveal exactly the inner
answer text (unescaped), emit nothing for a `tool_call`, and survive fragments split at
any boundary -- since the decision stream arrives in arbitrary chunks.
"""

from mind_of_christ_agent.domain.final_stream import FinalValueExtractor


def _feed_all(*fragments: str) -> str:
    extractor = FinalValueExtractor()
    return "".join(extractor.feed(f) for f in fragments)


def test_extracts_a_whole_final_value():
    assert _feed_all('{"final": "Peace is yours."}') == "Peace is yours."


def test_emits_nothing_for_a_tool_call():
    assert (
        _feed_all('{"tool_call": {"name": "find_claims", "arguments": {}}}') == ""
    )


def test_survives_fragments_split_mid_key_and_mid_value():
    assert _feed_all('{"fin', 'al": "', "Hel", 'lo"}') == "Hello"


def test_unescapes_quotes_and_newlines():
    assert _feed_all('{"final": "a \\"quote\\"\\nnext"}') == 'a "quote"\nnext'


def test_ignores_a_nested_final_key():
    raw = '{"tool_call": {"arguments": {"final": "not this"}}}'
    assert _feed_all(raw) == ""


def test_stops_at_the_closing_quote():
    assert _feed_all('{"final": "done"} trailing junk') == "done"
