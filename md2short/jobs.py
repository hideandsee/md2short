"""Job ID와 산출물 디렉터리 규약 (docs/architecture.md §3.2, §4.4)."""

from __future__ import annotations

import secrets
from datetime import date
from pathlib import Path

JOB_SUBDIRS = ("inputs", "audio", "transcripts", "edit", "logs", "thumbs")


def new_job_id(today: date | None = None) -> str:
    d = today or date.today()
    return f"sf_{d:%Y%m%d}_{secrets.token_hex(3)}"


def create_job_dir(jobs_root: Path, job_id: str) -> Path:
    job_dir = jobs_root / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    for sub in JOB_SUBDIRS:
        (job_dir / sub).mkdir()
    return job_dir
