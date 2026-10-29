"""자막 segment 분할의 유일한 구현 (Remotion은 결과를 그리기만 함).

boundary: 단어 끝 구두점(`.!?。！？…`) 또는 다음 단어까지 gap ≥ 600ms,
또는 `chunk_size` 단어 상한. 오프닝 구간 단어는 자막에서 제외한다.
문장이 `MAX_CAPTION_CHARS`(2줄 분량)를 넘으면 쉼표를 우선해 글자 수가 고르게 나뉘도록 다시 쪼갠다
(Remotion의 2줄 clamp에 걸려 내용이 잘리지 않게).
"""

from __future__ import annotations

import re

from md2short.schema import CaptionSegment, FramedWord, Word
from md2short.timeutil import ms_to_frames

SENTENCE_PUNCT = tuple(".!?。！？…")
GAP_BOUNDARY_MS = 600
MAX_CAPTION_CHARS = 26
_SOFT_BREAK = (",", "，", "、")
_NUMBER_TAIL_RE = re.compile(r"\d[\d,.]*(?:조|억|천억|만|천)?$")
# 어절 끝이 조사·접속어미면 구가 닫힌 곳이라 자막을 끊기 좋다('발표될'·'데이터센터'처럼 뒤 말을 꾸미는 어절은 피함)
_PHRASE_END_RE = re.compile(r"(?:[이가은는을를에의와과도로만]|에서|으로|까지|부터|에게|고|며|서|면|지만|다)[.,!?]?$")
_MODIFIER_END_RE = re.compile(r"[될할갈볼낼][,]?$")  # 뒤 명사를 꾸미는 관형형은 뒤 말과 붙여 둔다
_UNIT_HEAD_RE = re.compile(r"^(?:\d|원|달러|억|조|만|천|%|포인트|퍼센트)")


def framed(word: Word) -> FramedWord:
    return FramedWord(
        text=word.text,
        start_ms=word.start,
        end_ms=word.end,
        start_frame=ms_to_frames(word.start),
        end_frame=ms_to_frames(word.end),
    )


def _chars(words: list[Word], a: int, b: int) -> int:
    return len(" ".join(w.text for w in words[a:b] if w.text))


def split_long_range(words: list[Word], a: int, b: int, max_chars: int = MAX_CAPTION_CHARS) -> list[tuple[int, int]]:
    """[a, b)가 max_chars를 넘으면 글자 수가 고른 조각으로 나눈다. 쉼표 뒤 경계를 우선한다."""
    total = _chars(words, a, b)
    if total <= max_chars or b - a < 2:
        return [(a, b)]
    parts = -(-total // max_chars)
    target = total / parts
    best_cut, best_cost = None, None
    for cut in range(a + 1, b):
        left = _chars(words, a, cut)
        if left > max_chars and best_cut is not None:
            break
        cost = abs(left - target) - (target * 0.35 if words[cut - 1].text.endswith(_SOFT_BREAK) else 0)
        if not _PHRASE_END_RE.search(words[cut - 1].text):
            cost += target * 0.3  # 구 중간에서 끊지 않음
        if _MODIFIER_END_RE.search(words[cut - 1].text):
            cost += target * 0.3
        if not words[cut - 1].text:  # 비운 단어 뒤에서 끊으면 원문 표기(S&P 500 등)가 갈라짐
            cost += total
        if _NUMBER_TAIL_RE.search(words[cut - 1].text) and _UNIT_HEAD_RE.match(words[cut].text):
            cost += total  # ‘1조 2천억 / 원’처럼 숫자와 단위를 가르지 않음
        if best_cost is None or cost < best_cost:
            best_cut, best_cost = cut, cost
    assert best_cut is not None
    return [(a, best_cut), *split_long_range(words, best_cut, b, max_chars)]


def split_word_ranges(
    words: list[Word], *, chunk_size: int, skip_words: int = 0, forced_breaks: frozenset[int] = frozenset()
) -> list[tuple[int, int]]:
    """단어 인덱스 범위 [start, end) 목록. `forced_breaks`는 그 인덱스 앞에서 끊는다(스토리보드 컷)."""
    ranges: list[tuple[int, int]] = []
    start = skip_words
    for i in range(skip_words, len(words)):
        nxt = i + 1
        is_last = nxt == len(words)
        boundary = (
            is_last
            or words[i].text.endswith(SENTENCE_PUNCT)
            or words[nxt].start - words[i].end >= GAP_BOUNDARY_MS
            or nxt - start >= chunk_size
            or nxt in forced_breaks
        )
        if boundary:
            ranges.extend(split_long_range(words, start, nxt))
            start = nxt
    return ranges


def build_caption_segments(
    words: list[Word],
    *,
    chunk_size: int,
    skip_words: int = 0,
    forced_breaks: frozenset[int] = frozenset(),
) -> list[CaptionSegment]:
    ranges = split_word_ranges(words, chunk_size=chunk_size, skip_words=skip_words, forced_breaks=forced_breaks)
    return segments_from_ranges(words, ranges)


def segments_from_ranges(words: list[Word], ranges: list[tuple[int, int]]) -> list[CaptionSegment]:
    """단어 범위 → CaptionSegment. 스토리보드는 컷 범위를 그대로 넘긴다."""
    segments: list[CaptionSegment] = []
    for idx, (a, b) in enumerate(ranges):
        start_ms = words[a].start
        last_end = words[b - 1].end
        # 다음 자막이 바로 이어지면(gap < 600ms) 그 시작까지 유지해 깜빡임을 없앤다.
        if idx + 1 < len(ranges):
            next_start = words[ranges[idx + 1][0]].start
            end_ms = next_start if next_start - last_end < GAP_BOUNDARY_MS else last_end
        else:
            end_ms = last_end
        segments.append(
            CaptionSegment(
                index=idx,
                text=" ".join(w.text for w in words[a:b] if w.text),
                start_ms=start_ms,
                end_ms=end_ms,
                start_frame=ms_to_frames(start_ms),
                end_frame=ms_to_frames(end_ms),
                word_start=a,
                word_end=b,
                words=[framed(w) for w in words[a:b] if w.text],  # numeric_display가 비운 단어는 표시하지 않음
            )
        )
    return segments
