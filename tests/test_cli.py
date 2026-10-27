from __future__ import annotations

import pytest

from md2short import cli
from md2short.pipeline import JobResult


@pytest.fixture
def env_keys(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "e")
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setattr(cli, "load_dotenv", lambda *_a, **_k: None)


@pytest.fixture
def captured(monkeypatch, tmp_path):
    calls: list[dict] = []

    def fake_run_job(markdown, cfg, **kwargs):
        calls.append({"cfg": cfg, **kwargs})
        return JobResult(job_id="sf_20260101_abcdef", job_dir=tmp_path, status="qc_passed", output_path=kwargs["output_path"])

    monkeypatch.setattr("md2short.pipeline.run_job", fake_run_job)
    return calls


@pytest.fixture
def md(tmp_path):
    path = tmp_path / "a.md"
    path.write_text("- 코스피 상승.", encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    "extra",
    [
        ["--lang", "en"],
        ["--chunk-size", "0"],
        ["--chunk-size", "25"],
        ["--speed", "0.69"],
        ["--speed", "1.21"],
        ["--engine", "ffmpeg"],
        ["--visual-mode", "video"],
        ["--bg", "#GGGGGG"],
        ["--chunk-size", "abc"],
    ],
)
def test_input_errors_exit_1(env_keys, captured, md, extra):
    assert cli.main(["run", md, *extra]) == 1
    assert captured == []


def test_missing_markdown_exits_1(env_keys, captured):
    assert cli.main(["run", "/nonexistent.md"]) == 1


def test_missing_elevenlabs_key_exits_1(env_keys, captured, md, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert cli.main(["run", md]) == 1


def test_photo_without_openai_key_exits_1(env_keys, captured, md, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    assert cli.main(["run", md, "--visual-mode", "photo"]) == 1
    assert cli.main(["run", md]) == 0  # emoticon mode works without OpenAI


def test_bg_normalized_and_output_disabled(env_keys, captured, md):
    assert cli.main(["run", md, "--bg", "#ffffff", "--output", ""]) == 0
    assert captured[0]["cfg"].bg_color == "#FFFFFF"
    assert captured[0]["output_path"] is None


def test_defaults_passed_to_pipeline(env_keys, captured, md):
    assert cli.main(["run", md]) == 0
    cfg = captured[0]["cfg"]
    assert cfg.show_opening is True and cfg.show_outro is False and cfg.visual_mode == "emoticon"
    assert str(captured[0]["output_path"]) == "output/ret.mp4"


def test_run_exception_exits_2(env_keys, md, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("api down")

    monkeypatch.setattr("md2short.pipeline.run_job", boom)
    assert cli.main(["run", md]) == 2


def test_qc_failed_exits_2(env_keys, md, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "md2short.pipeline.run_job",
        lambda *_a, **_k: JobResult(job_id="x", job_dir=tmp_path, status="qc_failed"),
    )
    assert cli.main(["run", md]) == 2
