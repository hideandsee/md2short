"""레이어 간 계약 모델 (docs/architecture.md §4).

`transcripts/words.json`의 `Word`는 ms만 가진다(§4.2, 시간 단일 진실원).
프레임 값은 Python이 `timeutil.ms_to_frames`로 계산해 EDL/props에만 싣는다.
Remotion은 props의 프레임 값을 그대로 쓰고 시간 계산을 하지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Language = Literal["ko"]
VisualMode = Literal["emoticon", "photo"]
AssetKind = Literal["emoticon", "photo"]

FPS = 30
WIDTH = 1080
HEIGHT = 1920

DEFAULT_VOICES: dict[str, str] = {"ko": "v1jVu1Ky28piIPEJqRrm"}
SCRIBE_LANG: dict[str, str] = {"ko": "kor"}
CTA_TEXT: dict[str, str] = {"ko": "구독과 알람 설정 부탁드립니다"}

OPENING_DURATION_FALLBACK_MS = 2800
OUTRO_DURATION_MS = 2600


class JobConfig(BaseModel):
    platform: Literal["youtube_shorts", "instagram_reels", "tiktok"] = "youtube_shorts"
    language: Language = "ko"
    voice_id: str = DEFAULT_VOICES["ko"]
    voice_speed: float = Field(default=1.0, ge=0.7, le=1.2)
    template_id: str = "tech_explainer"
    bg_color: str = "0xFFFFFF"
    chunk_size: int = Field(default=14, ge=1, le=24)
    engine: Literal["remotion"] = "remotion"
    visual_mode: VisualMode = "emoticon"
    show_opening: bool = True
    show_outro: bool = False
    script_model: str = "gpt-5-mini"


# --- words.json (§4.2) -------------------------------------------------------


class Word(BaseModel):
    text: str
    start: int
    end: int


class WordsDoc(BaseModel):
    language_code: str = "kor"
    audio_duration_ms: int
    text: str
    words: list[Word]


# --- EDL / props (§4.3) ------------------------------------------------------


class _Camel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        json_schema_serialization_defaults_required=True,
    )


class FramedWord(_Camel):
    text: str
    start_ms: int
    end_ms: int
    start_frame: int
    end_frame: int


class CaptionSegment(_Camel):
    index: int
    text: str
    start_ms: int
    end_ms: int
    start_frame: int
    end_frame: int
    word_start: int
    word_end: int  # exclusive
    words: list[FramedWord] = Field(default_factory=list)
    highlight_keyword: str | None = None


class EmoticonCue(_Camel):
    emoticon_file_name: str
    keyword: str | None = None
    start_ms: int
    duration_ms: int
    start_frame: int
    duration_frames: int
    asset_kind: AssetKind = "emoticon"
    visual_mode: VisualMode = "emoticon"
    primary_visual_subject: str | None = None
    visual_keywords: list[str] = Field(default_factory=list)


class NumberCard(_Camel):
    text: str
    label: str | None = None  # 지표명(S&P 500, 반도체, 국채 금리…)
    direction: Literal["up", "down"] | None = None
    word_start: int
    word_end: int  # exclusive
    start_ms: int
    duration_ms: int
    start_frame: int
    duration_frames: int


class CompanyLogoCue(_Camel):
    company: str
    logo_file_name: str
    start_ms: int
    duration_ms: int
    start_frame: int
    duration_frames: int


class Edl(_Camel):
    """편집 설계서. props.json은 이 EDL에서만 파생된다."""

    job_id: str
    audio_duration_ms: int
    duration_in_frames: int
    caption_segments: list[CaptionSegment]
    emoticon_cues: list[EmoticonCue] = Field(default_factory=list)
    number_cards: list[NumberCard] = Field(default_factory=list)
    company_logo_cues: list[CompanyLogoCue] = Field(default_factory=list)
    highlight_keywords: list[str] = Field(default_factory=list)
    opening_duration_ms: int = 0
    opening_duration_frames: int = 0


class RemotionProps(_Camel):
    audio_file_name: str
    words_file_name: str
    bg_color: str
    chunk_size: int
    caption_segments: list[CaptionSegment]
    emoticon_cues: list[EmoticonCue] = Field(default_factory=list)
    company_logo_cues: list[CompanyLogoCue] = Field(default_factory=list)
    number_cards: list[NumberCard] = Field(default_factory=list)
    highlight_keywords: list[str] = Field(default_factory=list)
    opening_text: str = ""
    opening_subtitle: str = ""  # 오프닝 박스 아래 hook 한 줄(숫자 카드 요약)
    opening_duration_ms: int = 0
    opening_duration_frames: int = 0
    show_opening: bool = True
    cta_text: str = CTA_TEXT["ko"]
    show_outro: bool = False
    outro_duration_frames: int = 0
    header_logo: str | None = None
    font_family: str = "MD2ShortSans"
    duration_in_frames: int


def normalize_bg_color(value: str) -> str:
    """`0xFFFFFF`, `#ffffff`, `FFFFFF` → `#FFFFFF`."""
    raw = value.strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    raw = raw.lstrip("#")
    if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        raise ValueError(f"invalid bg color: {value!r}")
    return "#" + raw.upper()
