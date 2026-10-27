from __future__ import annotations

import json

import pytest

from md2short.caption_plan import build_caption_segments
from md2short.company_logo import plan_company_logo_cues
from md2short.data_extract import (
    CARD_DURATION_MS,
    COOLDOWN_MS,
    MS_PER_CARD,
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
    "10월 26일 타이거살구브리핑입니다. S&P 500 지수가 1.2% 오른 5,830포인트로 마감했다. "
    "반도체 업종 지수는 3.5% 급등했다. 코스피는 외국인 순매수 1조 2천억 원에 힘입어 0.9% 올랐다."
)
# Scribe 발음형 전사(약어·숫자 일부가 한글로 나옴)
SCRIBE_WORDS = [
    "10월", "26일", "타이거살구브리핑입니다.", "에센피", "오백", "지수가", "일점이", "퍼센트", "오른", "오천팔백삼십포인트로",
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
    cues = plan_cues(segments, audio_duration_ms=audio_ms, emoticon_dir=EMOTICON_DIR)
    starts = {w.start for w in display}
    assert all(s.start_ms in starts for s in segments)
    assert all(c.start_ms in starts for c in cues)
    assert all(c.start_ms + c.duration_ms <= audio_ms for c in cues)
    assert segments[0].word_start == 3  # 오프닝 단어 제외
    assert all(w.text for s in segments for w in s.words)  # 비운 단어는 자막에 없음
    assert segments[0].text.startswith("S&P 500 지수가")


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
    assert (cards[0].label, cards[0].text, cards[0].direction, cards[0].word_start) == ("S&P 500", "1.2%", "up", 6)
    assert (cards[1].label, cards[1].text, cards[1].direction) == ("반도체", "3.5%", "up")
    assert {d["reason"] for d in dropped} <= {
        "cooldown", "max_cards", "no matching word in words.json", "after_audio_end", "not_sentence_representative"
    }


def test_one_representative_card_per_sentence_prefers_strong_move():
    words = _words(["나스닥은", "1.8%", "상승했고,", "반도체", "지수는", "3.5%", "급등했다."], step=1000)
    cards, dropped = plan_number_cards(words, "나스닥은 1.8% 상승했고, 반도체 지수는 3.5% 급등했다.", audio_duration_ms=8000)
    assert [(c.label, c.text, c.direction) for c in cards] == [("반도체", "3.5%", "up")]
    assert dropped == [{"text": "1.8%", "kind": "percent", "reason": "not_sentence_representative"}]


def test_card_direction_down_and_compound_label():
    words = _words(["미국", "10년물", "국채", "금리는", "4.15%로", "소폭", "내렸다."], step=1000)
    cards, _ = plan_number_cards(words, "미국 10년물 국채 금리는 4.15%로 소폭 내렸다.", audio_duration_ms=8000)
    assert [(c.label, c.text, c.direction) for c in cards] == [("국채 금리", "4.15%", "down")]


def test_unmatched_number_is_dropped_not_estimated():
    words = _words(["코스피는", "많이", "올랐다."])
    cards, dropped = plan_number_cards(words, "코스피는 3.5% 올랐다.", audio_duration_ms=2000)
    assert cards == []
    assert dropped == [{"text": "3.5%", "kind": "percent", "reason": "no matching word in words.json"}]


def test_number_card_cap_scales_with_length():
    texts = [t for i in range(1, 11) for t in (f"{i}.5%", "올랐다.")]
    words = _words(texts, step=3000)
    cards, dropped = plan_number_cards(words, " ".join(texts), audio_duration_ms=60_000)
    assert len(cards) == 60_000 // MS_PER_CARD == 8
    assert sum(d["reason"] == "max_cards" for d in dropped) == 2
    assert [c.start_ms for c in cards] == sorted(c.start_ms for c in cards)


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
    cues = plan_cues(segments, audio_duration_ms=3000, emoticon_dir=EMOTICON_DIR)
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


@pytest.mark.parametrize(
    "sentence,forbidden",
    [
        ("미국 10년물 국채 금리는 4.15%로 소폭 내렸다.", "32_매파동결_국채금리급등.png"),
        ("코스피는 외국인 순매수 1조 2천억 원에 힘입어 0.9% 오른 2,710포인트에 거래를 마쳤다.", "11_물타기가즈아_하락매수.png"),
        ("실적 시즌을 앞두고 반도체주 변동성에 유의할 필요가 있다.", "26_반도체급등_로켓상승.png"),
        ("간밤 뉴욕 증시는 기술주 강세에 힘입어 S&P 500 지수가 1.2% 올랐다.", "37_검색강세_트렌드상승.png"),
        ("엔비디아는 AI 데이터센터 수요 기대에 4.1% 올랐다.", "27_AI계약_승인.png"),
    ],
)
def test_image_never_contradicts_sentence(sentence, forbidden):
    """review.md P0-2/3: 방향이 반대이거나 문장에 없는 사건(급등·계약…)을 그린 이미지는 쓰지 않는다."""
    words = _words(sentence.split())
    segments = build_caption_segments(words, chunk_size=14)
    cues = plan_cues(segments, audio_duration_ms=words[-1].end, emoticon_dir=EMOTICON_DIR)
    assert all(c.emoticon_file_name != f"emoticon/{forbidden}" for c in cues)
    assert len({c.emoticon_file_name for c in cues}) == 1  # 한 문장은 같은 이미지


def test_specific_topic_beats_generic_direction_image():
    words = _words("코스닥은 0.4% 하락하며 혼조세를 보였다.".split())
    cues = plan_cues(build_caption_segments(words, chunk_size=14), audio_duration_ms=5000, emoticon_dir=EMOTICON_DIR)
    assert cues[0].emoticon_file_name == "emoticon/38_혼조세_증시갈림길.png"


def test_recent_image_is_not_repeated_for_next_sentence():
    words = _words("연준이 금리를 동결했다. 연준이 금리를 동결했다.".split())
    cues = plan_cues(build_caption_segments(words, chunk_size=14), audio_duration_ms=5000, emoticon_dir=EMOTICON_DIR)
    assert cues[0].emoticon_file_name != cues[-1].emoticon_file_name


def test_highlight_prefers_unit_number_then_direction_verb():
    words = _words("힘입어 S&P 500 지수가 1.2% 올랐다.".split())
    segments = build_caption_segments(words, chunk_size=14)
    plan_cues(segments, audio_duration_ms=5000, emoticon_dir=EMOTICON_DIR)
    assert segments[0].highlight_keyword == "1.2%"
    words = _words("기술주가 강세를 보였다.".split())
    segments = build_caption_segments(words, chunk_size=14)
    plan_cues(segments, audio_duration_ms=5000, emoticon_dir=EMOTICON_DIR)
    assert segments[0].highlight_keyword == "강세를"


def test_captions_fit_two_lines_and_keep_number_units():
    from md2short.caption_plan import MAX_CAPTION_CHARS
    from md2short.script import fallback_extract

    text = fallback_extract((ROOT / "samples" / "briefing.md").read_text(encoding="utf-8"))
    words = _words(text.split())
    segments = build_caption_segments(words, chunk_size=24)
    assert all(len(s.text) <= MAX_CAPTION_CHARS for s in segments), [s.text for s in segments if len(s.text) > 26]
    assert any("1조 2천억 원" in s.text for s in segments)
    assert " ".join(s.text for s in segments) == text  # 내용 손실 없음


def test_briefing_date_and_opening_subtitle():
    from datetime import date

    from md2short.opening import extract_briefing_date, opening_subtitle
    from md2short.schema import NumberCard

    assert extract_briefing_date("---\ndate: 2026-10-24\n---\n# 브리핑") == date(2026, 10, 24)
    assert extract_briefing_date("# 2026.10.23 마켓 브리핑") == date(2026, 10, 23)
    assert extract_briefing_date("# 2026년 9월 1일 데일리") == date(2026, 9, 1)
    assert extract_briefing_date("# 날짜 없음\n" + "본문\n" * 20 + "2026-01-01") is None
    card = dict(word_start=0, word_end=1, start_ms=0, duration_ms=1, start_frame=0, duration_frames=1)
    cards = [
        NumberCard(text="1.2%", label="S&P 500", direction="up", **card),
        NumberCard(text="4.15%", label="국채 금리", direction="down", **card),
        NumberCard(text="3%", label="반도체", direction="up", **card),
    ]
    assert opening_subtitle(cards) == "S&P 500 ▲1.2% · 국채 금리 ▼4.15%"
    assert opening_subtitle([], "코스피가 올랐습니다.") == "코스피가 올랐습니다."


def test_card_label_when_sp500_is_split_into_words():
    words = _words(["S&P", "500", "지수가", "1.2%", "올랐다."], step=1000)
    cards, _ = plan_number_cards(words, "S&P 500 지수가 1.2% 올랐다.", audio_duration_ms=6000)
    assert [(c.label, c.text) for c in cards][0] == ("S&P 500", "1.2%")


def test_split_prefers_phrase_boundary():
    from md2short.script import fallback_extract

    text = fallback_extract((ROOT / "samples" / "briefing.md").read_text(encoding="utf-8"))
    segments = build_caption_segments(_words(text.split()), chunk_size=24)
    texts = [s.text for s in segments]
    assert not any(t.endswith(("데이터센터", "수요")) for t in texts), texts


def test_exchange_rate_drop_does_not_get_crying_tiger():
    words = _words("원·달러 환율은 1,372원으로 5원 하락했다.".split())
    cues = plan_cues(build_caption_segments(words, chunk_size=14), audio_duration_ms=5000, emoticon_dir=EMOTICON_DIR)
    assert all("04_나도울고싶어" not in c.emoticon_file_name and "15_존버" not in c.emoticon_file_name for c in cues)


def test_generic_images_rotate_across_the_video():
    sentences = ["코스피가 올랐다."] * 1 + ["코스닥이 올랐다.", "다우가 올랐다.", "나스닥이 올랐다.", "항셍이 올랐다."]
    words = _words(" ".join(sentences).split())
    cues = plan_cues(build_caption_segments(words, chunk_size=14), audio_duration_ms=9000, emoticon_dir=EMOTICON_DIR)
    files = [c.emoticon_file_name for c in cues]
    assert len(set(files)) >= 3, files
