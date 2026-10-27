"""ElevenLabs TTS (docs/architecture.md §5.2)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from md2short._retry import post_with_retry

ELEVENLABS_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
TTS_MODEL = "eleven_multilingual_v2"
TTS_OUTPUT_FORMAT = "mp3_44100_128"
TTS_TIMEOUT_S = 120.0
_META_HEADERS = ("request-id", "x-request-id", "character-cost", "x-character-count", "history-item-id")


def synthesize(
    text: str,
    *,
    voice_id: str,
    speed: float,
    api_key: str,
    client: httpx.Client,
    out_path: Path,
    log_dir: Path,
) -> Path:
    response = post_with_retry(
        client,
        ELEVENLABS_TTS_URL.format(voice_id=voice_id),
        timeout=TTS_TIMEOUT_S,
        params={"output_format": TTS_OUTPUT_FORMAT},
        headers={"xi-api-key": api_key, "Accept": "audio/mpeg"},
        json={"text": text, "model_id": TTS_MODEL, "voice_settings": {"speed": speed}},
    )
    out_path.write_bytes(response.content)
    meta = {
        "status_code": response.status_code,
        "voice_id": voice_id,
        "model_id": TTS_MODEL,
        "output_format": TTS_OUTPUT_FORMAT,
        "chars": len(text),
        "bytes": len(response.content),
        "headers": {h: response.headers[h] for h in _META_HEADERS if h in response.headers},
    }
    (log_dir / "tts_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
