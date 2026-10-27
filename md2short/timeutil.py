"""ms ↔ frame 변환의 유일한 위치 (AGENTS.md §4.2).

정수 연산 half-up 반올림. Python `round()`(banker's)와 JS `Math.round`의
불일치를 피하려고 Remotion 쪽에는 변환 코드를 두지 않는다.
"""

from __future__ import annotations

from md2short.schema import FPS


def ms_to_frames(ms: int, fps: int = FPS) -> int:
    return (int(ms) * fps * 2 + 1000) // 2000


def frames_to_ms(frames: int, fps: int = FPS) -> int:
    return (int(frames) * 1000 * 2 + fps) // (2 * fps)
