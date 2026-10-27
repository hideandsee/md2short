"""날짜 기반 오프닝 (docs/architecture.md §5.10).

오프닝 구간 길이는 추정하지 않고 `words.json`에서 오프닝 단어를 찾아 결정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from md2short.schema import NumberCard, Word

OPENING_ANCHOR = "타이거살구브리핑"
_MAX_OPENING_WORDS = 8
_NON_HANGUL_RE = re.compile(r"[^가-힣]")


def spoken_opening(d: date) -> str:
    return f"{d.month}월 {d.day}일 {OPENING_ANCHOR}입니다."


def opening_visual_text(d: date) -> str:
    return f"{d:%y}년 {d.month}월 {d.day}일\n{OPENING_ANCHOR}"


@dataclass(frozen=True)
class OpeningWindow:
    word_count: int
    end_ms: int  # 오프닝 화면 유지 끝: 다음 단어 시작(없으면 마지막 오프닝 단어 끝). 자막과 사이 빈 화면 방지.


def find_opening_window(words: list[Word]) -> OpeningWindow:
    """앞쪽 단어 중 `타이거살구브리핑`이 나오는 단어까지를 오프닝 구간으로 보고, 다음 단어 시작까지 화면을 유지한다. 없으면 0."""
    for i, word in enumerate(words[:_MAX_OPENING_WORDS]):
        if OPENING_ANCHOR in _NON_HANGUL_RE.sub("", word.text):
            nxt = words[i + 1].start if i + 1 < len(words) else word.end
            return OpeningWindow(word_count=i + 1, end_ms=nxt)
    return OpeningWindow(word_count=0, end_ms=0)


_DATE_PATTERNS = (
    re.compile(r"^date:\s*(\d{4})-(\d{1,2})-(\d{1,2})", re.M),
    re.compile(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})"),
    re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일"),
)
_DATE_SCAN_LINES = 8
_ARROWS = {"up": "▲", "down": "▼"}
HOOK_CARDS = 2


def extract_briefing_date(markdown: str) -> date | None:
    """front matter `date:` 또는 앞쪽 8줄 안의 날짜(YYYY-MM-DD, YYYY.MM.DD, YYYY년 M월 D일). 없으면 None."""
    head = "\n".join(markdown.splitlines()[:_DATE_SCAN_LINES])
    for pattern in _DATE_PATTERNS:
        m = pattern.search(head)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
    return None


def opening_subtitle(cards: list[NumberCard], hook: str = "") -> str:
    """오프닝 박스 아래 한 줄 hook: 앞쪽 숫자 카드 2개(라벨 ▲수치). 카드가 없으면 대본 hook."""
    parts = [
        f"{c.label} {_ARROWS.get(c.direction or '', '')}{c.text}".strip()
        for c in cards
        if c.label
    ][:HOOK_CARDS]
    if parts:
        return " · ".join(parts)
    return hook.strip()
