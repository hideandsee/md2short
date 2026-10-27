"""파일 기반 Job 상태 머신 (docs/architecture.md §3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUSES = (
    "created",
    "script_generated",
    "voice_generated",
    "transcribed",
    "subtitled",
    "final_rendered",
    "qc_passed",
    "qc_failed",
    "failed",
)
TERMINAL = frozenset({"qc_passed", "qc_failed", "failed"})
PROGRESS_EVENTS = frozenset({"photo_generating", "photos_generated", "photo_fallback"})

_FORWARD: dict[str | None, frozenset[str]] = {
    None: frozenset({"created"}),
    "created": frozenset({"script_generated"}),
    "script_generated": frozenset({"voice_generated"}),
    "voice_generated": frozenset({"transcribed"}),
    "transcribed": frozenset({"subtitled"}),
    "subtitled": frozenset({"final_rendered"}),
    "final_rendered": frozenset({"qc_passed", "qc_failed"}),
}


def validate_transition(current: str | None, new: str) -> None:
    if new in PROGRESS_EVENTS:
        raise ValueError(f"{new!r} is a progress event, not a status")
    if new not in STATUSES:
        raise ValueError(f"unknown status {new!r}")
    if current in TERMINAL:
        raise ValueError(f"job already terminal ({current!r}); cannot move to {new!r}")
    if new == "failed" and current is not None:
        return
    if new not in _FORWARD.get(current, frozenset()):
        raise ValueError(f"illegal transition {current!r} -> {new!r}")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def read_status(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "status.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(job_dir: Path, new: str, **fields: Any) -> dict[str, Any]:
    """전이를 검증하고 `status.json`에 병합 기록한다."""
    data = read_status(job_dir)
    validate_transition(data.get("status"), new)
    history = data.setdefault("history", [])
    now = _now()
    history.append({"status": new, "at": now})
    data.update(fields)
    data["status"] = new
    data.setdefault("started_at", now)
    data["updated_at"] = now
    (job_dir / "status.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
