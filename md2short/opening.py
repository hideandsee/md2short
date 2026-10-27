"""날짜 기반 오프닝 (docs/architecture.md §5.10).

오프닝 구간 길이는 추정하지 않고 `words.json`에서 오프닝 단어를 찾아 결정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from md2short.schema import Word

OPENING_ANCHOR = "데이브리핑"
_MAX_OPENING_WORDS = 8
_NON_HANGUL_RE = re.compile(r"[^가-힣]")


def spoken_opening(d: date) -> str:
    return f"{d.month}월 {d.day}일 {OPENING_ANCHOR}입니다."


def opening_visual_text(d: date) -> str:
    return f"{d:%y}년 {d.month}월 {d.day}일\n{OPENING_ANCHOR}"


@dataclass(frozen=True)
class OpeningWindow:
    word_count: int
    end_ms: int


def find_opening_window(words: list[Word]) -> OpeningWindow:
    """앞쪽 단어 중 `데이브리핑`이 나오는 단어까지를 오프닝 구간으로 본다. 없으면 0."""
    for i, word in enumerate(words[:_MAX_OPENING_WORDS]):
        if OPENING_ANCHOR in _NON_HANGUL_RE.sub("", word.text):
            return OpeningWindow(word_count=i + 1, end_ms=word.end)
    return OpeningWindow(word_count=0, end_ms=0)
