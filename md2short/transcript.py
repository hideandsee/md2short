"""ElevenLabs Scribe → `transcripts/words.json` (docs/architecture.md §5.3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from md2short._retry import post_with_retry
from md2short.schema import SCRIBE_LANG, Word, WordsDoc

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"
SCRIBE_MODEL = "scribe_v1"
STT_TIMEOUT_S = 120.0


def seconds_to_ms(seconds: float) -> int:
    return int(float(seconds) * 1000 + 0.5)


def normalize_scribe(payload: dict[str, Any], *, audio_duration_ms: int) -> WordsDoc:
    """`type == "word"`만 남기고(spacing/audio_event 제외) 초 → 정수 ms."""
    words: list[Word] = []
    for item in payload.get("words", []):
        if item.get("type", "word") != "word":
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        start = seconds_to_ms(item["start"])
        end = max(start, seconds_to_ms(item["end"]))
        words.append(Word(text=text, start=start, end=end))
    return WordsDoc(
        language_code=payload.get("language_code") or SCRIBE_LANG["ko"],
        audio_duration_ms=audio_duration_ms,
        text=str(payload.get("text", "")),
        words=words,
    )


def transcribe(
    audio_path: Path,
    *,
    api_key: str,
    client: httpx.Client,
    audio_duration_ms: int,
    log_dir: Path,
    language: str = "ko",
) -> WordsDoc:
    with audio_path.open("rb") as fh:
        response = post_with_retry(
            client,
            ELEVENLABS_STT_URL,
            timeout=STT_TIMEOUT_S,
            headers={"xi-api-key": api_key},
            data={
                "model_id": SCRIBE_MODEL,
                "language_code": SCRIBE_LANG[language],
                "timestamps_granularity": "word",
                "tag_audio_events": "false",
            },
            files={"file": (audio_path.name, fh, "audio/mpeg")},
        )
    payload = response.json()
    (log_dir / "scribe_raw.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalize_scribe(payload, audio_duration_ms=audio_duration_ms)
