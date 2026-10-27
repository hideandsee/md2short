"""TTS 전용 입력 텍스트 보정. 자막 표시 원문은 바꾸지 않는다."""

from __future__ import annotations

import re

_REPLACEMENTS = (
    (re.compile(r"S&P\s*500"), "에스앤피 오백"),
    (re.compile(r"(\d)\s*%"), r"\1퍼센트"),
    (re.compile(r"&"), " 앤 "),
    (re.compile(r"[·ㆍ]"), " "),
    (re.compile(r"[()\[\]{}\"“”‘’]"), " "),
    (re.compile(r"…+|\.{2,}"), "."),
    (re.compile(r"([!?])[!?]+"), r"\1"),
    (re.compile(r"\s*[:;]\s*"), ", "),
    (re.compile(r"\s+"), " "),
)


def prepare_tts_text(text: str) -> str:
    out = text
    for pattern, repl in _REPLACEMENTS:
        out = pattern.sub(repl, out)
    return out.strip()
