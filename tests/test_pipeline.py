from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import httpx
import pytest
import respx

from md2short import qc
from md2short._retry import BACKOFF_SECONDS, ExternalAPIError, post_with_retry
from md2short.caption_plan import build_caption_segments
from md2short.opening import find_opening_window
from md2short.pipeline import run_job
from md2short.schema import JobConfig, Word
from md2short.script import fallback_extract
from md2short.script_engine import OPENAI_RESPONSES_URL, _looks_korean, generate_script
from md2short.transcript import normalize_scribe
from md2short.tts_text import prepare_tts_text

from .conftest import AUDIO_MS, ROOT, SCRIBE_TOKENS, openai_payload, scribe_payload

URL = "https://api.example.test/x"


# --- retry -----------------------------------------------------------------------


def _retry_call(router, *responses):
    router.post(URL).mock(side_effect=list(responses))
    sleeps: list[float] = []
    with httpx.Client() as client:
        try:
            return post_with_retry(client, URL, timeout=5, sleep=sleeps.append), sleeps
        except ExternalAPIError as exc:
            return exc, sleeps


@respx.mock(assert_all_mocked=True)
def test_retry_recovers_after_429_and_5xx(respx_mock):
    resp, sleeps = _retry_call(respx_mock, httpx.Response(429), httpx.Response(503), httpx.Response(200, text="ok"))
    assert resp.text == "ok"
    assert sleeps == [0.5, 1.0]


@respx.mock(assert_all_mocked=True)
def test_retry_gives_up_after_three_retries_with_backoff(respx_mock):
    err, sleeps = _retry_call(respx_mock, *[httpx.Response(500)] * 4)
    assert isinstance(err, ExternalAPIError) and err.status_code == 500
    assert sleeps == list(BACKOFF_SECONDS)
    assert respx_mock.calls.call_count == 4


@respx.mock(assert_all_mocked=True)
def test_retry_on_timeout_then_success(respx_mock):
    resp, sleeps = _retry_call(respx_mock, httpx.ReadTimeout("slow"), httpx.Response(200, text="ok"))
    assert resp.text == "ok" and sleeps == [0.5]


@respx.mock(assert_all_mocked=True)
def test_retry_does_not_retry_client_errors(respx_mock):
    err, sleeps = _retry_call(respx_mock, httpx.Response(401, text="bad key"))
    assert isinstance(err, ExternalAPIError) and err.status_code == 401
    assert sleeps == [] and respx_mock.calls.call_count == 1


# --- script ----------------------------------------------------------------------


def test_fallback_extract_strips_markdown():
    md = "# 제목\n\n> 인용\n\n- **코스피**는 [상승](http://x)했다\n- 환율 하락.\n\n```\ncode\n```\n"
    assert fallback_extract(md) == "코스피는 상승했다. 환율 하락."


@pytest.mark.parametrize(
    "text,ok",
    [
        ("코스피는 0.9% 올랐고 S&P 500은 1.2% 상승했습니다.", True),
        ("The market rallied strongly today across all sectors.", False),
        ("오늘 시장은 上昇 했습니다.", False),
        ("今日は株価が上がりました。", False),
        ("", False),
    ],
)
def test_looks_korean(text, ok):
    assert _looks_korean(text) is ok


@respx.mock(assert_all_mocked=True)
def test_openai_500_falls_back_and_logs(respx_mock, tmp_path, monkeypatch):
    monkeypatch.setattr("md2short._retry.time.sleep", lambda _s: None)
    respx_mock.post(OPENAI_RESPONSES_URL).mock(return_value=httpx.Response(500))
    with httpx.Client() as client:
        result = generate_script("- 코스피 상승.", api_key="k", model="gpt-5-mini", client=client, log_dir=tmp_path)
    assert result.plan["engine"] == "fallback_extract"
    assert "ExternalAPIError" in result.plan["fallback_reason"]
    assert json.loads((tmp_path / "fallback.json").read_text())["engine"] == "fallback_extract"


@respx.mock(assert_all_mocked=True)
def test_openai_foreign_output_is_rejected(respx_mock, tmp_path):
    respx_mock.post(OPENAI_RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=openai_payload("Stocks rose today in New York.", "The index gained a lot of points."))
    )
    with httpx.Client() as client:
        result = generate_script("- 코스피 상승.", api_key="k", model="m", client=client, log_dir=tmp_path)
    assert result.plan == {"engine": "fallback_extract", "fallback_reason": "non_korean_output"}
    assert (tmp_path / "openai_script_raw.json").exists()


@respx.mock(assert_all_mocked=True)
def test_openai_request_wraps_user_content_and_uses_schema(respx_mock, tmp_path):
    route = respx_mock.post(OPENAI_RESPONSES_URL).mock(
        return_value=httpx.Response(200, json=openai_payload("코스피가 올랐습니다.", "자세히 보겠습니다."))
    )
    with httpx.Client() as client:
        result = generate_script("본문", api_key="k", model="gpt-5-mini", client=client, log_dir=tmp_path, opening="오프닝.")
    sent = json.loads(route.calls.last.request.content)
    assert sent["input"][1]["content"] == "<user_content>\n본문\n</user_content>"
    assert sent["text"]["format"]["type"] == "json_schema"
    assert result.full_text == "오프닝. 코스피가 올랐습니다. 자세히 보겠습니다."
    assert result.plan["engine"] == "openai"


