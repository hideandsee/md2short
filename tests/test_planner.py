from __future__ import annotations

import json

import pytest

from md2short.caption_plan import build_caption_segments
from md2short.company_logo import plan_company_logo_cues
from md2short.data_extract import (
    CARD_DURATION_MS,
    COOLDOWN_MS,
    MAX_CARDS,
    extract_candidates,
    plan_number_cards,
)
from md2short.emoticon_map import best_match, build_keyword_index, plan_cues
from md2short.numeric_display import apply_numeric_display_overrides, read_number
from md2short.opening import find_opening_window
from md2short.pipeline import run_job
from md2short.schema import JobConfig, Word

from .conftest import ROOT

EMOTICON_DIR = ROOT / "emoticon"

SCRIPT = (
    "10월 26일 데이브리핑입니다. S&P 500 지수가 1.2% 오른 5,830포인트로 마감했다. "
    "반도체 업종 지수는 3.5% 급등했다. 코스피는 외국인 순매수 1조 2천억 원에 힘입어 0.9% 올랐다."
)
# Scribe 발음형 전사(약어·숫자 일부가 한글로 나옴)
SCRIBE_WORDS = [
    "10월", "26일", "데이브리핑입니다.", "에센피", "오백", "지수가", "일점이", "퍼센트", "오른", "오천팔백삼십포인트로",
    "마감했다.", "반도체", "업종", "지수는", "3.5%", "급등했다.", "코스피는", "외국인", "순매수", "1조", "2천억",
    "원에", "힘입어", "0.9%", "올랐다.",
]


def _words(texts: list[str], step: int = 450) -> list[Word]:
    return [Word(text=t, start=i * step, end=i * step + step - 50) for i, t in enumerate(texts)]


@pytest.fixture
def words() -> list[Word]:
    return _words(SCRIBE_WORDS)


@pytest.fixture
def display(words) -> list[Word]:
    return apply_numeric_display_overrides(words, SCRIPT)


def test_numeric_display_restores_text_and_keeps_timing(words, display):
    assert len(display) == len(words)
    assert [(w.start, w.end) for w in display] == [(w.start, w.end) for w in words]
    assert display[3].text == "S&P 500" and display[4].text == ""
    assert display[6].text == "1.2%" and display[7].text == ""
    assert display[9].text == "5,830포인트로"
    assert display[14].text == "3.5%"  # 이미 원문 표기
    assert display[8].text == "오른"  # 앞붙음 매칭 없음


@pytest.mark.parametrize("num,ko", [("2,710", "이천칠백십"), ("0.9", "영점구"), ("1372", "천삼백칠십이"), ("100000", "십만")])
def test_read_number(num, ko):
    assert read_number(num) == ko


def test_caption_and_cue_starts_are_word_starts(display):
    window = find_opening_window(display)
    assert window.word_count == 3
    segments = build_caption_segments(display, chunk_size=14, skip_words=window.word_count)
    audio_ms = display[-1].end + 300
    cues = plan_cues(segments, display, audio_duration_ms=audio_ms, emoticon_dir=EMOTICON_DIR)
    starts = {w.start for w in display}
    assert all(s.start_ms in starts for s in segments)
    assert all(c.start_ms in starts for c in cues)
    assert all(c.start_ms + c.duration_ms <= audio_ms for c in cues)
    assert segments[0].word_start == 3  # 오프닝 단어 제외
    assert all(w.text for s in segments for w in s.words)  # 비운 단어는 자막에 없음
    assert segments[0].text.startswith("S&P 500 지수가 1.2%")


