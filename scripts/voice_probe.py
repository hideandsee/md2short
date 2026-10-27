"""실제 ElevenLabs TTS + Scribe를 짧은 문장에 1회 호출해 테스트 fixture로 저장한다.

usage: uv run python scripts/voice_probe.py [out_dir]   (기본 tests/fixtures/probe)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import find_dotenv, load_dotenv

from md2short.render import get_audio_duration_ms
from md2short.schema import DEFAULT_VOICES
from md2short.transcript import transcribe
from md2short.tts_text import prepare_tts_text
from md2short.voice import synthesize

PROBE_TEXT = "간밤 뉴욕 증시에서 S&P 500 지수가 1.2% 올랐습니다. 코스피는 0.9% 오른 2,710포인트에 마감했습니다."


def run(out_dir: Path) -> dict:
    load_dotenv(find_dotenv(usecwd=True))
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set (.env)")
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = out_dir / "narration.mp3"
    with httpx.Client() as client:
        synthesize(prepare_tts_text(PROBE_TEXT), voice_id=DEFAULT_VOICES["ko"], speed=1.0, api_key=key,
                   client=client, out_path=audio, log_dir=out_dir)
        audio_ms = get_audio_duration_ms(audio)
        doc = transcribe(audio, api_key=key, client=client, audio_duration_ms=audio_ms, log_dir=out_dir)
    (out_dir / "words.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "probe_text.txt").write_text(PROBE_TEXT + "\n", encoding="utf-8")
    summary = {
        "audio_duration_ms": audio_ms,
        "words": len(doc.words),
        "last_word_end_ms": doc.words[-1].end if doc.words else None,
        "tail_silence_ms": audio_ms - doc.words[-1].end if doc.words else None,
    }
    (out_dir / "probe_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "tests/fixtures/probe"
    print(json.dumps(run(target), indent=2))
