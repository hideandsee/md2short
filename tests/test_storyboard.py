from __future__ import annotations

import json

import httpx
import pytest

from md2short.caption_plan import segments_from_ranges
from md2short.emoticon_map import plan_cues
from md2short.numeric_display import apply_numeric_display_overrides
from md2short.pipeline import run_job
from md2short.render import VideoInfo
from md2short.schema import ENDCARD_DURATION_MS, JobConfig, Word
from md2short.storyboard import is_storyboard, map_cuts_to_segments, narration_text, parse_storyboard
from md2short.transcript import ELEVENLABS_STT_URL

from .conftest import ROOT, scribe_payload

SAMPLE = (ROOT / "samples" / "storyboard.md").read_text(encoding="utf-8")

# Scribe가 숫자 주변을 잘게 쪼갠 전사(‘6%’ → ‘6’, ‘퍼센트’ 등)
SCRIBE_TEXT = (
    "오늘 국제 유가가 크게 흔들렸습니다. "
    "서부텍사스산 원유는 하루 만에 6 퍼센트 올라 배럴당 84 달러를 기록했습니다. "
    "반면 항공주와 운송주는 비용 부담 우려로 약세를 보였습니다. "
    "당분간 에너지 가격 변동성에 대비하는 전략이 필요합니다."
)


def _scribe_words(text: str, offset: int = 0) -> list[Word]:
    return [Word(text=t, start=offset + i * 400, end=offset + i * 400 + 350) for i, t in enumerate(text.split())]


def test_detect_and_parse_sample():
    assert is_storyboard(SAMPLE)
    assert not is_storyboard("# 일반 문서\n\n- 코스피 상승.")
    cuts = parse_storyboard(SAMPLE)
    assert [c.number for c in cuts] == [1, 2, 3, 4]
    assert cuts[2].direction == "주가 폭락 패닉, 하락 화살표"
    assert cuts[0].image_prompt.startswith("oil barrels")


def test_narration_is_captions_only():
    cuts = parse_storyboard(SAMPLE)
    text = narration_text(cuts)
    assert text == " ".join(c.caption for c in cuts)
    for cut in cuts:
        assert cut.direction not in text and cut.image_prompt not in text
    assert "화면 연출" not in text and "이미지 프롬프트" not in text


def test_cut_mapping_snaps_to_sentences_despite_number_splits():
    cuts = parse_storyboard(SAMPLE)
    words = _scribe_words(SCRIBE_TEXT)
    ranges = map_cuts_to_segments(words, cuts)
    assert len(ranges) == len(cuts)
    texts = [" ".join(w.text for w in words[a:b]) for a, b in ranges]
    assert texts[0] == "오늘 국제 유가가 크게 흔들렸습니다."
    assert texts[1].endswith("기록했습니다.")
    assert texts[2].startswith("반면") and texts[3].startswith("당분간")
    assert ranges[0][0] == 0 and ranges[-1][1] == len(words)
    assert all(a < b for a, b in ranges)


def test_direction_drives_cue_selection():
    cuts = parse_storyboard(SAMPLE)
    assert "폭락" not in cuts[2].caption
    words = _scribe_words(SCRIBE_TEXT)
    segments = segments_from_ranges(words, map_cuts_to_segments(words, cuts))
    hints = {i: c.direction for i, c in enumerate(cuts)}
    with_hints = plan_cues(segments, audio_duration_ms=20_000, emoticon_dir=ROOT / "emoticon", hints=hints)
    assert with_hints[2].emoticon_file_name == "emoticon/28_폭락_패닉하락.png"
    without = plan_cues(segments, audio_duration_ms=20_000, emoticon_dir=ROOT / "emoticon")
    assert without[2].emoticon_file_name != "emoticon/28_폭락_패닉하락.png"


def test_display_restore_inside_storyboard():
    words = _scribe_words(SCRIBE_TEXT)
    display = apply_numeric_display_overrides(words, narration_text(parse_storyboard(SAMPLE)))
    assert [w.start for w in display] == [w.start for w in words]


@pytest.fixture
def storyboard_md(tmp_path):
    path = tmp_path / "storyboard.md"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def test_pipeline_storyboard_branch(mock_apis, runtime, storyboard_md, tmp_path):
    opening_words = [("10월", 0.0, 0.3), ("26일", 0.32, 0.6), ("타이거살구브리핑입니다.", 0.62, 1.4)]
    body = [(t, 1.5 + i * 0.4, 1.5 + i * 0.4 + 0.35) for i, t in enumerate(SCRIBE_TEXT.split())]
    mock_apis.post(ELEVENLABS_STT_URL).mock(return_value=httpx.Response(200, json=scribe_payload(opening_words + body)))
    audio_ms = int((body[-1][2] + 0.3) * 1000)
    runtime.probe_audio_ms = lambda _p: audio_ms
    runtime.probe_video = lambda _p: VideoInfo(width=1080, height=1920, fps=30.0, duration_ms=audio_ms + ENDCARD_DURATION_MS)
    openai_route = mock_apis.routes[0]
    result = run_job(storyboard_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
                     jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)
    assert result.status == "qc_passed"
    assert not openai_route.called  # 스토리보드는 OpenAI 대본 생성을 우회
    job = result.job_dir
    script = json.loads((job / "inputs/script.json").read_text())
    assert script["plan"]["engine"] == "storyboard"
    assert len(json.loads((job / "inputs/storyboard.json").read_text())) == 4
    mapped = json.loads((job / "edit/storyboard_segments.json").read_text())
    captions = json.loads((job / "edit/caption_segments.json").read_text())
    assert len(mapped) == 4 and len(captions) >= 4
    assert mapped[0]["wordStart"] == 3  # 오프닝 단어 뒤부터
    # 자막 조각은 컷 경계를 넘지 않고, 컷 3 조각들은 모두 `화면 연출`(폭락)에 맞는 이미지를 받는다
    cut_bounds = {m["wordStart"] for m in mapped} | {m["wordEnd"] for m in mapped}
    assert all(any(c["wordStart"] == b for c in captions) for b in cut_bounds - {mapped[-1]["wordEnd"]})
    assert all(len(c["text"]) <= 26 for c in captions)
    cues = json.loads((job / "edit/emoticon_cues.json").read_text())
    cut3 = mapped[2]
    cut3_cues = [cue for cue, cap in zip(cues, captions, strict=True) if cut3["wordStart"] <= cap["wordStart"] < cut3["wordEnd"]]
    assert cut3_cues and all(c["emoticonFileName"] == "emoticon/28_폭락_패닉하락.png" for c in cut3_cues)
    tts_input = (job / "logs/tts_input.txt").read_text()
    assert "화면 연출" not in tts_input and "oil barrels" not in tts_input
