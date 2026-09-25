"""Incremental extractor that pulls the answer out of a streaming decision call.

The orchestrator's decision LLM emits a JSON object -- `{"final": "...answer..."}` when it
answers directly, or `{"tool_call": {...}}` when it routes to a tool. On the streaming
surface we want the answer's real provider tokens to reach the UI *as they arrive*, but
without leaking the JSON wrapper (`{"final":"`, the closing `"}`, or escape sequences).

`FinalValueExtractor.feed(fragment)` consumes raw decision-stream fragments and returns the
newly-revealed, unescaped characters of the `final` string value -- nothing before the
value opens, nothing after it closes, and nothing at all when the decision is a `tool_call`.
The caller still accumulates the raw text separately to parse the full decision once the
stream ends (tool routing, the final value, fallback) -- this extractor only governs what
is shown live.
"""

_KEY = '"final"'


class FinalValueExtractor:
    """Streaming state machine over decision-call fragments.

    Emits only the characters inside the top-level `final` string value, unescaped. It
    scans for the `"final"` key at object depth 1, then streams the value string until its
    unescaped closing quote. Fragments may split anywhere -- across the key, across an
    escape sequence, mid-\\uXXXX -- so all cross-fragment state lives on the instance.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._pos = 0
        self._in_value = False
        self._done = False
        # Brace depth of self._pos in the enclosing object, tracked as we scan so a
        # `"final"` is only accepted as the top-level key (depth 1), not a nested one
        # like {"tool_call":{"arguments":{"final":...}}}. Braces inside string literals
        # don't count; the scan skips over any string it enters.
        self._depth = 0
        # True while the scan position sits inside a string literal (so `{`/`}` there
        # are data, not structure). Carried across fragments.
        self._in_string = False
        # Pending backslash / partial \uXXXX carried across fragment boundaries.
        self._escape = False
        self._unicode: str | None = None  # None = not in a \uXXXX run

    def feed(self, fragment: str) -> str:
        if self._done:
            return ""
        self._buf += fragment
        if not self._in_value:
            if not self._locate_value_start():
                return ""
        return self._consume_value()

    def _locate_value_start(self) -> bool:
        """Scan the buffer for the top-level `"final"` : `"` opening. Returns True once
        the value's opening quote has been consumed (self._pos then points at the first
        value char). Maintains brace depth across the scan so only a `"final"` key at
        object depth 1 is accepted -- a nested `"final"` key is stepped over.
        """
        buf = self._buf
        n = len(buf)
        i = self._pos
        while i < n:
            if self._in_string:
                # Inside a string literal: skip its contents (honoring escapes) so the
                # `"final"` key-match below can't fire on text sitting inside a value,
                # and so braces here don't move the depth. A `"final"` key is matched
                # separately, at its opening quote, before we enter the string.
                ch = buf[i]
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                i += 1
                continue

            ch = buf[i]
            if ch == "{":
                self._depth += 1
                i += 1
                continue
            if ch == "}":
                self._depth -= 1
                i += 1
                continue
            if ch != '"' or self._depth == 0:
                # At depth 0 we're in the prose/fence before the object opens; quotes
                # there are ordinary text, not JSON string delimiters, so ignore them
                # (an unbalanced prose quote must not swallow the real `{"final"...`).
                i += 1
                continue

            # A string opening inside the object. At depth 1 it may be the top-level
            # `"final"` key.
            if self._depth == 1:
                if buf.startswith(_KEY, i):
                    resolved = self._resolve_key_value(i + len(_KEY))
                    if resolved is not None:
                        return resolved
                    # Matched the key but the `: "` isn't buffered yet -- anchor and wait.
                    self._pos = i
                    return False
                if _KEY.startswith(buf[i:]):
                    # The buffer ends partway through what could be `"final"` (the key
                    # split across this fragment boundary). Anchor at the opening quote
                    # and wait for the rest rather than skipping into it as a string.
                    self._pos = i
                    return False
            self._in_string = True
            i += 1

        # Consumed everything without opening the value. While still at depth 0 (prose
        # before the object) keep only a tail long enough to re-detect a `"final"` key
        # that straddles the next fragment, so prose can't grow the buffer unbounded.
        # Once inside the object, depth/string state is positional -- keep the whole
        # buffer and just advance _pos so that state stays valid.
        keep = len(_KEY) - 1
        if self._depth == 0 and not self._in_string and len(buf) > keep:
            self._buf = buf[-keep:]
            self._pos = 0
        else:
            self._pos = len(self._buf)
        return False

    def _resolve_key_value(self, i: int) -> bool | None:
        """Given `i` positioned just past a matched top-level `"final"` key, expect
        optional ws, `:`, optional ws, `"`. Returns True (value open, state advanced),
        False (`"final"` is a non-string value -- extraction is finished), or None
        (need more buffer to decide)."""
        buf = self._buf
        n = len(buf)
        while i < n and buf[i] in " \t\r\n":
            i += 1
        if i >= n:
            return None
        if buf[i] != ":":
            # `"final"` was a string value, not a key (e.g. "name":"final"). Step into
            # it as an ordinary string and keep scanning.
            self._pos = i
            self._in_string = True
            return self._locate_value_start()
        i += 1
        while i < n and buf[i] in " \t\r\n":
            i += 1
        if i >= n:
            return None
        if buf[i] != '"':
            # `"final": null` / a number / an object -- not a streamable string value.
            self._done = True
            return False
        self._pos = i + 1
        self._in_value = True
        return True

    def _consume_value(self) -> str:
        out: list[str] = []
        buf = self._buf
        n = len(buf)
        i = self._pos
        while i < n:
            ch = buf[i]
            if self._unicode is not None:
                self._unicode += ch
                i += 1
                if len(self._unicode) == 4:
                    try:
                        out.append(chr(int(self._unicode, 16)))
                    except ValueError:
                        pass
                    self._unicode = None
                continue
            if self._escape:
                self._escape = False
                if ch == "u":
                    self._unicode = ""  # collect the next 4 hex digits
                else:
                    out.append(_UNESCAPE.get(ch, ch))
                i += 1
                continue
            if ch == "\\":
                self._escape = True
                i += 1
                continue
            if ch == '"':
                self._done = True
                self._pos = i + 1
                self._buf = ""
                return "".join(out)
            out.append(ch)
            i += 1
        # Consumed everything buffered; drop it so the buffer can't grow unbounded
        # across a long value. Position resets to the fresh (empty) buffer.
        self._buf = ""
        self._pos = 0
        return "".join(out)


_UNESCAPE = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    "/": "/",
    '"': '"',
    "\\": "\\",
}
