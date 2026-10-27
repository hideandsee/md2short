"""실제 E2E 1회 실행 직후 증거를 .omc/state/e2e-evidence.json에 누적한다 (AC-11).

usage: uv run python scripts/e2e_evidence.py <label> <job_id> [output_mp4]
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from md2short.render import get_video_info

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / ".omc" / "state" / "e2e-evidence.json"


def main(label: str, job_id: str, output: str = "output/ret.mp4") -> dict:
    job_dir = ROOT / "jobs" / job_id
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    report = json.loads((job_dir / "qc_report.json").read_text(encoding="utf-8"))
    mp4 = ROOT / output
    info = get_video_info(mp4)
    entry = {
        "label": label,
        "job_id": job_id,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": status["status"],
        "script_engine": report.get("script_engine"),
        "qc_checks": report["checks"],
        "cost_estimate": report.get("cost_estimate"),
        "output": output,
        "ffprobe": {"width": info.width, "height": info.height, "fps": info.fps, "duration_ms": info.duration_ms},
        "sha256": hashlib.sha256(mp4.read_bytes()).hexdigest(),
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(EVIDENCE.read_text()) if EVIDENCE.exists() else []
    data.append(entry)
    EVIDENCE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:]), ensure_ascii=False, indent=2))
