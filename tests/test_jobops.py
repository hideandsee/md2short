from __future__ import annotations

import json
import os
import time

import pytest

from md2short import cli
from md2short.jobops import clean_jobs, format_status, parse_age
from md2short.pipeline import run_job
from md2short.schema import JobConfig


@pytest.mark.parametrize("value,seconds", [("90", 90), ("30s", 30), ("15m", 900), ("24h", 86400), ("7d", 604800)])
def test_parse_age(value, seconds):
    assert parse_age(value) == seconds


@pytest.mark.parametrize("value", ["", "1w", "-5m", "h", "abc"])
def test_parse_age_rejects(value):
    with pytest.raises(ValueError):
        parse_age(value)


def _make_jobs(root, ages_h: dict[str, float], now: float):
    for name, hours in ages_h.items():
        d = root / name
        d.mkdir(parents=True)
        (d / "status.json").write_text("{}")
        os.utime(d, (now - hours * 3600, now - hours * 3600))


def test_clean_dry_run_and_real(tmp_path):
    now = time.time()
    root = tmp_path / "jobs"
    _make_jobs(root, {"sf_20260101_aaaaaa": 48, "sf_20260102_bbbbbb": 1}, now)
    (root / ".photo_cache").mkdir()
    remotion = tmp_path / "remotion"
    (remotion / "public" / "jobs" / "sf_20260101_aaaaaa").mkdir(parents=True)

    dry = clean_jobs(root, 24 * 3600, dry_run=True, now=now, remotion_dir=remotion)
    assert [p.name for p in dry] == ["sf_20260101_aaaaaa"]
    assert (root / "sf_20260101_aaaaaa").exists()

    real = clean_jobs(root, 24 * 3600, dry_run=False, now=now, remotion_dir=remotion)
    assert [p.name for p in real] == ["sf_20260101_aaaaaa"]
    assert not (root / "sf_20260101_aaaaaa").exists()
    assert (root / "sf_20260102_bbbbbb").exists() and (root / ".photo_cache").exists()
    assert not (remotion / "public" / "jobs" / "sf_20260101_aaaaaa").exists()


def test_status_output_after_run(mock_apis, runtime, sample_md, tmp_path):
    result = run_job(sample_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
                     jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)
    text = format_status(result.job_dir)
    assert f"job_id: {result.job_id}" in text
    assert "status: qc_passed" in text
    assert "[PASS] sync_last_word_vs_audio" in text and "[PASS] final_mp4_vs_audio" in text
    assert "cost (USD est.): total" in text


def test_cli_status_and_clean(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "load_dotenv", lambda *_a, **_k: None)
    job = tmp_path / "sf_20260101_cccccc"
    job.mkdir()
    (job / "status.json").write_text(json.dumps({"job_id": job.name, "status": "failed", "error": "boom"}))
    assert cli.main(["status", job.name, "--jobs-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "status: failed" in out and "error: boom" in out
    assert cli.main(["status", "sf_20990101_000000", "--jobs-root", str(tmp_path)]) == 1
    assert cli.main(["clean", "--older-than", "1w", "--jobs-root", str(tmp_path)]) == 1
    assert cli.main(["clean", "--older-than", "0s", "--dry-run", "--jobs-root", str(tmp_path)]) == 0
    assert job.exists()
