"""Scribe 발음형 숫자·약어 → 원문 표시형 복원 (docs/architecture.md §1.2, §2.2).

표시 텍스트만 바꾼다. 단어 개수·순서·타이밍은 `words.json`과 1:1로 유지한다:
여러 단어에 걸친 매칭이면 첫 단어에 원문 표기를 싣고 나머지 단어 텍스트는 비운다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from md2short.schema import Word

ACRONYM_MATCH_THRESHOLD = 0.86
GROUPED_NUMBER_THRESHOLD = 0.84
ACRONYM_MAX_SCAN_WORDS = 96
MAX_RUN_WORDS = 4
MAX_PARTICLE_CHARS = 2

_ACRONYM_TOKEN_RE = re.compile(r"[A-Z][A-Za-z&]*(?:\s?\d+)?")
_NUMBER_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?\s?(?:%|퍼센트|포인트|p\b)?")
_LETTERS = {
    "A": "에이", "B": "비", "C": "씨", "D": "디", "E": "이", "F": "에프", "G": "지", "H": "에이치", "I": "아이",
    "J": "제이", "K": "케이", "L": "엘", "M": "엠", "N": "엔", "O": "오", "P": "피", "Q": "큐", "R": "알", "S": "에스",
    "T": "티", "U": "유", "V": "브이", "W": "더블유", "X": "엑스", "Y": "와이", "Z": "지", "&": "앤",
}
# Scribe가 흔히 내는 한글 음역 단축형
_ACRONYM_KO_VARIANTS = {"에센피": "에스앤피", "에스엔피": "에스앤피", "에쓰앤피": "에스앤피"}
_DIGITS = "영일이삼사오육칠팔구"
_SMALL_UNITS = ((1000, "천"), (100, "백"), (10, "십"))
_BIG_UNITS = ((10**12, "조"), (10**8, "억"), (10**4, "만"))
_KEEP_RE = re.compile(r"[가-힣0-9]")


def _read_under_10000(n: int) -> str:
    out = ""
    for value, name in _SMALL_UNITS:
        q, n = divmod(n, value)
        if q:
            out += ("" if q == 1 else _DIGITS[q]) + name
    if n:
        out += _DIGITS[n]
    return out


def read_number(text: str) -> str:
    """'2,710' → '이천칠백십', '0.9' → '영점구', '5830' → '오천팔백삼십'."""
    raw = text.replace(",", "")
    integer, _, frac = raw.partition(".")
    n = int(integer or "0")
    if n == 0:
        out = "영"
    else:
        out = ""
        for value, name in _BIG_UNITS:
            q, n = divmod(n, value)
            if q:
                out += _read_under_10000(q) + name
        out += _read_under_10000(n)
    if frac:
        out += "점" + "".join(_DIGITS[int(d)] for d in frac)
    return out


def spoken_form(token: str) -> str:
    out = []
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?|[A-Za-z&]|%|퍼센트|포인트|[가-힣]+", token):
        piece = m.group(0)
        if piece[0].isdigit():
            out.append(read_number(piece))
        elif piece == "%":
            out.append("퍼센트")
        elif len(piece) == 1 and piece.upper() in _LETTERS:
            out.append(_LETTERS[piece.upper()])
        else:
            out.append(piece)
    return "".join(out)


def _compact(text: str) -> str:
    out = "".join(_KEEP_RE.findall(text))
    for variant, canonical in _ACRONYM_KO_VARIANTS.items():
        out = out.replace(variant, canonical)
    return out


@dataclass(frozen=True)
class DisplayToken:
    display: str
    spoken: str
    threshold: float


def extract_display_tokens(script_text: str) -> list[DisplayToken]:
    tokens: list[DisplayToken] = []
    seen: set[str] = set()
    for regex, threshold in ((_ACRONYM_TOKEN_RE, ACRONYM_MATCH_THRESHOLD), (_NUMBER_TOKEN_RE, GROUPED_NUMBER_THRESHOLD)):
        for m in regex.finditer(script_text):
            display = m.group(0).strip()
            if display in seen or len(display) < 2 and not display.isdigit():
                continue
            seen.add(display)
            tokens.append(DisplayToken(display, spoken_form(display), threshold))
    # 긴 토큰 우선(‘S&P 500’이 ‘500’보다 먼저 매칭되도록)
    return sorted(tokens, key=lambda t: len(t.spoken), reverse=True)


def _match_run(words: list[Word], i: int, token: DisplayToken) -> tuple[int, str] | None:
    """words[i:i+k] 접두가 token 발음과 충분히 비슷하면 (k, 조사) 반환."""
    target = token.spoken
    first = _compact(words[i].text) if i < len(words) else ""
    # 앞 단어가 매칭 대상의 시작과 맞물려야 한다(‘오른’+‘오천…’ 같은 앞붙음 방지).
    if not first or first[0] != target[0] or (
        len(first) <= len(target) and SequenceMatcher(None, first, target[: len(first)]).ratio() < 0.75
    ):
        return None
    joined = ""
    for k in range(1, MAX_RUN_WORDS + 1):
        if i + k > len(words):
            break
        joined += _compact(words[i + k - 1].text)
        if len(joined) < len(target) - 1:
            continue
        best: tuple[float, str] | None = None
        for extra in range(0, min(MAX_PARTICLE_CHARS, len(joined) - 1) + 1):
            head, tail = joined[: len(joined) - extra], joined[len(joined) - extra :]
            ratio = SequenceMatcher(None, head, target).ratio()
            if ratio >= token.threshold and not any(ch.isdigit() for ch in tail) and (best is None or ratio > best[0]):
                best = (ratio, tail)
        if best is not None:
            return k, best[1]
        if len(joined) > len(target) + MAX_PARTICLE_CHARS:
            break
    return None


def apply_numeric_display_overrides(words: list[Word], script_text: str) -> list[Word]:
    """표시용 단어 목록. 길이·타이밍은 입력과 동일하다."""
    out = [w.model_copy() for w in words]
    tokens = extract_display_tokens(script_text)
    if not tokens:
        return out
    for i in range(len(out)):
        if not out[i].text or any(ch.isdigit() or ("A" <= ch <= "Z") for ch in out[i].text):
            continue  # 이미 원문 표기거나 앞 매칭에 흡수된 단어
        for token in tokens:
            if _compact(token.display) == _compact(out[i].text):
                break
            hit = _match_run(out[i : i + ACRONYM_MAX_SCAN_WORDS], 0, token)
            if hit is None:
                continue
            k, particle = hit
            trailing = re.sub(r"[가-힣0-9A-Za-z]+", "", out[i + k - 1].text)  # 마침표 등 구두점 보존
            out[i] = out[i].model_copy(update={"text": f"{token.display}{particle}{trailing}"})
            for j in range(i + 1, i + k):
                out[j] = out[j].model_copy(update={"text": ""})
            break
    return out
