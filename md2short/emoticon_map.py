"""호랑이 emoticon cue planner (docs/architecture.md §5.8, visual_mode=emoticon).

키워드 사전은 `emoticon/NN_키워드_설명.png` 파일명에서 만든다.
- 파일명 조각(`폭락`, `패닉하락`)은 exact keyword(가중치 2)
- 조각 안에 들어 있는 다른 파일의 exact keyword·도메인 용어(`DOMAIN_TERMS`)와 그 나머지
  (`패닉하락` → `하락`, `패닉` / `원유급등` → `원유`, `급등`)는 sub keyword(가중치 1)
선택 순서: 가중치 합 → 가장 긴 매칭 키워드 → 낮은 NN.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from md2short.schema import CaptionSegment, EmoticonCue, Word
from md2short.timeutil import ms_to_frames

LOOKAHEAD_WORDS = 2
NEUTRAL_DEFAULTS = (
    "01_정독중_리포트.png",
    "12_리포트작성_공부.png",
    "05_분석중_차트.png",
    "06_움직임없음_관망.png",
)
NUMBER_FALLBACK = "05_분석중_차트.png"
DOMAIN_TERMS = frozenset(
    {
        "유가", "원유", "급등", "급락", "상승", "하락", "폭락", "반도체", "금리", "동결", "매도", "매수",
        "실적", "성장", "지수", "증시", "환율", "물가", "랠리", "혼조", "매파", "국채", "연준", "협상",
        "긴장", "봉쇄", "휴전", "클라우드", "검색", "소비", "심리", "파업", "테마주", "주가", "AI", "OPEC",
    }
)
_NAME_RE = re.compile(r"^(\d+)_(.+)\.png$")
_NUMBER_RE = re.compile(r"\d")


@dataclass(frozen=True)
class EmoticonEntry:
    file_name: str
    number: int
    exact: tuple[str, ...]
    sub: tuple[str, ...] = field(default_factory=tuple)


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
        sub: set[str] = set()
        for part in parts:
            rest = part
            for word in sorted(vocab, key=len, reverse=True):
                if word != part and word in rest:
                    sub.add(word)
                    rest = rest.replace(word, " ")
            sub.update(piece for piece in rest.split() if len(piece) >= 2 and piece != part)
        entries.append(EmoticonEntry(name, number, tuple(parts), tuple(sorted(sub - set(parts)))))
    return entries


@dataclass(frozen=True)
class Match:
    entry: EmoticonEntry
    score: int
    longest: str


def best_match(text: str, index: list[EmoticonEntry]) -> Match | None:
    best: Match | None = None
    best_key: tuple[int, int, int] | None = None
    for entry in index:
        hits = [(k, 2) for k in entry.exact if k in text] + [(k, 1) for k in entry.sub if k in text]
        if not hits:
            continue
        score = sum(w for _, w in hits)
        longest = max((k for k, _ in hits), key=len)
        key = (score, len(longest), -entry.number)
        if best_key is None or key > best_key:
            best, best_key = Match(entry, score, longest), key
    return best


def _boundary_match(seg: CaptionSegment, words: list[Word], index: list[EmoticonEntry]) -> Match | None:
    """segment 경계에 걸쳐 쪼개진 키워드만 잡는다(lookahead 2 words).

    다음 단어들만으로도 매칭되는 키워드는 다음 segment 몫이므로 제외한다.
    """
    ahead = words[seg.word_end : seg.word_end + LOOKAHEAD_WORDS]
    if not seg.words or not ahead:
        return None
    joined = seg.words[-1].text + "".join(w.text for w in ahead)
    ahead_only = " ".join(w.text for w in ahead)
    straddling = [
        EmoticonEntry(
            e.file_name,
            e.number,
            tuple(k for k in e.exact if k not in ahead_only),
            tuple(k for k in e.sub if k not in ahead_only),
        )
        for e in index
    ]
    return best_match(joined, straddling)


def _highlight(segment: CaptionSegment, match: Match | None) -> str | None:
    if match:
        for k in sorted((*match.entry.exact, *match.entry.sub), key=len, reverse=True):
            if k in segment.text:
                return k
    for w in segment.words:
        if _NUMBER_RE.search(w.text):
            return w.text
    return None


def plan_cues(
    segments: list[CaptionSegment],
    words: list[Word],
    *,
    audio_duration_ms: int,
    emoticon_dir: Path,
    hints: dict[int, str] | None = None,
) -> list[EmoticonCue]:
    """caption segment마다 cue 1개(fill_gaps). 다음 segment 시작까지 유지한다.

    `hints`(segment index → 텍스트, 예: 스토리보드 `화면 연출`)가 있으면 매칭 텍스트 앞에 붙인다.
    선택한 highlight keyword는 segment에 기록한다.
    """
    index = build_keyword_index(emoticon_dir)
    cues: list[EmoticonCue] = []
    for i, seg in enumerate(segments):
        hint = (hints or {}).get(seg.index, "")
        # 공백 제거본도 함께 본다: Scribe가 한 단어를 쪼갠 경우(`폭 락`)에도 키워드가 잡히게.
        text = f"{hint} {seg.text} | {seg.text.replace(' ', '')}"
        match = best_match(text, index) or _boundary_match(seg, words, index)
        if match:
            file_name, keyword = match.entry.file_name, match.longest
        elif _NUMBER_RE.search(seg.text):
            file_name, keyword = NUMBER_FALLBACK, None
        else:
            file_name, keyword = NEUTRAL_DEFAULTS[i % len(NEUTRAL_DEFAULTS)], None
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
