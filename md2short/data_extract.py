"""숫자·지표 NumberCard cue (docs/architecture.md §5.9).

카드 후보는 대본 원문에서 정규식으로 뽑고, 시점은 표시용 단어 목록(`numeric_display` 적용,
`words.json`과 1:1)에서 그 숫자가 실제로 발화된 단어 구간에 고정한다.
일치하는 단어가 없으면 카드를 만들지 않고 `dropped`에 남긴다(시간 추정 금지, AGENTS.md §3.2).
문장마다 대표 수치 1개(방향 어휘가 붙은 퍼센트 우선)만 카드로 만들고, 앞쪽 지표명(라벨)과 상승/하락 방향을 싣는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from md2short.caption_plan import SENTENCE_PUNCT
from md2short.emoticon_map import direction_of
from md2short.schema import NumberCard, Word
from md2short.timeutil import ms_to_frames

MS_PER_CARD = 7000  # 카드 상한 = 오디오 길이 / 7초
MIN_CARDS = 2
COOLDOWN_MS = 2500
CARD_DURATION_MS = 1800
MAX_SPAN_WORDS = 4
LABEL_SCAN_WORDS = 10
DIRECTION_SCAN_WORDS = 3
KIND_PRIORITY = {"percent": 1.0, "index": 1.0, "money": 0.5, "points": 0.5}
STRONG_MOVES = ("급등", "폭락", "급락", "치솟")
LABEL_TERMS = (
    "S&P500", "S&P 500", "S&P", "나스닥", "다우", "코스피", "코스닥", "니케이", "항셍", "반도체", "환율", "국채", "금리",
    "유가", "원유", "WTI", "비트코인", "금값", "달러",
)

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


def _sentence_ids(words: list[Word]) -> list[int]:
    ids, sid = [], 0
    for w in words:
        ids.append(sid)
        if w.text.endswith(SENTENCE_PUNCT):
            sid += 1
    return ids


def _strip_particle(text: str) -> str:
    return re.sub(r"(은|는|이|가|의|도)$", "", text.strip(".,"))


def _label(words: list[Word], a: int, sids: list[int]) -> str | None:
    """카드 앞쪽(같은 문장, 최대 10단어)에서 지표명을 찾는다. 연속된 지표어는 붙인다(국채 금리)."""
    lo = max(0, a - LABEL_SCAN_WORDS)
    back = [j for j in range(a - 1, lo - 1, -1) if sids[j] == sids[a] and words[j].text]
    for j in back:
        term = next((t for t in LABEL_TERMS if t in words[j].text.replace(" ", "")), None)
        if term:
            prev = next((k for k in back if k < j), None)
            prev_term = next((t for t in LABEL_TERMS if prev is not None and t in words[prev].text), None)
            if term.startswith("S&P"):
                return "S&P 500"
            return f"{prev_term} {term}" if prev_term and prev_term != term else term
    for j in back:
        if re.search(r"(은|는|이|가)$", words[j].text) and not any(ch.isdigit() for ch in words[j].text):
            name = _strip_particle(words[j].text)
            if 2 <= len(name) <= 8:
                return name
    return None


def _direction(words: list[Word], a: int, b: int, sids: list[int]) -> str | None:
    window = [w.text for k, w in enumerate(words[a : b + DIRECTION_SCAN_WORDS], start=a) if sids[k] == sids[a]]
    return direction_of(" ".join(window))


def _score(cand: Candidate, words: list[Word], a: int, b: int, sids: list[int]) -> float:
    window = " ".join(w.text for k, w in enumerate(words[a : b + DIRECTION_SCAN_WORDS], start=a) if sids[k] == sids[a])
    strong = 2 if any(t in window for t in STRONG_MOVES) else (1 if direction_of(window) else 0)
    return strong + KIND_PRIORITY.get(cand.kind, 0)


def plan_number_cards(
    display_words: list[Word], script_text: str, *, audio_duration_ms: int, skip_words: int = 0
) -> tuple[list[NumberCard], list[dict]]:
    """문장마다 대표 수치 1개를 골라 단어 구간에 고정한다. 라벨·방향을 함께 싣는다."""
    dropped: list[dict] = []
    sids = _sentence_ids(display_words)
    anchored: list[tuple[Candidate, int, int, float]] = []
    cursor = skip_words
    for cand in extract_candidates(script_text):
        span = _anchor(display_words, cand, cursor)
        if span is None:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "no matching word in words.json"})
            continue
        a, b = span
        cursor = b
        anchored.append((cand, a, b, _score(cand, display_words, a, b, sids)))

    # 문장별 대표 1개(점수 → 먼저 나온 것)
    best: dict[int, tuple[Candidate, int, int, float]] = {}
    for item in anchored:
        sid = sids[item[1]]
        if sid not in best or item[3] > best[sid][3]:
            best[sid] = item
    chosen = sorted(best.values(), key=lambda x: x[1])
    for item in anchored:
        if item not in chosen:
            dropped.append({"text": item[0].text, "kind": item[0].kind, "reason": "not_sentence_representative"})

    cap = max(MIN_CARDS, audio_duration_ms // MS_PER_CARD)
    cards: list[NumberCard] = []
    last_start: int | None = None
    for cand, a, b, _ in chosen:
        start = display_words[a].start
        if last_start is not None and start - last_start < COOLDOWN_MS:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "cooldown"})
            continue
        end = min(start + CARD_DURATION_MS, audio_duration_ms)
        if end <= start:
            dropped.append({"text": cand.text, "kind": cand.kind, "reason": "after_audio_end"})
            continue
        start_frame = ms_to_frames(start)
        label = _label(display_words, a, sids)
        cards.append(
            NumberCard(
                text=cand.text if not (label and cand.kind == "index") else cand.text.split(" ", 1)[-1],
                label=label,
                direction=_direction(display_words, a, b, sids),  # type: ignore[arg-type]
                word_start=a,
                word_end=b,
                start_ms=start,
                duration_ms=end - start,
                start_frame=start_frame,
                duration_frames=max(1, ms_to_frames(end) - start_frame),
            )
        )
        last_start = start
    if len(cards) > cap:
        # 길이 비례 상한: 점수 낮은 카드부터 뺀다(시간 분포는 문장 단위라 이미 고르게 퍼져 있음)
        scores = {id(c): best[sids[c.word_start]][3] for c in cards}
        keep = sorted(cards, key=lambda c: (-scores[id(c)], c.start_ms))[:cap]
        for c in cards:
            if c not in keep:
                dropped.append({"text": c.text, "kind": "card", "reason": "max_cards"})
        cards = sorted(keep, key=lambda c: c.start_ms)
    return cards, dropped
