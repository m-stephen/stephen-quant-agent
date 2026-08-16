from __future__ import annotations

from collections.abc import Iterator

import pytest

from stephen_quant.research_agent import (
    AlphaPaiTransportResponse,
    ResearchAgentError,
    request_alphapai_with_retry,
)


class SequenceTransport:
    def __init__(self, outcomes: list[AlphaPaiTransportResponse | Exception]) -> None:
        self._outcomes: Iterator[AlphaPaiTransportResponse | Exception] = iter(outcomes)
        self.calls = 0

    def __call__(
        self, endpoint: str, payload: dict[str, object], timeout_seconds: float
    ) -> AlphaPaiTransportResponse:
        self.calls += 1
        outcome = next(self._outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_alphapai_transport_retries_timeout_and_rate_limit() -> None:
    transport = SequenceTransport(
        [
            TimeoutError(),
            AlphaPaiTransportResponse(429, {}, retry_after_seconds=0.2),
            AlphaPaiTransportResponse(200, {"code": 200000, "data": []}),
        ]
    )
    sleeps: list[float] = []
    result = request_alphapai_with_retry(
        transport,
        endpoint="hot_topics",
        request_payload={"limit": 10},
        max_attempts=3,
        base_backoff_seconds=0.1,
        sleeper=sleeps.append,
    )
    assert result["code"] == 200000
    assert transport.calls == 3
    assert sleeps == [0.1, 0.2]


def test_alphapai_transport_fails_closed_on_incomplete_stream() -> None:
    transport = SequenceTransport(
        [AlphaPaiTransportResponse(200, {"code": 200000}, stream_complete=False)]
    )
    with pytest.raises(ResearchAgentError, match="incomplete"):
        request_alphapai_with_retry(
            transport,
            endpoint="agent",
            request_payload={"question": "sample"},
            sleeper=lambda _: None,
        )


def test_alphapai_transport_stops_after_retry_budget() -> None:
    transport = SequenceTransport([TimeoutError(), TimeoutError()])
    with pytest.raises(ResearchAgentError, match="after 2 attempt"):
        request_alphapai_with_retry(
            transport,
            endpoint="agent",
            request_payload={"question": "sample"},
            max_attempts=2,
            sleeper=lambda _: None,
        )
