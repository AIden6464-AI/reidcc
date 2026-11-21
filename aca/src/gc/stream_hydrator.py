"""Streaming GC Pointer Hydrator (`src/gc/stream_hydrator.py`).

Implements a stateful token-boundary buffer for `POST /v1/proxy/chat/completions`
when `stream=True`. When an opening `<` or `[` is detected in an SSE delta chunk,
it buffers up to `max_buffer_len` (default 24) characters until the closing `>` or `]`
arrives, hydrates any matched GC pointer (`<P_x>`, `[STATE_x]`, `[CMD_x]`, `<GUID_x>`, etc.),
and flushes immediately if a non-pointer character invalidates the pattern.

Plain entity pointers (`U1`, `C1`, `I1`, `W1`, `R1`) have no brackets, so trailing word
characters are held back until a word boundary arrives and then expanded as a whole word,
matching the non-streaming `GCEngine.expand` output.
"""

from __future__ import annotations

import re
from typing import Iterator, List

from src.gc.gc_engine import GCEngine


class StreamHydrator:
    """Stateful token-boundary buffer for streaming SSE GC pointer hydration."""

    # Valid characters inside a bracketed GC pointer: e.g. <P_12>, [STATE_3], [CMD_1], <GUID_4>
    VALID_INNER_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
    WORD_CHARS = VALID_INNER_CHARS
    OPEN_TO_CLOSE = {"<": ">", "[": "]"}
    POINTER_EXACT_RE = re.compile(
        r"^(?:<P_\d+>|<GUID_\d+>|<HASH_\d+>|<SID_\d+>|<TMP_\d+>|<TOK_\d+>|<ID_\d+>|\[STATE_\d+\]|\[CMD_\d+\])$"
    )
    # Plain entity pointers are short; longer words are streamed through without holding them back
    MAX_WORD_HOLD = 32

    def __init__(self, gc_engine: GCEngine, max_buffer_len: int = 24, *, unmask: bool = True) -> None:
        self.gc = gc_engine
        self.max_buffer_len = max_buffer_len
        self.unmask = unmask
        self._buf: List[str] = []
        self._expected_close: str | None = None
        self._word: List[str] = []
        self._word_overflow = False

    def _reset(self) -> str:
        raw = "".join(self._buf)
        self._buf.clear()
        self._expected_close = None
        return raw

    def _drain_word(self) -> str:
        word = "".join(self._word)
        self._word.clear()
        self._word_overflow = False
        return self.gc.expand(word, unmask=self.unmask) if word else ""

    def push_chunk(self, chunk: str) -> str:
        """Process an incoming delta chunk character-by-character through the buffer
        and return the immediately safe hydrated string.
        """
        if not chunk:
            return ""

        out: List[str] = []
        for ch in chunk:
            if self._expected_close is None:
                if ch in self.OPEN_TO_CLOSE:
                    out.append(self._drain_word())
                    self._buf.append(ch)
                    self._expected_close = self.OPEN_TO_CLOSE[ch]
                elif ch in self.WORD_CHARS:
                    if self._word_overflow:
                        out.append(ch)
                    elif len(self._word) >= self.MAX_WORD_HOLD:
                        # Too long to be an entity pointer: release it unexpanded
                        out.append("".join(self._word))
                        out.append(ch)
                        self._word.clear()
                        self._word_overflow = True
                    else:
                        self._word.append(ch)
                else:
                    out.append(self._drain_word())
                    self._word_overflow = False
                    out.append(ch)
            else:
                # Currently buffering a potential pointer starting with '<' or '['
                if ch == self._expected_close:
                    self._buf.append(ch)
                    candidate = "".join(self._buf)
                    self._buf.clear()
                    self._expected_close = None
                    if self.POINTER_EXACT_RE.match(candidate):
                        out.append(self.gc.expand(candidate, unmask=self.unmask))
                    else:
                        out.append(candidate)
                elif ch in self.OPEN_TO_CLOSE:
                    # A new opener appeared before closing -> flush previous partial buffer
                    out.append(self._reset())
                    self._buf.append(ch)
                    self._expected_close = self.OPEN_TO_CLOSE[ch]
                elif ch in self.VALID_INNER_CHARS and len(self._buf) < self.max_buffer_len:
                    self._buf.append(ch)
                else:
                    # Invalid pointer character or exceeded 24-char buffer -> flush immediately
                    self._buf.append(ch)
                    out.append(self._reset())

        return "".join(out)

    def flush(self) -> str:
        """Flush any remaining held characters at the end of the SSE stream."""
        tail = self._drain_word()
        if self._buf:
            tail += self.gc.expand(self._reset(), unmask=self.unmask)
        return tail

    def stream_hydrate(self, chunks: Iterator[str]) -> Iterator[str]:
        """Generator wrapper that yields hydrated text across arbitrary delta chunks."""
        for chunk in chunks:
            emitted = self.push_chunk(chunk)
            if emitted:
                yield emitted
        rem = self.flush()
        if rem:
            yield rem
