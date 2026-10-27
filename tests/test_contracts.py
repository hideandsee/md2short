import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from md2short import jobs, state
from md2short.schema import (
    DEFAULT_VOICES,
    CaptionSegment,
    FramedWord,
    JobConfig,
    RemotionProps,
    Word,
    normalize_bg_color,
)
from md2short.timeutil import frames_to_ms, ms_to_frames

ROOT = Path(__file__).resolve().parents[1]


def test_job_config_defaults_match_architecture_4_1():
    cfg = JobConfig()
    assert cfg.platform == "youtube_shorts"
    assert cfg.language == "ko"
    assert cfg.voice_id == "v1jVu1Ky28piIPEJqRrm"
    assert cfg.voice_speed == 1.0
    assert cfg.template_id == "tech_explainer"
    assert cfg.bg_color == "0xFFFFFF"
    assert cfg.chunk_size == 14
    assert cfg.engine == "remotion"
    assert cfg.visual_mode == "emoticon"
    assert cfg.show_opening is True
    assert cfg.show_outro is False
    assert DEFAULT_VOICES == {"ko": "v1jVu1Ky28piIPEJqRrm"}


@pytest.mark.parametrize(
    "field,value",
    [("language", "en"), ("chunk_size", 0), ("chunk_size", 25), ("voice_speed", 0.69), ("engine", "ffmpeg")],
)
def test_job_config_rejects_out_of_contract_values(field, value):
    with pytest.raises(ValidationError):
        JobConfig(**{field: value})


def test_word_is_ms_only_and_framed_word_adds_frames():
    assert set(Word.model_fields) == {"text", "start", "end"}
    assert {"start_frame", "end_frame"} <= set(FramedWord.model_fields)


def test_props_require_caption_segments_and_allow_null_header_logo():
    with pytest.raises(ValidationError):
        RemotionProps(audio_file_name="a", words_file_name="w", bg_color="#FFFFFF", chunk_size=14, duration_in_frames=30)
    props = RemotionProps(
        audio_file_name="a",
        words_file_name="w",
        bg_color="#FFFFFF",
        chunk_size=14,
        caption_segments=[],
        duration_in_frames=30,
    )
    dumped = props.model_dump(by_alias=True)
    assert dumped["headerLogo"] is None
    assert dumped["captionSegments"] == []
    assert RemotionProps.model_validate(json.loads(json.dumps(dumped))) == props


def test_caption_segment_round_trip_uses_camel_case():
    seg = CaptionSegment(
        index=0, text="안녕", start_ms=0, end_ms=500, start_frame=0, end_frame=15, word_start=0, word_end=1
    )
    dumped = seg.model_dump(by_alias=True)
    assert "startFrame" in dumped and "wordEnd" in dumped
    assert CaptionSegment.model_validate(dumped) == seg


@pytest.mark.parametrize("ms,frames", [(0, 0), (16, 0), (17, 1), (33, 1), (150, 5), (1000, 30), (30000, 900)])
def test_ms_to_frames_integer_half_up(ms, frames):
    assert ms_to_frames(ms) == frames


def test_frames_to_ms_round_trips_within_one_frame():
    for frames in range(0, 200):
        assert ms_to_frames(frames_to_ms(frames)) == frames


@pytest.mark.parametrize(
    "value,expected", [("0xFFFFFF", "#FFFFFF"), ("#ffffff", "#FFFFFF"), ("1a2B3c", "#1A2B3C")]
)
def test_normalize_bg_color(value, expected):
    assert normalize_bg_color(value) == expected


def test_normalize_bg_color_rejects_garbage():
    with pytest.raises(ValueError):
        normalize_bg_color("#GGGGGG")


HAPPY_PATH = [
    "created",
    "script_generated",
    "voice_generated",
    "transcribed",
    "subtitled",
    "final_rendered",
]


def test_state_happy_path_and_both_qc_terminals():
    current = None
    for nxt in HAPPY_PATH:
        state.validate_transition(current, nxt)
        current = nxt
    state.validate_transition("final_rendered", "qc_passed")
    state.validate_transition("final_rendered", "qc_failed")


@pytest.mark.parametrize("current", HAPPY_PATH)
def test_any_non_terminal_can_fail(current):
    state.validate_transition(current, "failed")


@pytest.mark.parametrize(
    "current,new",
    [
        (None, "script_generated"),
        ("created", "voice_generated"),
        ("transcribed", "final_rendered"),
        ("subtitled", "qc_passed"),
        ("qc_passed", "failed"),
        ("failed", "created"),
        ("qc_failed", "qc_passed"),
        ("transcribed", "photo_generating"),
        ("created", "bogus"),
    ],
)
def test_illegal_transitions_raise(current, new):
    with pytest.raises(ValueError):
        state.validate_transition(current, new)


def test_write_status_merges_fields_and_history(tmp_path):
    state.write_status(tmp_path, "created", job_id="sf_20260101_abcdef", markdown_input="/x.md")
    data = state.write_status(tmp_path, "script_generated", script_chars=12)
    assert data["status"] == "script_generated"
    assert data["markdown_input"] == "/x.md"
    assert data["script_chars"] == 12
    assert [h["status"] for h in data["history"]] == ["created", "script_generated"]
    with pytest.raises(ValueError):
        state.write_status(tmp_path, "qc_passed")


def test_job_id_format_and_dirs(tmp_path):
    job_id = jobs.new_job_id(date(2026, 5, 2))
    assert re.fullmatch(r"sf_20260502_[0-9a-f]{6}", job_id)
    job_dir = jobs.create_job_dir(tmp_path, job_id)
    for sub in ("inputs", "audio", "transcripts", "edit", "logs", "thumbs"):
        assert (job_dir / sub).is_dir()


@pytest.mark.skipif(shutil.which("pnpm") is None, reason="pnpm not installed")
def test_generated_ts_types_are_up_to_date(tmp_path):
    subprocess.run([str(ROOT / "scripts" / "gen_types.sh"), str(tmp_path)], check=True, cwd=ROOT, timeout=120)
    committed = ROOT / "remotion" / "src" / "generated"
    for name in ("props.schema.json", "props.ts"):
        assert (tmp_path / name).read_text() == (committed / name).read_text(), f"{name} is stale; run scripts/gen_types.sh"
