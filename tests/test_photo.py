from __future__ import annotations

import base64
import json

import httpx
import pytest

from md2short.photo_engine import (
    _SAFE_FALLBACK_PROMPT,
    OPENAI_IMAGES_URL,
    _apply_keyword_focus,
    _sanitise_prompt,
    extract_visual_focus,
)
from md2short.pipeline import run_job
from md2short.schema import JobConfig
from md2short.script_engine import OPENAI_RESPONSES_URL

PNG = base64.b64encode(b"\x89PNG fake").decode()
BLOCKED = httpx.Response(400, json={"error": {"code": "moderation_blocked", "message": "blocked"}})


def _prompts_response(n: int) -> httpx.Response:
    text = json.dumps({"prompts": [{"index": i, "prompt": f"A trading screen showing Donald Trump scene {i}"} for i in range(n)]})
    return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]})


def _script_response() -> httpx.Response:
    text = json.dumps({"hook": "코스피가 올랐습니다.", "body": "트럼프가 합의를 했다.", "cta": "끝."}, ensure_ascii=False)
    return httpx.Response(200, json={"output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]})


@pytest.fixture
def photo_apis(mock_apis):
    """Responses API: 1st call = script, later calls = image prompts."""
    route = mock_apis.post(OPENAI_RESPONSES_URL)
    route.side_effect = [_script_response()] + [_prompts_response(8)] * 5
    return mock_apis


def _run(runtime, sample_md, tmp_path, events=None):
    if events is not None:
        runtime.on_stage = lambda name, info: events.append(name)
    return run_job(sample_md, JobConfig(visual_mode="photo"), elevenlabs_api_key="e", openai_api_key="o",
                   jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)


def test_visual_focus_and_keyword_prefix():
    subject, keywords = extract_visual_focus("트럼프가 합의를 했다")
    assert subject == "Donald Trump" and "diplomatic agreement table" in keywords
    assert _apply_keyword_focus("A table with flags", subject).startswith("Primary visual subject: Donald Trump.")
    assert _apply_keyword_focus("Donald Trump at a table", subject) == "Donald Trump at a table"


def test_sanitise_removes_names_brands_and_conflict_words():
    out = _sanitise_prompt("Primary visual subject: Donald Trump. NVIDIA chips near Iran missile strike")
    for banned in ("Donald Trump", "NVIDIA", "Iran", "missile", "Primary visual subject"):
        assert banned not in out


def test_photo_success_writes_photo_cues(photo_apis, runtime, sample_md, tmp_path):
    images = photo_apis.post(OPENAI_IMAGES_URL).mock(return_value=httpx.Response(200, json={"data": [{"b64_json": PNG}]}))
    events: list[str] = []
    result = _run(runtime, sample_md, tmp_path, events)
    edit = result.job_dir / "edit"
    records = json.loads((edit / "photo_cues.json").read_text())
    props = json.loads((edit / "props.json").read_text())
    assert images.call_count == len(records) > 0
    assert all(r["stage"] == "original" for r in records)
    assert all(c["assetKind"] == "photo" and c["visualMode"] == "photo" for c in props["emoticonCues"])
    first = props["emoticonCues"][0]["emoticonFileName"]
    assert (runtime.remotion_dir / "public" / first).is_file()
    assert not (edit / "emoticon_cues.json").exists()
    assert {"photo_generating", "photos_generated"} <= set(events)


def test_sanitised_stage_used_when_original_blocked(photo_apis, runtime, sample_md, tmp_path):
    sent: list[str] = []

    def image(request):
        prompt = json.loads(request.content)["prompt"]
        sent.append(prompt)
        return BLOCKED if "Donald Trump" in prompt else httpx.Response(200, json={"data": [{"b64_json": PNG}]})

    photo_apis.post(OPENAI_IMAGES_URL).mock(side_effect=image)
    result = _run(runtime, sample_md, tmp_path)
    records = json.loads((result.job_dir / "edit/photo_cues.json").read_text())
    assert {r["stage"] for r in records} == {"sanitised"}
    assert not (result.job_dir / "logs/photo_fallback.json").exists()


def test_all_stages_blocked_falls_back_to_emoticon(photo_apis, runtime, sample_md, tmp_path):
    images = photo_apis.post(OPENAI_IMAGES_URL).mock(return_value=BLOCKED)
    events: list[str] = []
    result = _run(runtime, sample_md, tmp_path, events)
    job = result.job_dir
    assert result.status == "qc_passed"
    fallback = json.loads((job / "logs/photo_fallback.json").read_text())
    assert fallback["to"] == "emoticon" and "PhotoEngineError" in fallback["reason"]
    sent_prompts = [json.loads(c.request.content)["prompt"] for c in images.calls]
    assert _SAFE_FALLBACK_PROMPT in sent_prompts
    props = json.loads((job / "edit/props.json").read_text())
    assert all(c["assetKind"] == "emoticon" for c in props["emoticonCues"])
    assert (job / "edit/emoticon_cues.json").exists() and not (job / "edit/photo_cues.json").exists()
    assert "photo_fallback" in events
    history = [h["status"] for h in json.loads((job / "status.json").read_text())["history"]]
    assert history == ["created", "script_generated", "voice_generated", "transcribed", "subtitled",
                       "final_rendered", "qc_passed"]


def test_progress_events_never_written_to_status(photo_apis, runtime, sample_md, tmp_path):
    photo_apis.post(OPENAI_IMAGES_URL).mock(return_value=httpx.Response(200, json={"data": [{"b64_json": PNG}]}))
    result = _run(runtime, sample_md, tmp_path)
    raw = (result.job_dir / "status.json").read_text()
    for event in ("photo_generating", "photos_generated", "photo_fallback"):
        assert event not in raw


def test_cache_hit_skips_second_image_call(photo_apis, runtime, sample_md, tmp_path):
    images = photo_apis.post(OPENAI_IMAGES_URL).mock(return_value=httpx.Response(200, json={"data": [{"b64_json": PNG}]}))
    first = _run(runtime, sample_md, tmp_path)
    calls_after_first = images.call_count
    photo_apis.post(OPENAI_RESPONSES_URL).side_effect = [_script_response(), _prompts_response(8)]
    second = _run(runtime, sample_md, tmp_path)
    assert images.call_count == calls_after_first  # 같은 prompt → 캐시 재사용
    records = json.loads((second.job_dir / "edit/photo_cues.json").read_text())
    assert all(r["cached"] for r in records)
    assert first.job_id != second.job_id


def test_storyboard_image_prompts_skip_prompt_llm(mock_apis, runtime, tmp_path):
    from .conftest import ROOT

    md = tmp_path / "sb.md"
    md.write_text((ROOT / "samples/storyboard.md").read_text(encoding="utf-8"), encoding="utf-8")
    responses = mock_apis.post(OPENAI_RESPONSES_URL)
    images = mock_apis.post(OPENAI_IMAGES_URL).mock(return_value=httpx.Response(200, json={"data": [{"b64_json": PNG}]}))
    runtime.probe_audio_ms = lambda _p: 5600
    result = run_job(md, JobConfig(visual_mode="photo"), elevenlabs_api_key="e", openai_api_key="o",
                     jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)
    assert not responses.called  # 스토리보드 대본 + 이미지 프롬프트 모두 원문 사용
    assert images.called
    records = json.loads((result.job_dir / "edit/photo_cues.json").read_text())
    assert "oil barrels" in records[0]["prompt"]
