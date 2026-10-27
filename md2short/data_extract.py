"""숫자·지표 NumberCard cue (docs/architecture.md §5.9).

카드 후보는 대본 원문에서 정규식으로 뽑고, 시점은 표시용 단어 목록(`numeric_display` 적용,
`words.json`과 1:1)에서 그 숫자가 실제로 발화된 단어 구간에 고정한다.
일치하는 단어가 없으면 카드를 만들지 않고 `dropped`에 남긴다(시간 추정 금지, AGENTS.md §3.2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from md2short.schema import NumberCard, Word
from md2short.timeutil import ms_to_frames

MAX_CARDS = 6
COOLDOWN_MS = 2500
CARD_DURATION_MS = 1800
MAX_SPAN_WORDS = 4

_NUM = r"\d[\d,]*(?:\.\d+)?"
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # 지수 레벨: 지수명 뒤 12자 안의 '숫자+포인트' (퍼센트·금액은 아래 패턴 몫)
    ("index", re.compile(rf"(코스피|코스닥|S&P\s?500|나스닥|다우|니케이|항셍)[^\d%]{{0,12}}?({_NUM}\s?(?:포인트|p\b))")),
    ("money", re.compile(rf"{_NUM}\s?(?:조|억|만)(?:\s?{_NUM}?\s?(?:천억|백억|십억|억|천만|백만|만|천))*\s?(?:원|달러)")),
    ("percent", re.compile(rf"{_NUM}\s?(?:%|퍼센트|프로)")),
    ("points", re.compile(rf"{_NUM}\s?(?:포인트|p\b)")),
)
_DIGIT_CORE_RE = re.compile(_NUM)


@dataclass(frozen=True)
class Candidate:
    kind: str
    text: str
    core: str  # 단어 매칭에 쓰는 첫 숫자(쉼표 제거)
    pos: int


def extract_candidates(script_text: str) -> list[Candidate]:
    taken: list[tuple[int, int]] = []
    found: list[Candidate] = []
    for kind, regex in PATTERNS:
        for m in regex.finditer(script_text):
            span = m.span(2) if kind == "index" else m.span(0)
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            taken.append(span)
            if kind == "index":
                name = re.sub(r"\s", " ", m.group(1))
                text = f"{name} {m.group(2).strip()}"
                number = m.group(2)
            else:
                text = re.sub(r"\s+", " ", m.group(0).strip())
                number = m.group(0)
            core = _DIGIT_CORE_RE.search(number).group(0).replace(",", "")  # type: ignore[union-attr]
            found.append(Candidate(kind, text, core, span[0]))
    return sorted(found, key=lambda c: c.pos)


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text.replace(",", "").replace(" ", ""))


def _anchor(words: list[Word], cand: Candidate, cursor: int) -> tuple[int, int] | None:
    for i in range(cursor, len(words)):
        if not any(ch.isdigit() for ch in words[i].text):
            continue  # 카드는 숫자가 처음 발화된 단어에서 시작한다
        joined = ""
        for k in range(1, MAX_SPAN_WORDS + 1):
            if i + k > len(words):
                break
            joined += words[i + k - 1].text.replace(",", "").replace(" ", "")
            if not joined:
                continue
            if cand.core in _numbers(joined):
                a, b = i, i + k
                while a + 1 < b and cand.core in _numbers("".join(w.text for w in words[a + 1 : b])):
                    a += 1  # 가장 짧은 구간으로 줄인다(‘S&P 500은 1.2%’ → ‘1.2%’)
                return a, b
    return None


def plan_number_cards(
    display_words: list[Word], script_text: str, *, audio_duration_ms: int, skip_words: int = 0
) -> tuple[list[NumberCard], list[dict]]:
    cards: list[NumberCard] = []
    dropped: list[dict] = []
    cursor = skip_words
    last_start: int | None = None
    for cand in extract_candidates(script_text):
        span = _anchor(display_words, cand, cursor)
        if span is None:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "no matching word in words.json"})
            continue
        a, b = span
        cursor = b
        start = display_words[a].start
        if len(cards) >= MAX_CARDS:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "max_cards"})
            continue
        if last_start is not None and start - last_start < COOLDOWN_MS:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "cooldown"})
            continue
        end = min(start + CARD_DURATION_MS, audio_duration_ms)
        if end <= start:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "after_audio_end"})
            continue
        start_frame = ms_to_frames(start)
        cards.append(
            NumberCard(
                text=cand.text,
                word_start=a,
                word_end=b,
                start_ms=start,
                duration_ms=end - start,
                start_frame=start_frame,
                duration_frames=max(1, ms_to_frames(end) - start_frame),
            )
        )
        last_start = start
    return cards, dropped
