"""단일 job 오케스트레이션 (docs/architecture.md §2.1)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from md2short import render, state
from md2short._retry import ExternalAPIError
from md2short.caption_plan import build_caption_segments, segments_from_ranges, split_long_range
from md2short.company_logo import plan_company_logo_cues
from md2short.data_extract import plan_number_cards
from md2short.edl import build_edl, build_props
from md2short.emoticon_map import plan_cues
from md2short.jobs import create_job_dir, new_job_id
from md2short.numeric_display import apply_numeric_display_overrides
from md2short.opening import (
    extract_briefing_date,
    find_opening_window,
    opening_subtitle,
    opening_visual_text,
    spoken_opening,
)
from md2short.photo_engine import PhotoEngineError, plan_photo_cues
from md2short.qc import estimate_cost, run_qc
from md2short.schema import CTA_TEXT, JobConfig, WordsDoc
from md2short.script_engine import SYSTEM_PROMPT, ScriptResult, generate_script
from md2short.storyboard import (
    Cut,
    cuts_to_json,
    is_storyboard,
    map_cuts_to_segments,
    narration_text,
    parse_storyboard,
)
from md2short.transcript import transcribe
from md2short.tts_text import prepare_tts_text
from md2short.voice import synthesize

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_COPY = Path("output/ret.mp4")

StageCallback = Callable[[str, dict[str, Any]], None]


def _noop_stage(_name: str, _info: dict[str, Any]) -> None:
    return None


@dataclass
class Runtime:
    """외부 의존성 주입점. 테스트는 여기만 바꿔 끼운다."""

    project_root: Path = PROJECT_ROOT
    remotion_dir: Path = PROJECT_ROOT / "remotion"
    emoticon_dir: Path = PROJECT_ROOT / "emoticon"
    client_factory: Callable[[], httpx.Client] = httpx.Client
    preflight: Callable[[Path], None] | None = None
    probe_audio_ms: Callable[[Path], int] = render.get_audio_duration_ms
    probe_video: Callable[[Path], render.VideoInfo] = render.get_video_info
    renderer: Callable[..., Path] = render.render_remotion
    cleanup_staging: Callable[[Path, str], None] = render.cleanup_staging
    today: Callable[[], date] = date.today
    on_stage: StageCallback = field(default=_noop_stage)

    def run_preflight(self) -> None:
        if self.preflight is not None:
            self.preflight(self.remotion_dir)
            return
        render.ensure_ffmpeg_available()
        render.ensure_remotion_available(self.remotion_dir)


@dataclass
class JobResult:
    job_id: str
    job_dir: Path
    status: str
    qc_report: dict[str, Any] | None = None
    output_path: Path | None = None


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _dump_models(path: Path, items: list[Any]) -> None:
    _write_json(path, [m.model_dump(by_alias=True) for m in items])


def _photo_or_fallback(
    segments: list,
    emoticon_cues: list,
    cfg: JobConfig,
    rt: Runtime,
    client: httpx.Client,
    job_id: str,
    job_dir: Path,
    edit: Path,
    logs: Path,
    *,
    openai_api_key: str | None,
    image_prompts: dict[int, str],
) -> list:
    """photo 모드 cue. 어떤 이미지 단계든 실패하면 잡 전체를 emoticon 모드로 되돌린다(§5.7)."""
    try:
        if not openai_api_key:
            raise PhotoEngineError("OPENAI_API_KEY missing")
        cues, records = plan_photo_cues(
            segments,
            emoticon_cues,
            api_key=openai_api_key,
            model=cfg.script_model,
            client=client,
            job_id=job_id,
            remotion_dir=rt.remotion_dir,
            cache_dir=job_dir.parent / ".photo_cache",
            log_dir=logs,
            image_prompts=image_prompts,
            on_stage=rt.on_stage,
        )
    except (PhotoEngineError, ExternalAPIError, ValueError, KeyError) as exc:
        reason = f"{type(exc).__name__}: {exc}"
        _write_json(
            logs / "photo_fallback.json",
            {"from": "photo", "to": "emoticon", "reason": reason, "at": datetime.now(UTC).isoformat(timespec="seconds")},
        )
        rt.on_stage("photo_fallback", {"reason": reason})
        _dump_models(edit / "emoticon_cues.json", emoticon_cues)
        return emoticon_cues
    _write_json(edit / "photo_cues.json", records)
    return cues


def run_job(
    markdown_path: Path,
    cfg: JobConfig,
    *,
    elevenlabs_api_key: str,
    openai_api_key: str | None,
    jobs_root: Path = Path("jobs"),
    output_path: Path | None = DEFAULT_OUTPUT_COPY,
    runtime: Runtime | None = None,
) -> JobResult:
    rt = runtime or Runtime()
    rt.run_preflight()

    today = rt.today()
    job_id = new_job_id(today)
    job_dir = create_job_dir(jobs_root, job_id)
    inputs, logs, edit = job_dir / "inputs", job_dir / "logs", job_dir / "edit"
    markdown = markdown_path.read_text(encoding="utf-8")
    (inputs / "source.md").write_text(markdown, encoding="utf-8")
    state.write_status(
        job_dir,
        "created",
        job_id=job_id,
        config=cfg.model_dump(),
        markdown_input=str(markdown_path.resolve()),
        engine=cfg.engine,
    )
    rt.on_stage("created", {"job_id": job_id})

    try:
        with rt.client_factory() as client:
            result = _run_stages(
                markdown, cfg, rt, client, job_id, job_dir, inputs, logs, edit, today,
                elevenlabs_api_key=elevenlabs_api_key, openai_api_key=openai_api_key, output_path=output_path,
            )
    except Exception as exc:
        state.write_status(job_dir, "failed", error=f"{type(exc).__name__}: {exc}", error_type=type(exc).__name__)
        rt.on_stage("failed", {"job_id": job_id, "error": str(exc)})
        raise
    return result


def _run_stages(
    markdown: str,
    cfg: JobConfig,
    rt: Runtime,
    client: httpx.Client,
    job_id: str,
    job_dir: Path,
    inputs: Path,
    logs: Path,
    edit: Path,
    today: date,
    *,
    elevenlabs_api_key: str,
    openai_api_key: str | None,
    output_path: Path | None,
) -> JobResult:
    # [1] script
    # 오프닝 날짜: 원문에 적힌 브리핑 날짜 우선, 없으면 실행일
    briefing_date = extract_briefing_date(markdown) or today
    opening = spoken_opening(briefing_date) if cfg.show_opening else ""
    cuts: list[Cut] = parse_storyboard(markdown) if is_storyboard(markdown) else []
    if cuts:
        # 스토리보드: OpenAI 대본 생성을 우회하고 `자막`만 이어 내레이션으로 쓴다.
        _write_json(inputs / "storyboard.json", cuts_to_json(cuts))
        body = narration_text(cuts)
        script = ScriptResult(
            hook="", body=body, cta="", full_text=" ".join(p for p in (opening, body) if p),
            opening=opening, plan={"engine": "storyboard", "cuts": len(cuts)},
        )
    else:
        script = generate_script(
            markdown,
            api_key=openai_api_key,
            model=cfg.script_model,
            client=client,
            log_dir=logs,
            opening=opening,
            include_cta=cfg.show_outro,
        )
    if not script.full_text.strip():
        raise ValueError("script is empty: markdown has no narratable text")
    (inputs / "script.md").write_text(script.full_text + "\n", encoding="utf-8")
    _write_json(inputs / "script.json", script.to_json())
    state.write_status(
        job_dir, "script_generated", script_chars=len(script.full_text), briefing_date=briefing_date.isoformat()
    )
    rt.on_stage("script_generated", script.plan)

    # [2] TTS
    tts_input = prepare_tts_text(script.full_text)
    (logs / "tts_input.txt").write_text(tts_input + "\n", encoding="utf-8")
    audio_path = job_dir / "audio" / "narration.mp3"
    synthesize(
        tts_input, voice_id=cfg.voice_id, speed=cfg.voice_speed, api_key=elevenlabs_api_key,
        client=client, out_path=audio_path, log_dir=logs,
    )
    state.write_status(job_dir, "voice_generated")
    rt.on_stage("voice_generated", {})

    # [3] Scribe → words.json (시간 단일 진실원)
    audio_ms = rt.probe_audio_ms(audio_path)
    words_doc: WordsDoc = transcribe(
        audio_path, api_key=elevenlabs_api_key, client=client, audio_duration_ms=audio_ms, log_dir=logs
    )
    if not words_doc.words:
        raise ValueError("Scribe returned no words")
    (job_dir / "transcripts" / "words.json").write_text(words_doc.model_dump_json(indent=2), encoding="utf-8")
    state.write_status(job_dir, "transcribed")
    rt.on_stage("transcribed", {"words": len(words_doc.words), "audio_duration_ms": audio_ms})

    # [5][6] cue planning + subtitled
    # [4] 표시 텍스트만 원문 숫자·약어로 복원(단어 수·타이밍은 words.json과 1:1)
    display_words = apply_numeric_display_overrides(words_doc.words, script.full_text)
    window = find_opening_window(display_words) if cfg.show_opening else None
    skip = window.word_count if window else 0
    hints: dict[int, str] = {}
    image_prompts: dict[int, str] = {}
    if cuts:
        ranges = map_cuts_to_segments(display_words, cuts, skip_words=skip)
        cut_segments = segments_from_ranges(display_words, ranges)
        _write_json(
            edit / "storyboard_segments.json",
            [
                {"cut": cut.number, "caption": cut.caption, "text": seg.text, "wordStart": seg.word_start,
                 "wordEnd": seg.word_end, "startMs": seg.start_ms, "endMs": seg.end_ms}
                for cut, seg in zip(cuts, cut_segments, strict=True)
            ],
        )
        # 자막은 컷 경계를 지키면서 2줄(26자) 단위로 다시 나눈다. 각 조각은 자기 컷의 `화면 연출`을 hint로 받는다.
        sub_ranges = [(n, r) for n, (a, b) in enumerate(ranges) for r in split_long_range(display_words, a, b)]
        segments = segments_from_ranges(display_words, [r for _, r in sub_ranges])
        hints = {i: cuts[n].direction for i, (n, _) in enumerate(sub_ranges)}
        image_prompts = {i: cuts[n].image_prompt for i, (n, _) in enumerate(sub_ranges)}
    else:
        segments = build_caption_segments(display_words, chunk_size=cfg.chunk_size, skip_words=skip)
    cues = plan_cues(segments, audio_duration_ms=audio_ms, emoticon_dir=rt.emoticon_dir, hints=hints)
    if cfg.visual_mode == "photo":
        cues = _photo_or_fallback(
            segments, cues, cfg, rt, client, job_id, job_dir, edit, logs,
            openai_api_key=openai_api_key,
            image_prompts=image_prompts,
        )
    else:
        _dump_models(edit / "emoticon_cues.json", cues)
    number_cards, dropped_cards = plan_number_cards(
        display_words, script.full_text, audio_duration_ms=audio_ms, skip_words=skip
    )
    logo_cues = plan_company_logo_cues(
        display_words, company_dir=rt.project_root / "company", audio_duration_ms=audio_ms, skip_words=skip
    )
    _dump_models(edit / "caption_segments.json", segments)
    _write_json(
        edit / "number_cards.json",
        {"cards": [c.model_dump(by_alias=True) for c in number_cards], "dropped": dropped_cards},
    )
    _dump_models(edit / "company_logo_cues.json", logo_cues)
    edl = build_edl(
        job_id=job_id,
        words_doc=words_doc,
        caption_segments=segments,
        emoticon_cues=cues,
        number_cards=number_cards,
        company_logo_cues=logo_cues,
        opening_duration_ms=window.end_ms if window else 0,
    )
    (edit / "edl.json").write_text(edl.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    state.write_status(job_dir, "subtitled")
    rt.on_stage("subtitled", {"segments": len(segments), "cues": len(cues)})

    # [7] render
    props = build_props(
        edl,
        cfg,
        staging_prefix=f"jobs/{job_id}",
        opening_text=opening_visual_text(briefing_date),
        opening_subtitle=opening_subtitle(number_cards, script.hook),
        cta_text=CTA_TEXT[cfg.language],
        header_logo=render.header_logo_path(rt.project_root),
        opening_image=render.opening_image_path(rt.project_root),
    )
    final_mp4 = rt.renderer(
        job_id=job_id, job_dir=job_dir, props=props, words_doc=words_doc, audio_path=audio_path,
        project_root=rt.project_root, remotion_dir=rt.remotion_dir,
    )
    state.write_status(job_dir, "final_rendered", final_mp4=str(final_mp4))
    rt.on_stage("final_rendered", {})

    # [8] output copy
    copied: Path | None = None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(final_mp4, output_path)
        copied = output_path

    # [9] QC
    video = rt.probe_video(final_mp4)
    llm_in = len(SYSTEM_PROMPT) + len(markdown) if script.plan.get("engine") == "openai" else 0
    llm_out = len(script.full_text) if script.plan.get("engine") == "openai" else 0
    report = run_qc(
        audio_duration_ms=audio_ms,
        last_word_end_ms=words_doc.words[-1].end,
        final_mp4_duration_ms=video.duration_ms,
        cost=estimate_cost(
            tts_chars=len(tts_input), audio_duration_ms=audio_ms, llm_input_chars=llm_in, llm_output_chars=llm_out
        ),
        video={"width": video.width, "height": video.height, "fps": video.fps, "duration_ms": video.duration_ms},
    )
    report["job_id"] = job_id
    report["script_engine"] = script.plan.get("engine")
    qc_path = job_dir / "qc_report.json"
    _write_json(qc_path, report)
    final_status = "qc_passed" if report["passed"] else "qc_failed"
    state.write_status(
        job_dir,
        final_status,
        qc_report=str(qc_path),
        qc_passed=report["passed"],
        output_copy=str(copied) if copied else None,
    )
    rt.on_stage(final_status, {"qc_report": str(qc_path)})
    if report["passed"]:
        rt.cleanup_staging(rt.remotion_dir, job_id)
    return JobResult(job_id=job_id, job_dir=job_dir, status=final_status, qc_report=report, output_path=copied)
