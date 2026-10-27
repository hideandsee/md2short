"""회사 로고 cue: `company/<회사명>.png` 파일명이 발화된 단어에 나오면 그 단어 시점에 표시."""

from __future__ import annotations

from pathlib import Path

from md2short.schema import CompanyLogoCue, Word
from md2short.timeutil import ms_to_frames

LOGO_DURATION_MS = 2000
LOGO_COOLDOWN_MS = 4000


def plan_company_logo_cues(
    display_words: list[Word], *, company_dir: Path, audio_duration_ms: int, skip_words: int = 0
) -> list[CompanyLogoCue]:
    if not company_dir.is_dir():
        return []
    logos = {p.stem: p.name for p in sorted(company_dir.glob("*.png"))}
    if not logos:
        return []
    cues: list[CompanyLogoCue] = []
    last_shown: dict[str, int] = {}
    for word in display_words[skip_words:]:
        for company, file_name in logos.items():
            if company not in word.text:
                continue
            if company in last_shown and word.start - last_shown[company] < LOGO_COOLDOWN_MS:
                continue
            end = min(word.start + LOGO_DURATION_MS, audio_duration_ms)
            if end <= word.start:
                continue
            start_frame = ms_to_frames(word.start)
            cues.append(
                CompanyLogoCue(
                    company=company,
                    logo_file_name=f"company/{file_name}",
                    start_ms=word.start,
                    duration_ms=end - word.start,
                    start_frame=start_frame,
                    duration_frames=max(1, ms_to_frames(end) - start_frame),
                )
            )
            last_shown[company] = word.start
    return cues