def test_number_cards_are_word_anchored(display):
    cards, dropped = plan_number_cards(display, SCRIPT, audio_duration_ms=display[-1].end, skip_words=3)
    assert cards, "expected at least one card"
    for card in cards:
        assert 0 <= card.word_start < card.word_end <= len(display)
        assert card.start_ms == display[card.word_start].start
        assert any(ch.isdigit() for ch in display[card.word_start].text)
        assert card.duration_ms <= CARD_DURATION_MS
    starts = [c.start_ms for c in cards]
    assert all(b - a >= COOLDOWN_MS for a, b in zip(starts, starts[1:], strict=False))
    assert cards[0].text == "1.2%" and cards[0].word_start == 6
    assert {d["reason"] for d in dropped} <= {"cooldown", "max_cards", "no matching word in words.json", "after_audio_end"}


def test_unmatched_number_is_dropped_not_estimated():
    words = _words(["코스피는", "많이", "올랐다."])
    cards, dropped = plan_number_cards(words, "코스피는 3.5% 올랐다.", audio_duration_ms=2000)
    assert cards == []
    assert dropped == [{"text": "3.5%", "kind": "percent", "reason": "no matching word in words.json"}]


def test_number_card_cap():
    texts = [f"{i}.5%" for i in range(1, 11)]
    words = _words(texts, step=3000)
    cards, dropped = plan_number_cards(words, " ".join(texts), audio_duration_ms=40_000)
    assert len(cards) == MAX_CARDS
    assert sum(d["reason"] == "max_cards" for d in dropped) == 4


def test_candidates_cover_architecture_5_9_patterns():
    kinds = {c.kind: c.text for c in extract_candidates("코스피 2,710포인트, 1조 2천억 원, 3.5%, 120p")}
    assert kinds == {"index": "코스피 2,710포인트", "money": "1조 2천억 원", "percent": "3.5%", "points": "120p"}


def test_emoticon_tie_break_prefers_exact_keyword_then_lower_number():
    index = build_keyword_index(EMOTICON_DIR)
    assert best_match("폭락", index).entry.file_name == "28_폭락_패닉하락.png"
    assert best_match("주가 폭락 패닉, 하락 화살표", index).entry.file_name == "28_폭락_패닉하락.png"
    assert best_match("유가가 급등했다", index).entry.file_name == "22_유가비상_원유급등.png"


def test_lookahead_does_not_steal_next_sentence_image():
    words = _words(["코스피는", "0.9%", "마감했다.", "반도체", "업종이", "급등했다."])
    segments = build_caption_segments(words, chunk_size=14)
    cues = plan_cues(segments, words, audio_duration_ms=3000, emoticon_dir=EMOTICON_DIR)
    assert cues[0].emoticon_file_name == "emoticon/05_분석중_차트.png"
    assert cues[1].emoticon_file_name == "emoticon/26_반도체급등_로켓상승.png"


def test_company_logo_cues(tmp_path, display):
    empty = tmp_path / "company"
    empty.mkdir()
    assert plan_company_logo_cues(display, company_dir=empty, audio_duration_ms=20_000) == []
    assert plan_company_logo_cues(display, company_dir=tmp_path / "missing", audio_duration_ms=20_000) == []
    (empty / "반도체.png").write_bytes(b"png")
    cues = plan_company_logo_cues(display, company_dir=empty, audio_duration_ms=20_000)
    assert [c.logo_file_name for c in cues] == ["company/반도체.png"]
    assert cues[0].start_ms == display[11].start


def test_pipeline_writes_planner_artifacts(mock_apis, runtime, sample_md, tmp_path):
    result = run_job(sample_md, JobConfig(), elevenlabs_api_key="e", openai_api_key="o",
                     jobs_root=tmp_path / "jobs", output_path=None, runtime=runtime)
    cards = json.loads((result.job_dir / "edit/number_cards.json").read_text())
    assert set(cards) == {"cards", "dropped"}
    assert all("wordStart" in c for c in cards["cards"])
    assert json.loads((result.job_dir / "edit/company_logo_cues.json").read_text()) == []
    props = json.loads((result.job_dir / "edit/props.json").read_text())
    assert props["numberCards"] == cards["cards"]
