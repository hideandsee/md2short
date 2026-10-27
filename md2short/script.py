"""마크다운 → 내레이션 텍스트 fallback 추출 (한국어 전용)."""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```.*?```", re.S)
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_INLINE_RE = re.compile(r"(\*\*|__|\*|_|`|~~)")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_SENTENCE_END = (".", "!", "?", "。", "…")


def strip_markdown_lines(markdown: str) -> list[str]:
    """본문 문장만 남긴다. 제목·인용·표·코드 블록은 버린다."""
    text = _FENCE_RE.sub("", markdown)
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ">", "|")) or set(line) <= {"-", "*", "_", "="}:
            continue
        line = _BULLET_RE.sub("", line)
        line = _LINK_RE.sub(r"\1", line)
        line = _INLINE_RE.sub("", line).strip()
        if line:
            lines.append(line)
    return lines


def fallback_extract(markdown: str) -> str:
    sentences = []
    for line in strip_markdown_lines(markdown):
        sentences.append(line if line.endswith(_SENTENCE_END) else line + ".")
    return " ".join(sentences)