def test_no_key_uses_fallback_without_fallback_log(tmp_path):
    with httpx.Client() as client:
        result = generate_script("- 코스피 상승.", api_key=None, model="m", client=client, log_dir=tmp_path)
    assert result.plan["engine"] == "fallback_extract"
    assert not (tmp_path / "fallback.json").exists()


def test_tts_text_normalizes_pronunciation_only():
    assert prepare_tts_text("S&P 500이 1.2% 올랐다… (잠정)") == "에스앤피 오백이 1.2퍼센트 올랐다. 잠정"


# --- transcript / captions / opening ---------------------------------------------


def test_scribe_normalization_keeps_only_words_and_int_ms():
    doc = normalize_scribe(scribe_payload([("안녕", 0.0004, 0.2995), ("하세요.", 0.3, 0.8)]), audio_duration_ms=900)
    assert [w.model_dump() for w in doc.words] == [
        {"text": "안녕", "start": 0, "end": 300},
        {"text": "하세요.", "start": 300, "end": 800},
    ]
    assert doc.audio_duration_ms == 900


def _words(spec: list[tuple[str, int, int]]) -> list[Word]:
    return [Word(text=t, start=s, end=e) for t, s, e in spec]


def test_caption_boundaries_punctuation_gap_and_chunk_cap():
    words = _words(
        [("가", 0, 100), ("나.", 110, 200), ("다", 210, 300), ("라", 900, 1000), ("마", 1010, 1100), ("바", 1110, 1200)]
    )
    segs = build_caption_segments(words, chunk_size=2)
    assert [(s.word_start, s.word_end) for s in segs] == [(0, 2), (2, 3), (3, 5), (5, 6)]
    assert segs[0].end_ms == 210  # next starts within 600ms → hold until it
    assert segs[1].end_ms == 300  # gap 600ms → end at last word
    assert segs[0].start_frame == 0 and segs[1].start_frame == 6
    assert segs[0].words[1].end_frame == 6


def test_opening_window_found_from_words():
    words = normalize_scribe(scribe_payload(SCRIBE_TOKENS), audio_duration_ms=AUDIO_MS).words
    window = find_opening_window(words)
    assert window.word_count == 3 and window.end_ms == 1500  # 다음 단어 시작까지 유지
    assert find_opening_window(words[3:]).word_count == 0


# --- QC ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "last_word,final,passed",
    [(9000, 10000, True), (8999, 10000, False), (11000, 10000, True), (11001, 10000, False),
     (10000, 10100, True), (10000, 10101, False), (10000, 9900, True), (10000, 9899, False)],
)
def test_qc_tolerance_boundaries(last_word, final, passed):
    report = qc.run_qc(audio_duration_ms=10000, last_word_end_ms=last_word, final_mp4_duration_ms=final, cost={})
    assert report["passed"] is passed


def test_cost_estimate_formula():
    cost = qc.estimate_cost(tts_chars=1000, audio_duration_ms=3_600_000, llm_input_chars=0, llm_output_chars=0)
    assert cost["elevenlabs_tts"] == pytest.approx(0.30)
    assert cost["elevenlabs_stt"] == pytest.approx(0.40)
    assert cost["total"] == pytest.approx(0.70)


# --- run_job ----------------------------------------------------------------------

REQUIRED_ARTIFACTS = {
    "created": ["status.json", "inputs/source.md"],
    "script_generated": ["inputs/source.md", "inputs/script.md", "inputs/script.json"],
    "voice_generated": ["audio/narration.mp3", "logs/tts_input.txt", "logs/tts_meta.json"],
    "transcribed": ["transcripts/words.json", "logs/scribe_raw.json"],
    "subtitled": ["edit/caption_segments.json", "edit/emoticon_cues.json", "edit/edl.json"],
    "final_rendered": ["edit/final.mp4", "edit/props.json", "logs/remotion.log"],
    "qc_passed": ["qc_report.json"],
}


