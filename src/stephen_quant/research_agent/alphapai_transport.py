from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .models import ResearchAgentError


@dataclass(frozen=True)
class AlphaPaiTransportResponse:
    """Transport-neutral result for one complete HTTP or streamed response."""

    status_code: int
    payload: dict[str, object]
    stream_complete: bool = True
    retry_after_seconds: float | None = None


class AlphaPaiTransport(Protocol):
    def __call__(
        self, endpoint: str, payload: dict[str, object], timeout_seconds: float
    ) -> AlphaPaiTransportResponse: ...


def request_alphapai_with_retry(
    transport: AlphaPaiTransport,
    *,
    endpoint: str,
    request_payload: dict[str, object],
    timeout_seconds: float = 30.0,
    max_attempts: int = 3,
    base_backoff_seconds: float = 0.25,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Call an injected read-only client with bounded retries and strict completeness."""

    if not endpoint.strip():
        raise ResearchAgentError("AlphaPai endpoint cannot be empty")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ResearchAgentError("AlphaPai timeout must be finite and positive")
    if max_attempts < 1:
        raise ResearchAgentError("AlphaPai max_attempts must be positive")
    if not math.isfinite(base_backoff_seconds) or base_backoff_seconds < 0:
        raise ResearchAgentError("AlphaPai backoff must be finite and non-negative")

    last_error = "unknown transport failure"
    for attempt in range(1, max_attempts + 1):
        retry_after: float | None = None
        try:
            response = transport(endpoint.strip(), request_payload, timeout_seconds)
        except TimeoutError:
            last_error = "request timed out"
            retryable = True
        else:
            if response.status_code == 200:
                if not response.stream_complete:
                    raise ResearchAgentError(
                        "AlphaPai streaming response is incomplete; partial data was discarded"
                    )
                if not isinstance(response.payload, dict) or not response.payload:
                    raise ResearchAgentError("AlphaPai transport returned an empty response")
                return response.payload
            retryable = response.status_code == 429 or response.status_code >= 500
            last_error = f"HTTP {response.status_code}"
            retry_after = response.retry_after_seconds

        if not retryable or attempt == max_attempts:
            raise ResearchAgentError(
                f"AlphaPai request failed after {attempt} attempt(s): {last_error}"
            )
        delay = base_backoff_seconds * (2 ** (attempt - 1))
        if retry_after is not None:
            delay = max(delay, retry_after)
        sleeper(delay)

    raise AssertionError("unreachable AlphaPai retry state")
