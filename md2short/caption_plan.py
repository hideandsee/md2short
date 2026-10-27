"""자막 segment 분할의 유일한 구현 (Remotion은 결과를 그리기만 함).

boundary: 단어 끝 구두점(`.!?。！？…`) 또는 다음 단어까지 gap ≥ 600ms,
또는 `chunk_size` 단어 상한. 오프닝 구간 단어는 자막에서 제외한다.
"""

from __future__ import annotations

from md2short.schema import CaptionSegment, FramedWord, Word
from md2short.timeutil import ms_to_frames

SENTENCE_PUNCT = tuple(".!?。！？…")
GAP_BOUNDARY_MS = 600


def framed(word: Word) -> FramedWord:
    return FramedWord(
        text=word.text,
        start_ms=word.start,
        end_ms=word.end,
        start_frame=ms_to_frames(word.start),
        end_frame=ms_to_frames(word.end),
    )


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
            ranges.append((start, nxt))
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
