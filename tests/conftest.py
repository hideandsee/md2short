from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from md2short.pipeline import Runtime
from md2short.render import VideoInfo
from md2short.script_engine import OPENAI_RESPONSES_URL
from md2short.transcript import ELEVENLABS_STT_URL

ROOT = Path(__file__).resolve().parents[1]
FAKE_MP3 = b"ID3fake-mp3-bytes"

SAMPLE_MD = """# 마켓 브리핑

- 코스피는 0.9% 오른 2,710포인트에 마감했다.
- 반도체 업종 지수는 3.5% 급등했다.
"""


def scribe_payload(tokens: list[tuple[str, float, float]], *, with_spacing: bool = True) -> dict:
    words: list[dict] = []
    for i, (text, start, end) in enumerate(tokens):
        if with_spacing and i:
            words.append({"text": " ", "start": tokens[i - 1][2], "end": start, "type": "spacing"})
        words.append({"text": text, "start": start, "end": end, "type": "word"})
    words.append({"text": "(웃음)", "start": tokens[-1][2], "end": tokens[-1][2] + 0.1, "type": "audio_event"})
    return {"language_code": "kor", "text": " ".join(t for t, _, _ in tokens), "words": words}


SCRIBE_TOKENS = [
    ("10월", 0.0, 0.3),
    ("26일", 0.32, 0.6),
    ("데이브리핑입니다.", 0.62, 1.4),
    ("코스피는", 1.5, 1.9),
    ("0.9%", 1.92, 2.3),
    ("오른", 2.32, 2.5),
    ("2,710포인트에", 2.52, 3.1),
    ("마감했다.", 3.12, 3.6),
    ("반도체", 3.7, 4.0),
    ("업종", 4.02, 4.2),
    ("지수는", 4.22, 4.5),
    ("3.5%", 4.52, 4.9),
    ("급등했다.", 4.92, 5.5),
]
AUDIO_MS = 5600


def openai_payload(hook: str, body: str, cta: str = "구독 부탁드립니다.") -> dict:
    text = json.dumps({"hook": hook, "body": body, "cta": cta}, ensure_ascii=False)
    return {"id": "resp_1", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


@pytest.fixture
def mock_apis():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.post(OPENAI_RESPONSES_URL).mock(
            return_value=httpx.Response(
                200, json=openai_payload("코스피가 올랐습니다.", "코스피는 0.9% 오른 2,710포인트에 마감했고 반도체 업종 지수는 3.5% 급등했습니다.")
            )
        )
        router.post(url__regex=r"https://api\.elevenlabs\.io/v1/text-to-speech/.*").mock(
            return_value=httpx.Response(200, content=FAKE_MP3, headers={"request-id": "req-tts-1"})
        )
        router.post(ELEVENLABS_STT_URL).mock(return_value=httpx.Response(200, json=scribe_payload(SCRIBE_TOKENS)))
        yield router


def fake_renderer(**kwargs) -> Path:
    job_dir: Path = kwargs["job_dir"]
    (job_dir / "edit" / "props.json").write_text(kwargs["props"].model_dump_json(by_alias=True), encoding="utf-8")
    (job_dir / "logs" / "remotion.log").write_text("fake render\n", encoding="utf-8")
    out = job_dir / "edit" / "final.mp4"
    out.write_bytes(b"fake-mp4")
    return out


@pytest.fixture
def runtime(tmp_path) -> Runtime:
    cleaned: list[str] = []
    rt = Runtime(
        project_root=tmp_path / "project",
        remotion_dir=tmp_path / "project" / "remotion",
        emoticon_dir=ROOT / "emoticon",
        preflight=lambda _dir: None,
        probe_audio_ms=lambda _p: AUDIO_MS,
        probe_video=lambda _p: VideoInfo(width=1080, height=1920, fps=30.0, duration_ms=AUDIO_MS + 10),
        renderer=fake_renderer,
        cleanup_staging=lambda _d, job_id: cleaned.append(job_id),
        today=lambda: date(2026, 10, 26),
    )
    rt.cleaned = cleaned  # type: ignore[attr-defined]
    return rt


@pytest.fixture
def sample_md(tmp_path) -> Path:
    path = tmp_path / "sample.md"
    path.write_text(SAMPLE_MD, encoding="utf-8")
    return path
