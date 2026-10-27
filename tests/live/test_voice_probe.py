from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = ROOT / "tests" / "fixtures" / "probe"


@pytest.mark.live
def test_voice_probe_records_fixtures():
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    if not os.environ.get("ELEVENLABS_API_KEY"):
        pytest.fail("ELEVENLABS_API_KEY missing: live tests need .env")
    spec = importlib.util.spec_from_file_location("voice_probe", ROOT / "scripts" / "voice_probe.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    summary = module.run(PROBE_DIR)
    for name in ("narration.mp3", "scribe_raw.json", "words.json"):
        assert (PROBE_DIR / name).is_file()
    words = json.loads((PROBE_DIR / "words.json").read_text())
    assert words["words"] and all(isinstance(w["start"], int) and set(w) == {"text", "start", "end"} for w in words["words"])
    assert words["audio_duration_ms"] == summary["audio_duration_ms"] > 0
