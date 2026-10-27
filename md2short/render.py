"""Remotion 렌더 subprocess + ffprobe 측정 (docs/architecture.md §5.5).

ffmpeg/ffprobe는 길이 측정·QC 보조 전용이다. 자막·오버레이는 Remotion만 합성한다.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from md2short.schema import RemotionProps, WordsDoc

FFPROBE_TIMEOUT_S = 30
RENDER_TIMEOUT_S = 900
RENDER_CONCURRENCY = 2
COMPOSITION_ID = "TechExplainer"
# Remotion `Fonts.tsx`가 읽는 고정 파일명. Noto는 subset별 파일이라 korean + latin을 둘 다 둔다.
NOTO_FILES = {
    "regular.woff2": "noto-sans-kr-korean-400-normal.woff2",
    "regular-latin.woff2": "noto-sans-kr-latin-400-normal.woff2",
    "bold.woff2": "noto-sans-kr-korean-700-normal.woff2",
    "bold-latin.woff2": "noto-sans-kr-latin-700-normal.woff2",
}
SEOUL_FILES = {
    "regular.woff2": "SeoulNotice-Regular.woff2",
    "regular-latin.woff2": "SeoulNotice-Regular.woff2",
    "bold.woff2": "SeoulAlrim-Bold.woff2",
    "bold-latin.woff2": "SeoulAlrim-Bold.woff2",
}


class PreflightError(RuntimeError):
    pass


class RenderError(RuntimeError):
    pass


def ensure_ffmpeg_available() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise PreflightError(f"missing {', '.join(missing)}: install with `sudo apt-get install -y ffmpeg`")


def _chrome_present(remotion_dir: Path) -> bool:
    cache = remotion_dir / "node_modules" / ".remotion"
    if not cache.is_dir():
        return False
    return any(p.is_file() for p in cache.rglob("chrome-headless-shell"))


def ensure_remotion_available(remotion_dir: Path) -> None:
    """존재만 확인한다. 브라우저 다운로드는 setup 단계(README) 책임이다."""
    if not (remotion_dir / "src" / "index.ts").is_file():
        raise PreflightError(f"Remotion project not found at {remotion_dir}")
    if not (remotion_dir / "node_modules" / ".bin" / "remotion").exists():
        raise PreflightError("remotion/node_modules missing: run `pnpm -C remotion install`")
    if shutil.which("pnpm") is None:
        raise PreflightError("pnpm not found on PATH")
    if not _chrome_present(remotion_dir):
        raise PreflightError("Chrome Headless Shell missing: run `pnpm -C remotion exec remotion browser ensure`")


def _ffprobe_json(path: Path, *args: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", *args, "-of", "json", str(path)],
        capture_output=True,
        text=True,
        timeout=FFPROBE_TIMEOUT_S,
        check=True,
    )
    return json.loads(result.stdout)


def get_audio_duration_ms(path: Path) -> int:
    data = _ffprobe_json(path, "-show_entries", "format=duration")
    return int(float(data["format"]["duration"]) * 1000 + 0.5)


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration_ms: int


def get_video_info(path: Path) -> VideoInfo:
    data = _ffprobe_json(
        path, "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration"
    )
    stream = data["streams"][0]
    num, den = stream["r_frame_rate"].split("/")
    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=float(num) / float(den),
        duration_ms=int(float(data["format"]["duration"]) * 1000 + 0.5),
    )


def header_logo_path(project_root: Path) -> str | None:
    """props `headerLogo` 값. 파일이 없으면 None → BrandHeader가 텍스트 워드마크로 대체."""
    return "img/header_logo.png" if (project_root / "img" / "header_logo.png").is_file() else None


def _link_asset_dir(public_dir: Path, name: str, source: Path) -> None:
    target = public_dir / name
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)
    if not source.is_dir() or not any(source.iterdir()):
        return
    try:
        target.symlink_to(os.path.relpath(source, public_dir), target_is_directory=True)
    except OSError:
        shutil.copytree(source, target)


def stage_fonts(public_dir: Path, project_root: Path, remotion_dir: Path) -> str:
    """`public/font/{regular,bold}{,-latin}.woff2` + `font.css`. 서울 폰트가 없으면 Noto Sans KR. 사용한 계열명 반환."""
    font_dir = public_dir / "font"
    font_dir.mkdir(parents=True, exist_ok=True)
    seoul_dir = project_root / "fonts"
    if all((seoul_dir / src).is_file() for src in SEOUL_FILES.values()):
        sources, family = {dst: seoul_dir / src for dst, src in SEOUL_FILES.items()}, "SeoulNotice"
    else:
        noto_dir = remotion_dir / "node_modules" / "@fontsource" / "noto-sans-kr" / "files"
        sources, family = {dst: noto_dir / src for dst, src in NOTO_FILES.items()}, "Noto Sans KR"
    for dst, src in sources.items():
        if not src.is_file():
            raise RenderError(f"font file missing: {src}")
        shutil.copyfile(src, font_dir / dst)
    css = "".join(
        f"@font-face{{font-family:'MD2ShortSans';src:url('{name}') format('woff2');"
        f"font-weight:{700 if name.startswith('bold') else 400};}}\n"
        for name in sources
    ) + f"/* source: {family} */\n"
    (font_dir / "font.css").write_text(css, encoding="utf-8")
    return family


def staging_dir(remotion_dir: Path, job_id: str) -> Path:
    return remotion_dir / "public" / "jobs" / job_id


def stage_assets(
    *,
    job_id: str,
    props: RemotionProps,
    words_doc: WordsDoc,
    audio_path: Path,
    project_root: Path,
    remotion_dir: Path,
) -> Path:
    public_dir = remotion_dir / "public"
    stage = staging_dir(remotion_dir, job_id)
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audio_path, stage / "narration.mp3")
    (stage / "words.json").write_text(words_doc.model_dump_json(indent=2), encoding="utf-8")
    props_path = stage / "props.json"
    props_path.write_text(props.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    for name in ("emoticon", "img", "company"):
        _link_asset_dir(public_dir, name, project_root / name)
    stage_fonts(public_dir, project_root, remotion_dir)
    return props_path


def render_remotion(
    *,
    job_id: str,
    job_dir: Path,
    props: RemotionProps,
    words_doc: WordsDoc,
    audio_path: Path,
    project_root: Path,
    remotion_dir: Path,
    timeout_s: int = RENDER_TIMEOUT_S,
) -> Path:
    """staging → `pnpm exec remotion render` → `edit/final.mp4`. 감사용 props 사본은 `edit/props.json`."""
    props_path = stage_assets(
        job_id=job_id,
        props=props,
        words_doc=words_doc,
        audio_path=audio_path,
        project_root=project_root,
        remotion_dir=remotion_dir,
    )
    shutil.copyfile(props_path, job_dir / "edit" / "props.json")
    out = job_dir / "edit" / "final.mp4"
    cmd = [
        "pnpm",
        "exec",
        "remotion",
        "render",
        "src/index.ts",
        COMPOSITION_ID,
        str(out),
        f"--props={props_path}",
        "--codec=h264",
        f"--concurrency={RENDER_CONCURRENCY}",
        "--log=warn",
        "--overwrite",
    ]
    log_path = job_dir / "logs" / "remotion.log"
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        try:
            proc = subprocess.run(cmd, cwd=remotion_dir, stdout=log, stderr=subprocess.STDOUT, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise RenderError(f"remotion render timed out after {timeout_s}s (see {log_path})") from exc
    if proc.returncode != 0 or not out.is_file():
        raise RenderError(f"remotion render failed with exit {proc.returncode} (see {log_path})")
    return out


def cleanup_staging(remotion_dir: Path, job_id: str) -> None:
    shutil.rmtree(staging_dir(remotion_dir, job_id), ignore_errors=True)
