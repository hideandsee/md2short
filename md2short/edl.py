"""EDL(`edit/edl.json`) 조립과 EDL → Remotion props 파생."""

from __future__ import annotations

from md2short.schema import (
    DISCLAIMER_TEXT,
    ENDCARD_DURATION_MS,
    OUTRO_DURATION_MS,
    CaptionSegment,
    CompanyLogoCue,
    Edl,
    EmoticonCue,
    JobConfig,
    NumberCard,
    RemotionProps,
    WordsDoc,
    normalize_bg_color,
)
from md2short.timeutil import ms_to_frames


def build_edl(
    *,
    job_id: str,
    words_doc: WordsDoc,
    caption_segments: list[CaptionSegment],
    emoticon_cues: list[EmoticonCue],
    number_cards: list[NumberCard] | None = None,
    company_logo_cues: list[CompanyLogoCue] | None = None,
    opening_duration_ms: int = 0,
) -> Edl:
    highlights = sorted({s.highlight_keyword for s in caption_segments if s.highlight_keyword})
    return Edl(
        job_id=job_id,
        audio_duration_ms=words_doc.audio_duration_ms,
        duration_in_frames=max(1, ms_to_frames(words_doc.audio_duration_ms)),
        caption_segments=caption_segments,
        emoticon_cues=emoticon_cues,
        number_cards=number_cards or [],
        company_logo_cues=company_logo_cues or [],
        highlight_keywords=highlights,
        opening_duration_ms=opening_duration_ms,
        opening_duration_frames=ms_to_frames(opening_duration_ms),
    )


def build_props(
    edl: Edl,
    cfg: JobConfig,
    *,
    staging_prefix: str,
    opening_text: str,
    cta_text: str,
    opening_subtitle: str = "",
    header_logo: str | None,
    opening_image: str | None = None,
) -> RemotionProps:
    endcard_frames = ms_to_frames(ENDCARD_DURATION_MS) if cfg.show_endcard else 0
    return RemotionProps(
        audio_file_name=f"{staging_prefix}/narration.mp3",
        words_file_name=f"{staging_prefix}/words.json",
        bg_color=normalize_bg_color(cfg.bg_color),
        chunk_size=cfg.chunk_size,
        caption_segments=edl.caption_segments,
        emoticon_cues=edl.emoticon_cues,
        company_logo_cues=edl.company_logo_cues,
        number_cards=edl.number_cards,
        highlight_keywords=edl.highlight_keywords,
        opening_text=opening_text if cfg.show_opening else "",
        opening_subtitle=opening_subtitle if cfg.show_opening else "",
        opening_duration_ms=edl.opening_duration_ms if cfg.show_opening else 0,
        opening_duration_frames=edl.opening_duration_frames if cfg.show_opening else 0,
        show_opening=cfg.show_opening,
        cta_text=cta_text,
        show_outro=cfg.show_outro,
        outro_duration_frames=ms_to_frames(OUTRO_DURATION_MS) if cfg.show_outro else 0,
        show_endcard=cfg.show_endcard,
        endcard_text=DISCLAIMER_TEXT[cfg.language] if cfg.show_endcard else "",
        endcard_duration_frames=endcard_frames,
        header_logo=header_logo,
        opening_image=opening_image if cfg.show_opening else None,
        duration_in_frames=edl.duration_in_frames + endcard_frames,
    )
