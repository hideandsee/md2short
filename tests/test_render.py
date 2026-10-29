from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from md2short import render
from md2short.caption_plan import build_caption_segments
from md2short.edl import build_edl, build_props
from md2short.emoticon_map import plan_cues
from md2short.schema import ENDCARD_DURATION_MS, JobConfig, Word, WordsDoc

from .conftest import ROOT

REMOTION_SRC = ROOT / "remotion" / "src"
TIME_MATH = re.compile(r"/\s*1000|\*\s*30\b|\bfps\s*\*|\*\s*fps\b|1000\s*/")
ALLOWLIST = {REMOTION_SRC / "generated"}
PROBE_DIR = ROOT / "tests" / "fixtures" / "probe"


def test_remotion_no_time_math():
    offenders = []
    for path in REMOTION_SRC.rglob("*.ts*"):
        if any(parent in ALLOWLIST for parent in path.parents):
            continue
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if TIME_MATH.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert offenders == []


def test_captions_component_has_no_segmentation_logic():
    src = (REMOTION_SRC / "Captions.tsx").read_text()
    assert "chunkBySentences" not in src
    assert not re.search(r"\.split\(|600", src)


def test_link_asset_dir_skips_missing_and_empty(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (tmp_path / "empty").mkdir()
    full = tmp_path / "full"
    full.mkdir()
    (full / "a.png").write_bytes(b"x")
    render._link_asset_dir(public, "missing", tmp_path / "nope")
    render._link_asset_dir(public, "empty", tmp_path / "empty")
    render._link_asset_dir(public, "full", full)
    assert not (public / "missing").exists() and not (public / "missing").is_symlink()
    assert not (public / "empty").exists()
    assert (public / "full" / "a.png").read_bytes() == b"x"
    # 이후 원본이 사라지면 dangling link를 남기지 않는다
    shutil.rmtree(full)
    render._link_asset_dir(public, "full", full)
    assert not (public / "full").is_symlink()


def test_stage_fonts_falls_back_to_noto(tmp_path):
    remotion_dir = ROOT / "remotion"
    if not (remotion_dir / "node_modules" / "@fontsource" / "noto-sans-kr").is_dir():
        pytest.skip("remotion/node_modules not installed")
    family = render.stage_fonts(tmp_path, tmp_path / "no-seoul-fonts", remotion_dir)
    assert family == "Noto Sans KR"
    for name in ("regular.woff2", "regular-latin.woff2", "bold.woff2", "bold-latin.woff2", "font.css"):
        assert (tmp_path / "font" / name).is_file()


def test_header_logo_path(tmp_path):
    assert render.header_logo_path(tmp_path) is None
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "header_logo.png").write_bytes(b"png")
    assert render.header_logo_path(tmp_path) == "img/header_logo.png"


def test_preflight_reports_missing_remotion(tmp_path):
    with pytest.raises(render.PreflightError):
        render.ensure_remotion_available(tmp_path)


SYNTHETIC_WORDS = ["코스피는", "0.9%", "올랐고", "반도체", "업종이", "급등했습니다.", "환율은", "하락했습니다."]


def _render_fixture(tmp_path: Path) -> tuple[WordsDoc, Path]:
    """실제 voice probe fixture가 있으면 그것을, 없으면 ffmpeg 사인파 + 합성 단어를 쓴다."""
    if (PROBE_DIR / "words.json").is_file() and (PROBE_DIR / "narration.mp3").is_file():
        return WordsDoc.model_validate_json((PROBE_DIR / "words.json").read_text()), PROBE_DIR / "narration.mp3"
    audio = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=4.2", "-q:a", "4", str(audio)],
        check=True, timeout=60,
    )
    audio_ms = render.get_audio_duration_ms(audio)
    words = [Word(text=t, start=i * 500, end=i * 500 + 450) for i, t in enumerate(SYNTHETIC_WORDS)]
    return WordsDoc(audio_duration_ms=audio_ms, text=" ".join(SYNTHETIC_WORDS), words=words), audio


@pytest.mark.render
def test_render_fixture_without_brand_assets(tmp_path):
    """img/, company/, 서울 폰트가 없어도 렌더 성공 + 1080×1920@30fps + audio ±100ms (AC-5, AC-6)."""
    render.ensure_ffmpeg_available()
    render.ensure_remotion_available(ROOT / "remotion")
    words_doc, audio = _render_fixture(tmp_path)

    project = tmp_path / "project"
    project.mkdir()
    shutil.copytree(ROOT / "emoticon", project / "emoticon")
    job_id = "sf_20260101_render"
    job_dir = tmp_path / "job"
    for sub in ("edit", "logs"):
        (job_dir / sub).mkdir(parents=True)

    segments = build_caption_segments(words_doc.words, chunk_size=14)
    cues = plan_cues(segments, audio_duration_ms=words_doc.audio_duration_ms,
                     emoticon_dir=project / "emoticon")
    edl = build_edl(job_id=job_id, words_doc=words_doc, caption_segments=segments, emoticon_cues=cues)
    props = build_props(edl, JobConfig(show_opening=False), staging_prefix=f"jobs/{job_id}", opening_text="",
                        cta_text="", header_logo=render.header_logo_path(project))
    assert props.header_logo is None
    try:
        out = render.render_remotion(
            job_id=job_id, job_dir=job_dir, props=props, words_doc=words_doc, audio_path=audio,
            project_root=project, remotion_dir=ROOT / "remotion",
        )
        info = render.get_video_info(out)
        assert (info.width, info.height) == (1080, 1920)
        assert info.fps == pytest.approx(30.0)
        assert abs(info.duration_ms - (words_doc.audio_duration_ms + ENDCARD_DURATION_MS)) <= 100
        staged = json.loads((job_dir / "edit" / "props.json").read_text())
        assert staged["captionSegments"]
        assert not (ROOT / "remotion" / "public" / "company").exists()
        assert not (ROOT / "remotion" / "public" / "img").exists()
    finally:
        render.cleanup_staging(ROOT / "remotion", job_id)


def test_opening_box_visible_on_first_frame():
    """썸네일(0번 프레임)이 빈 화면이 되지 않도록 오프닝 박스 scale은 0에서 시작하지 않는다."""
    src = (REMOTION_SRC / "OpeningBriefing.tsx").read_text()
    assert "scale(${pop})" not in src
    assert re.search(r"scale\(\$\{0\.\d+ \+ ", src)
