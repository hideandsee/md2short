"""`status` / `clean` 명령 구현 (docs/architecture.md §6.2, §6.3)."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from md2short.render import staging_dir

_AGE_RE = re.compile(r"^(\d+(?:\.\d+)?)([smhd]?)$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}
_JOB_DIR_RE = re.compile(r"^sf_\d{8}_[0-9a-f]{6}$")
REMOTION_DIR = Path(__file__).resolve().parents[1] / "remotion"


def parse_age(value: str) -> float:
    m = _AGE_RE.match(value.strip())
    if not m:
        raise ValueError(f"invalid --older-than {value!r}: use seconds or a s/m/h/d suffix (e.g. 24h)")
    return float(m.group(1)) * _UNIT_SECONDS[m.group(2)]


def clean_jobs(
    jobs_root: Path, older_than_s: float, *, dry_run: bool, now: float | None = None, remotion_dir: Path = REMOTION_DIR
) -> list[Path]:
    if not jobs_root.is_dir():
        return []
    cutoff = (now if now is not None else time.time()) - older_than_s
    removed: list[Path] = []
    for job_dir in sorted(jobs_root.iterdir()):
        if not job_dir.is_dir() or not _JOB_DIR_RE.match(job_dir.name):
            continue
        if job_dir.stat().st_mtime >= cutoff:
            continue
        removed.append(job_dir)
        if not dry_run:
            shutil.rmtree(job_dir)
            shutil.rmtree(staging_dir(remotion_dir, job_dir.name), ignore_errors=True)
    return removed


def format_status(job_dir: Path) -> str:
    data = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    lines = [f"{key}: {data.get(key)}" for key in ("job_id", "status", "started_at", "updated_at", "markdown_input")]
    if data.get("error"):
        lines.append(f"error: {data['error']}")
    cfg = data.get("config") or {}
    if cfg:
        lines.append(f"visual_mode: {cfg.get('visual_mode')}  voice_id: {cfg.get('voice_id')}")
    qc_path = job_dir / "qc_report.json"
    if qc_path.is_file():
        report = json.loads(qc_path.read_text(encoding="utf-8"))
        lines.append(f"qc: {'PASS' if report.get('passed') else 'FAIL'}")
        for check in report.get("checks", []):
            mark = "PASS" if check["passed"] else "FAIL"
            lines.append(f"  [{mark}] {check['name']}: delta {check['delta_ms']}ms (±{check['tolerance_ms']}ms)")
        cost = report.get("cost_estimate") or {}
        if cost:
            lines.append(
                f"cost (USD est.): total {cost.get('total')} = tts {cost.get('elevenlabs_tts')}"
                f" + stt {cost.get('elevenlabs_stt')} + openai {cost.get('openai_text')}"
            )
    return "\n".join(lines)
