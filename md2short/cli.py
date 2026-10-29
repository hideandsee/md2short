"""`md2short` CLI (docs/architecture.md §6). 종료 코드: 0 성공, 1 입력 오류, 2 실행 중 예외·QC 실패."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from dotenv import find_dotenv, load_dotenv

from md2short.schema import DEFAULT_VOICES, JobConfig, normalize_bg_color

EXIT_OK, EXIT_INPUT, EXIT_RUN = 0, 1, 2

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Markdown → 한국어 9:16 숏폼 MP4")


class InputError(Exception):
    pass


@app.callback()
def _group() -> None:
    """Markdown → 한국어 9:16 숏폼 MP4 (`run`, `status`, `clean`)."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise InputError(message)


@app.command()
def run(
    markdown_file: Path = typer.Argument(..., help="입력 마크다운"),
    lang: str = typer.Option("ko", "--lang", "-l"),
    voice: str = typer.Option(DEFAULT_VOICES["ko"], "--voice", "-v"),
    speed: float = typer.Option(1.0, "--speed"),
    template: str = typer.Option("tech_explainer", "--template", "-t"),
    chunk_size: int = typer.Option(14, "--chunk-size"),
    bg: str = typer.Option("0xFFFFFF", "--bg"),
    jobs_root: Path = typer.Option(Path("jobs"), "--jobs-root"),
    engine: str = typer.Option("remotion", "--engine"),
    visual_mode: str = typer.Option("emoticon", "--visual-mode"),
    model: str = typer.Option("gpt-5-mini", "--model"),
    output: str = typer.Option("output/ret.mp4", "--output", "-o", help="빈 문자열이면 사본 비활성화"),
    no_opening: bool = typer.Option(False, "--no-opening", help="날짜 오프닝 끄기"),
    outro: bool = typer.Option(False, "--outro", help="마지막 구독 CTA overlay 표시"),
    no_endcard: bool = typer.Option(False, "--no-endcard", help="끝에 붙는 투자 면책 고지 엔드카드 생략"),
) -> None:
    """마크다운 1개로 숏폼 1편을 만든다."""
    from md2short.pipeline import run_job

    _require(markdown_file.is_file(), f"markdown file not found: {markdown_file}")
    _require(lang == "ko", f"--lang {lang!r} not supported: v1 is Korean only (ko)")
    _require(1 <= chunk_size <= 24, "--chunk-size must be between 1 and 24")
    _require(0.7 <= speed <= 1.2, "--speed must be between 0.7 and 1.2")
    _require(engine == "remotion", "--engine must be 'remotion' (ffmpeg render engine is not supported)")
    _require(visual_mode in ("emoticon", "photo"), "--visual-mode must be 'emoticon' or 'photo'")
    try:
        bg_color = normalize_bg_color(bg)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    eleven_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    _require(bool(eleven_key), "ELEVENLABS_API_KEY is not set (.env)")
    _require(visual_mode != "photo" or bool(openai_key), "--visual-mode photo requires OPENAI_API_KEY")

    cfg = JobConfig(
        voice_id=voice,
        voice_speed=speed,
        template_id=template,
        bg_color=bg_color,
        chunk_size=chunk_size,
        visual_mode=visual_mode,  # type: ignore[arg-type]
        show_opening=not no_opening,
        show_outro=outro,
        show_endcard=not no_endcard,
        script_model=model,
    )
    output_path = Path(output) if output else None

    def on_stage(name: str, info: dict) -> None:
        typer.echo(f"[{name}] {info}" if info else f"[{name}]", err=True)

    from md2short.pipeline import Runtime

    try:
        result = run_job(
            markdown_file,
            cfg,
            elevenlabs_api_key=eleven_key,
            openai_api_key=openai_key,
            jobs_root=jobs_root,
            output_path=output_path,
            runtime=Runtime(on_stage=on_stage),
        )
    except Exception as exc:  # noqa: BLE001 — 모든 실행 예외는 exit 2 (§6.4)
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)
        raise typer.Exit(EXIT_RUN) from exc
    typer.echo(f"job_id={result.job_id} status={result.status}")
    if result.output_path:
        typer.echo(f"output={result.output_path}")
    if result.status != "qc_passed":
        raise typer.Exit(EXIT_RUN)


@app.command()
def status(
    job_id: str = typer.Argument(..., help="sf_YYYYMMDD_xxxxxx"),
    jobs_root: Path = typer.Option(Path("jobs"), "--jobs-root"),
) -> None:
    """status.json 요약과 QC check·비용을 출력한다."""
    from md2short.jobops import format_status

    job_dir = jobs_root / job_id
    _require((job_dir / "status.json").is_file(), f"job not found: {job_dir}")
    typer.echo(format_status(job_dir))


@app.command()
def clean(
    older_than: str = typer.Option(..., "--older-than", help="초 숫자 또는 30s/15m/24h/7d"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    jobs_root: Path = typer.Option(Path("jobs"), "--jobs-root"),
) -> None:
    """오래된 job 디렉터리(와 남은 Remotion staging)를 지운다."""
    from md2short.jobops import clean_jobs, parse_age

    try:
        seconds = parse_age(older_than)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    removed = clean_jobs(jobs_root, seconds, dry_run=dry_run)
    verb = "would remove" if dry_run else "removed"
    for path in removed:
        typer.echo(f"{verb} {path}")
    typer.echo(f"{len(removed)} job(s) {verb}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv(find_dotenv(usecwd=True))
    command = typer.main.get_command(app)
    try:
        rv = command.main(args=argv if argv is not None else sys.argv[1:], prog_name="md2short", standalone_mode=False)
    except InputError as exc:
        typer.echo(f"error: {exc}", err=True)
        return EXIT_INPUT
    except typer.Exit as exc:
        return exc.exit_code
    except typer.Abort:
        return EXIT_INPUT
    except typer.exceptions.TyperException as exc:  # usage/parameter errors → 입력 오류
        show = getattr(exc, "show", None)
        show() if callable(show) else typer.echo(f"error: {exc}", err=True)
        return EXIT_INPUT
    # standalone_mode=False에서는 typer.Exit 코드가 예외가 아니라 반환값으로 온다.
    return rv if isinstance(rv, int) else EXIT_OK


def entrypoint() -> None:
    sys.exit(main())