def test_run_job_happy_path_statuses_and_artifacts(mock_apis, runtime, sample_md, tmp_path):
    out = tmp_path / "output" / "ret.mp4"
    result = run_job(
        sample_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
        jobs_root=tmp_path / "jobs", output_path=out, runtime=runtime,
    )
    assert result.status == "qc_passed"
    status = json.loads((result.job_dir / "status.json").read_text())
    assert [h["status"] for h in status["history"]] == [
        "created", "script_generated", "voice_generated", "transcribed", "subtitled", "final_rendered", "qc_passed"
    ]
    for files in REQUIRED_ARTIFACTS.values():
        for rel in files:
            assert (result.job_dir / rel).exists(), rel
    assert out.read_bytes() == b"fake-mp4"
    assert status["markdown_input"] == str(sample_md.resolve())
    assert status["script_chars"] > 0 and status["qc_passed"] is True
    assert runtime.cleaned == [result.job_id]

    words = json.loads((result.job_dir / "transcripts/words.json").read_text())
    assert all(set(w) == {"text", "start", "end"} for w in words["words"])
    assert all(isinstance(w["start"], int) for w in words["words"])
    assert len(words["words"]) == len(SCRIBE_TOKENS)

    segs = json.loads((result.job_dir / "edit/caption_segments.json").read_text())
    word_starts = {w["start"] for w in words["words"]}
    assert all(s["startMs"] in word_starts for s in segs)
    assert segs[0]["wordStart"] == 3  # opening words suppressed
    props = json.loads((result.job_dir / "edit/props.json").read_text())
    assert props["openingDurationMs"] == 1500
    assert props["openingDurationFrames"] == props["captionSegments"][0]["startFrame"]  # 오프닝↔첫 자막 사이 빈 화면 없음
    assert props["openingText"] == "2026년 10월 26일\n타이거살구브리핑"
    assert props["durationInFrames"] == 168 + 90  # 오디오 168프레임 + 면책 엔드카드 90프레임
    assert props["headerLogo"] is None

    tts_meta = json.loads((result.job_dir / "logs/tts_meta.json").read_text())
    assert tts_meta["headers"]["request-id"] == "req-tts-1"
    report = json.loads((result.job_dir / "qc_report.json").read_text())
    assert report["cost_estimate"]["total"] > 0


def test_run_job_without_output_copy(mock_apis, runtime, sample_md, tmp_path):
    result = run_job(
        sample_md, JobConfig(show_opening=False), elevenlabs_api_key="e", openai_api_key=None,
        jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime,
    )
    assert result.output_path is None
    script = json.loads((result.job_dir / "inputs/script.json").read_text())
    assert script["plan"]["engine"] == "fallback_extract" and script["opening"] == ""


def test_run_job_qc_failure_keeps_staging(mock_apis, runtime, sample_md, tmp_path):
    from md2short.render import VideoInfo

    runtime.probe_video = lambda _p: VideoInfo(width=1080, height=1920, fps=30.0, duration_ms=AUDIO_MS + 500)
    result = run_job(
        sample_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
        jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime,
    )
    assert result.status == "qc_failed"
    assert runtime.cleaned == []


def test_run_job_exception_writes_failed(mock_apis, runtime, sample_md, tmp_path):
    def boom(**_kw):
        raise RuntimeError("render exploded")

    runtime.renderer = boom
    with pytest.raises(RuntimeError):
        run_job(sample_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
                jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)
    job_dir = next((tmp_path / "jobs").iterdir())
    status = json.loads((job_dir / "status.json").read_text())
    assert status["status"] == "failed"
    assert "render exploded" in status["error"]
    assert status["history"][-2]["status"] == "subtitled"


# --- layer boundary ---------------------------------------------------------------


def test_no_ffmpeg_caption_burn_in_in_python():
    result = subprocess.run(
        ["grep", "-rEn", "subtitles=|overlay=|drawtext", str(ROOT / "md2short")], capture_output=True, text=True
    )
    assert result.stdout == ""


def test_only_timeutil_converts_ms_to_frames():
    offenders = []
    for path in (ROOT / "md2short").glob("*.py"):
        if path.name == "timeutil.py":
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\*\s*FPS|FPS\s*\*|/\s*1000\s*\*\s*30|\*\s*30\s*/\s*1000", line):
                offenders.append(f"{path.name}:{n}: {line.strip()}")
    assert offenders == []


def test_generated_files_exist():
    assert (Path(ROOT) / "remotion/src/generated/props.ts").exists()


def test_endcard_extends_duration_and_qc_expects_it():
    from md2short.edl import build_edl, build_props
    from md2short.qc import run_qc
    from md2short.schema import DISCLAIMER_TEXT, ENDCARD_DURATION_MS, JobConfig, WordsDoc
    from md2short.timeutil import ms_to_frames

    doc = WordsDoc(audio_duration_ms=10_000, text="a", words=[])
    edl = build_edl(job_id="j", words_doc=doc, caption_segments=[], emoticon_cues=[])
    on = build_props(edl, JobConfig(), staging_prefix="jobs/j", opening_text="", cta_text="", header_logo=None)
    off = build_props(edl, JobConfig(show_endcard=False), staging_prefix="jobs/j", opening_text="", cta_text="", header_logo=None)
    assert on.endcard_duration_frames == ms_to_frames(ENDCARD_DURATION_MS) == 90
    assert on.duration_in_frames == off.duration_in_frames + 90
    assert on.endcard_text == DISCLAIMER_TEXT["ko"] and off.endcard_text == "" and off.endcard_duration_frames == 0
    cost = {"total_usd": 0}
    kwargs = {"audio_duration_ms": 10_000, "last_word_end_ms": 10_000, "cost": cost}
    assert run_qc(final_mp4_duration_ms=13_000, endcard_ms=3000, **kwargs)["passed"]
    assert not run_qc(final_mp4_duration_ms=10_000, endcard_ms=3000, **kwargs)["passed"]
    assert run_qc(final_mp4_duration_ms=10_000, **kwargs)["passed"]
