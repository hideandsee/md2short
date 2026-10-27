"""`### N컷` 스토리보드 입력 (docs/architecture.md §5.1, §5.4).

`자막`만 내레이션이 되고, `화면 연출`은 emoticon cue 선택, `이미지 프롬프트`는 photo 모드에만 쓰인다.
컷 경계는 실제 `words.json` 단어에 맞춘다(문장 boundary로 snap, 유사도로 병합).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from md2short.caption_plan import SENTENCE_PUNCT
from md2short.schema import Word

_CUT_HEADER_RE = re.compile(r"^###\s*(\d+)\s*컷\s*$", re.M)
_FIELD_RE = re.compile(r"^\s*[-*]?\s*(자막|화면\s*연출|이미지\s*프롬프트)\s*[:：]\s*(.+?)\s*$", re.M)
_COMPACT_RE = re.compile(r"[가-힣0-9A-Za-z]")
SNAP_TOLERANCE = 0.05
MAX_WORDS_PER_CUT = 80


@dataclass(frozen=True)
class Cut:
    number: int
    caption: str
    direction: str = ""
    image_prompt: str = ""


def is_storyboard(markdown: str) -> bool:
    return bool(_CUT_HEADER_RE.search(markdown))


def parse_storyboard(markdown: str) -> list[Cut]:
    headers = list(_CUT_HEADER_RE.finditer(markdown))
    cuts: list[Cut] = []
    for i, header in enumerate(headers):
        block = markdown[header.end() : headers[i + 1].start() if i + 1 < len(headers) else len(markdown)]
        fields = {re.sub(r"\s", "", k): v for k, v in _FIELD_RE.findall(block)}
        caption = fields.get("자막", "").strip()
        if not caption:
            continue
        cuts.append(
            Cut(
                number=int(header.group(1)),
                caption=caption,
                direction=fields.get("화면연출", "").strip(),
                image_prompt=fields.get("이미지프롬프트", "").strip(),
            )
        )
    return cuts


def narration_text(cuts: list[Cut]) -> str:
    return " ".join(c.caption if c.caption.endswith(SENTENCE_PUNCT) else c.caption + "." for c in cuts)


def cuts_to_json(cuts: list[Cut]) -> list[dict]:
    return [asdict(c) for c in cuts]


def _compact(text: str) -> str:
    return "".join(_COMPACT_RE.findall(text))


def map_cuts_to_segments(words: list[Word], cuts: list[Cut], *, skip_words: int = 0) -> list[tuple[int, int]]:
    """컷마다 [word_start, word_end). 각 컷 끝은 자막과 가장 비슷한 지점, 동률권이면 문장 끝 단어로 snap."""
    ranges: list[tuple[int, int]] = []
    start = skip_words
    for n, cut in enumerate(cuts):
        remaining_cuts = len(cuts) - n - 1
        last_allowed = len(words) - remaining_cuts
        if remaining_cuts == 0 or start >= last_allowed:
            ranges.append((start, len(words) if remaining_cuts == 0 else min(start + 1, len(words))))
            start = ranges[-1][1]
            continue
        target = _compact(cut.caption)
        scored: list[tuple[float, int]] = []
        joined = ""
        for end in range(start + 1, min(last_allowed, start + MAX_WORDS_PER_CUT) + 1):
            joined += _compact(words[end - 1].text)
            scored.append((SequenceMatcher(None, joined, target).ratio(), end))
        best_ratio = max(r for r, _ in scored)
        sentence_ends = [
            (r, e) for r, e in scored if r >= best_ratio - SNAP_TOLERANCE and words[e - 1].text.endswith(SENTENCE_PUNCT)
        ]
        _, end = max(sentence_ends or [(r, e) for r, e in scored if r == best_ratio])
        ranges.append((start, end))
        start = end
    return ranges
