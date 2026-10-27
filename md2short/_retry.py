"""외부 API 재시도 래퍼 (docs/architecture.md §7: 3회 재시도, 0.5/1.0/2.0s backoff)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

BACKOFF_SECONDS = (0.5, 1.0, 2.0)


class ExternalAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _retryable(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    timeout: float,
    backoff: tuple[float, ...] = BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """POST 1회 + 실패 시 len(backoff)회 재시도. 재시도 불가 4xx는 즉시 실패."""
    last_error: str = ""
    last_status: int | None = None
    last_body: str | None = None
    for attempt in range(len(backoff) + 1):
        try:
            response = client.post(url, timeout=timeout, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error, last_status, last_body = f"{type(exc).__name__}: {exc}", None, None
        else:
            if response.status_code < 400:
                return response
            last_status, last_body = response.status_code, response.text[:2000]
            last_error = f"HTTP {response.status_code}"
            if not _retryable(response.status_code):
                break
        if attempt < len(backoff):
            sleep(backoff[attempt])
    raise ExternalAPIError(f"POST {url} failed: {last_error}", status_code=last_status, body=last_body)
