"""자동 QC + 비용 추정 (docs/architecture.md §5.6)."""

from __future__ import annotations

from typing import Any

SYNC_TAIL_TOLERANCE_MS = 1000
RENDER_AUDIO_TOLERANCE_MS = 100

ELEVENLABS_TTS_USD_PER_1K_CHARS = 0.30
ELEVENLABS_STT_USD_PER_HOUR = 0.40
# 텍스트 모델 근사 단가(USD / 1M tokens). --model별 가격표는 아직 없음(§5.6).
OPENAI_TEXT_INPUT_USD_PER_1M = 0.25
OPENAI_TEXT_OUTPUT_USD_PER_1M = 2.00


def estimate_cost(*, tts_chars: int, audio_duration_ms: int, llm_input_chars: int, llm_output_chars: int) -> dict[str, Any]:
    tts = tts_chars / 1000 * ELEVENLABS_TTS_USD_PER_1K_CHARS
    stt = audio_duration_ms / 1000 / 3600 * ELEVENLABS_STT_USD_PER_HOUR
    llm = (llm_input_chars / 4) / 1e6 * OPENAI_TEXT_INPUT_USD_PER_1M + (llm_output_chars / 4) / 1e6 * OPENAI_TEXT_OUTPUT_USD_PER_1M
    return {
        "currency": "USD",
        "elevenlabs_tts": round(tts, 6),
        "elevenlabs_stt": round(stt, 6),
        "openai_text": round(llm, 6),
        "total": round(tts + stt + llm, 6),
        "excludes": ["gpt-image-2 (photo mode): check the OpenAI invoice"],
    }


def _check(name: str, actual: int, expected: int, tolerance: int) -> dict[str, Any]:
    delta = actual - expected
    return {
        "name": name,
        "passed": abs(delta) <= tolerance,
        "actual_ms": actual,
        "expected_ms": expected,
        "delta_ms": delta,
        "tolerance_ms": tolerance,
    }


def run_qc(
    *,
    audio_duration_ms: int,
    last_word_end_ms: int,
    final_mp4_duration_ms: int,
    cost: dict[str, Any],
    video: dict[str, Any] | None = None,
    endcard_ms: int = 0,
) -> dict[str, Any]:
    checks = [
        _check("sync_last_word_vs_audio", last_word_end_ms, audio_duration_ms, SYNC_TAIL_TOLERANCE_MS),
        _check("final_mp4_vs_audio", final_mp4_duration_ms, audio_duration_ms + endcard_ms, RENDER_AUDIO_TOLERANCE_MS),
    ]
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "duration_policy": {
            "source": "tts_audio_duration",
            "audio_duration_ms": audio_duration_ms,
            "endcard_ms": endcard_ms,
        },
        "video": video or {},
        "cost_estimate": cost,
    }
