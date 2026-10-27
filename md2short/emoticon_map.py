"""호랑이 emoticon cue planner (docs/architecture.md §5.8, visual_mode=emoticon).

키워드 사전은 `emoticon/NN_키워드_설명.png` 파일명에서 만든다.
- 파일명 조각(`폭락`, `패닉하락`)은 exact keyword(가중치 2)
- 조각 안의 다른 파일 조각·도메인 용어(`DOMAIN_TERMS`)는 sub keyword(가중치 1).
  어휘에 없는 나머지 조각(`검색강세`의 `강세`)은 매칭에 쓰지 않는다.

호랑이 그림에는 "급등", "계약 승인" 같은 문구가 그려져 있어 내레이션과 어긋나면 잘못된 정보가 된다.
그래서 이미지는 자막 segment가 아니라 **문장** 단위로 고르고, 아래 조건을 통과한 것만 쓴다.
- 방향: 이미지의 상승/하락(파일명 기준)이 문장 방향과 같아야 함. 방향 없는 문장엔 방향 있는 이미지를 쓰지 않음
- 주장: 이미지 파일명의 사건 어휘(`CLAIM_TERMS`: 급등, 계약, 동결…)가 문장에 없으면 제외
- 주제: 이미지의 구체 주제(반도체·유가·금리…, 증시·주가·지수 제외)가 문장에 하나도 없으면 제외
선택: 점수(주제 키워드 가중치[방향 어휘는 0.5] + 방향 일치 1.5 + 문장에 나온 사건 어휘당 1 − 최근 3문장 재사용 1.5) → 가장 긴 키워드 → 낮은 NN.
통과 후보가 없으면 방향별 범용 이미지 → 숫자 차트 → 중립 순서.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from md2short.caption_plan import SENTENCE_PUNCT
from md2short.schema import CaptionSegment, EmoticonCue
from md2short.timeutil import ms_to_frames

NEUTRAL_DEFAULTS = (
    "01_정독중_리포트.png",
    "12_리포트작성_공부.png",
    "05_분석중_차트.png",
    "06_움직임없음_관망.png",
)
NUMBER_FALLBACK = "05_분석중_차트.png"
GENERIC_BY_DIRECTION = {
    "up": ("09_가즈아_상승.png", "30_랠리_상승파티.png"),
    "down": ("04_나도울고싶어_하락.png", "15_존버중_버티기.png"),
}
DOMAIN_TERMS = frozenset(
    {
        "유가", "원유", "급등", "급락", "상승", "하락", "폭락", "반도체", "금리", "동결", "매도", "매수",
        "실적", "성장", "지수", "증시", "환율", "물가", "랠리", "혼조", "매파", "국채", "연준", "협상",
        "긴장", "봉쇄", "휴전", "클라우드", "검색", "소비", "심리", "파업", "테마주", "주가", "AI", "OPEC",
    }
)
# 이미지에 그려진 '사건' 어휘: 문장에 없으면 그 이미지를 쓰지 않는다.
CLAIM_TERMS = frozenset(
    {
        "급등", "폭락", "급락", "최고치", "신고가", "계약", "승인", "동결", "파업", "탈퇴", "배치", "봉쇄", "매파",
        "금지", "취소", "손절", "상폐", "미달", "우려", "깜짝", "연속", "협력", "협업", "소각", "장례식", "초읽기",
        "교착", "만료", "수령", "타격", "위기", "혼조", "익절", "전량", "물타기", "추격", "FOMO", "평화", "매도",
        "111달러", "6500톤", "60일", "47퍼센트",
    }
)
# 방향 어휘: 이미지 파일명과 문장 양쪽에 같은 표로 적용한다.
UP_TERMS = ("상승", "급등", "랠리", "로켓", "가즈아", "최고치", "신고가", "강세", "호조", "성장", "올랐", "오른", "올라",
            "반등", "치솟", "늘었", "증가", "상향")
DOWN_TERMS = ("하락", "폭락", "급락", "약세", "손절", "매도", "상폐", "추락", "내렸", "내린", "내려", "떨어", "밀렸",
              "줄었", "감소", "하향", "울고")
# 시장 전반을 가리키는 말: 이미지 주제로 강제하지 않는다
GENERIC_TOPICS = frozenset({"증시", "주가", "지수"})
DIRECTION_BONUS = 1.5
CLAIM_BONUS = 1.0
REUSE_PENALTY = 1.5
RECENT_SENTENCES = 3

_NAME_RE = re.compile(r"^(\d+)_(.+)\.png$")
_NUMBER_RE = re.compile(r"\d")
_UNIT_NUMBER_RE = re.compile(r"\d[\d,.]*\s?(?:%|퍼센트|포인트|p\b|원|달러|조|억|만)")


def direction_of(text: str) -> str | None:
    up = any(t in text for t in UP_TERMS)
    down = any(t in text for t in DOWN_TERMS)
    if up == down:
        return None
    return "up" if up else "down"


@dataclass(frozen=True)
class EmoticonEntry:
    file_name: str
    number: int
    exact: tuple[str, ...]
    sub: tuple[str, ...] = field(default_factory=tuple)
    direction: str | None = None
    claims: tuple[str, ...] = field(default_factory=tuple)
    topics: tuple[str, ...] = field(default_factory=tuple)


def build_keyword_index(emoticon_dir: Path) -> list[EmoticonEntry]:
    raw: list[tuple[str, int, list[str]]] = []
    for path in sorted(emoticon_dir.glob("*.png")):
        m = _NAME_RE.match(path.name)
        if not m:
            continue
        parts = [p for p in m.group(2).split("_") if len(p) >= 2]
        raw.append((path.name, int(m.group(1)), parts))
    vocab = {p for _, _, parts in raw for p in parts} | DOMAIN_TERMS
    entries: list[EmoticonEntry] = []
    for name, number, parts in raw:
        sub = {word for part in parts for word in vocab if word != part and word in part}
        joined = "_".join(parts)
        # 하락을 사는 그림(물타기·하락매수)은 상승 어휘가 섞여도 하락 장면이다
        direction = "down" if any(t in joined for t in DOWN_TERMS) else direction_of(joined)
        claims = tuple(sorted(c for c in CLAIM_TERMS if c in joined))
        topics = tuple(
            sorted(t for t in DOMAIN_TERMS - CLAIM_TERMS - GENERIC_TOPICS if t in joined and not direction_of(t))
        )
        entries.append(
            EmoticonEntry(name, number, tuple(parts), tuple(sorted(sub - set(parts))), direction, claims, topics)
        )
    return entries


@dataclass(frozen=True)
class Match:
    entry: EmoticonEntry
    score: float
    longest: str


def _allowed(entry: EmoticonEntry, text: str, direction: str | None) -> bool:
    if entry.direction is not None and entry.direction != direction:
        return False
    if entry.topics and not any(t in text for t in entry.topics):
        return False  # 반도체 그림을 유가 문장에 쓰지 않음
    return all(c in text for c in entry.claims)


def _weight(keyword: str, base: float) -> float:
    """방향 어휘(상승·하락…)는 방향 보너스로 따로 반영하므로 주제 점수는 낮게 준다."""
    return 0.5 if direction_of(keyword) else base


def best_match(text: str, index: list[EmoticonEntry], *, recent: frozenset[str] = frozenset()) -> Match | None:
    """주제 키워드가 맞고 방향·주장 조건을 통과한 이미지 중 최고점. 없으면 None."""
    direction = direction_of(text)
    best: Match | None = None
    best_key: tuple[float, int, int] | None = None
    for entry in index:
        hits = [(k, _weight(k, 2)) for k in entry.exact if k in text] + [(k, _weight(k, 1)) for k in entry.sub if k in text]
        if not hits or not _allowed(entry, text, direction):
            continue
        score = (
            sum(w for _, w in hits)
            + (DIRECTION_BONUS if entry.direction and entry.direction == direction else 0)
            + CLAIM_BONUS * len(entry.claims)  # 문장에 실제로 나온 사건 어휘(_allowed 통과)
        )
        if entry.file_name in recent:
            score -= REUSE_PENALTY
        longest = max((k for k, _ in hits), key=len)
        key = (score, len(longest), -entry.number)
        if best_key is None or key > best_key:
            best, best_key = Match(entry, score, longest), key
    return best


def _pick_fallback(text: str, recent: frozenset[str], counter: int) -> str:
    generic = GENERIC_BY_DIRECTION.get(direction_of(text) or "")
    if generic:
        fresh = [g for g in generic if g not in recent]
        return (fresh or list(generic))[0]
    if _NUMBER_RE.search(text) and NUMBER_FALLBACK not in recent:
        return NUMBER_FALLBACK
    fresh = [n for n in NEUTRAL_DEFAULTS if n not in recent]
    pool = fresh or list(NEUTRAL_DEFAULTS)
    return pool[counter % len(pool)]


def _highlight(segment: CaptionSegment, match: Match | None) -> str | None:
    """강조 우선순위: 단위 붙은 수치(1.2%, 2,710포인트, 1조) → 방향 동사 → 이미지 키워드 → 그 밖의 숫자."""
    for w in segment.words:
        if _UNIT_NUMBER_RE.search(w.text):
            return w.text
    for w in segment.words:
        if direction_of(w.text):
            return w.text
    if match:
        for k in sorted((*match.entry.exact, *match.entry.sub), key=len, reverse=True):
            if k in segment.text:
                return k
    for w in segment.words:
        if _NUMBER_RE.search(w.text):
            return w.text
    return None


def sentence_groups(segments: list[CaptionSegment]) -> list[list[int]]:
    """연속 segment를 문장 단위로 묶는다(마지막 segment가 구두점으로 끝날 때 문장 종료)."""
    groups: list[list[int]] = [[]]
    for i, seg in enumerate(segments):
        groups[-1].append(i)
        if seg.text.endswith(SENTENCE_PUNCT) and i + 1 < len(segments):
            groups.append([])
    return [g for g in groups if g]


def plan_cues(
    segments: list[CaptionSegment],
    *,
    audio_duration_ms: int,
    emoticon_dir: Path,
    hints: dict[int, str] | None = None,
) -> list[EmoticonCue]:
    """caption segment마다 cue 1개(다음 segment 시작까지). 이미지는 문장 단위로 고른다.

    `hints`(segment index → 텍스트, 예: 스토리보드 `화면 연출`)는 그 segment가 속한 문장의 매칭 텍스트에 더한다.
    선택한 highlight keyword는 segment에 기록한다.
    """
    index = build_keyword_index(emoticon_dir)
    cues: list[EmoticonCue] = []
    history: list[str] = []
    for n, group in enumerate(sentence_groups(segments)):
        sentence = " ".join(segments[i].text for i in group)
        hint = " ".join(dict.fromkeys((hints or {}).get(segments[i].index, "") for i in group))
        # 공백 제거본도 함께 본다: Scribe가 한 단어를 쪼갠 경우(`폭 락`)에도 키워드가 잡히게.
        text = f"{hint} {sentence} | {sentence.replace(' ', '')}"
        recent = frozenset(history[-RECENT_SENTENCES:])
        match = best_match(text, index, recent=recent)
        file_name = match.entry.file_name if match else _pick_fallback(text, recent, n)
        keyword = match.longest if match else None
        history.append(file_name)
        for i in group:
            seg = segments[i]
            seg.highlight_keyword = _highlight(seg, match)
            start_ms = seg.start_ms
            end_ms = segments[i + 1].start_ms if i + 1 < len(segments) else max(seg.end_ms, audio_duration_ms)
            start_frame = ms_to_frames(start_ms)
            cues.append(
                EmoticonCue(
                    emoticon_file_name=f"emoticon/{file_name}",
                    keyword=keyword,
                    start_ms=start_ms,
                    duration_ms=end_ms - start_ms,
                    start_frame=start_frame,
                    duration_frames=max(1, ms_to_frames(end_ms) - start_frame),
                )
            )
    return cues
