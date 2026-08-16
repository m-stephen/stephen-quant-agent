from __future__ import annotations

import json
from pathlib import Path

import pytest

from stephen_quant.research_agent import (
    ResearchAgentError,
    capture_alphapai_response,
    load_alphapai_cache,
    write_alphapai_cache,
)


def _request() -> dict[str, object]:
    return {"mode": 11, "question": "银行行业一页纸", "industry": "银行"}


def _response() -> dict[str, object]:
    return {
        "code": 200000,
        "message": "success",
        "questionId": "question-1",
        "answer": "# 银行行业研究",
        "references": [
            {
                "type": "report",
                "title": "银行业研究",
                "publishDate": "2024-01-10",
                "url": "https://example.invalid/report",
            }
        ],
    }


def _provenance() -> dict[str, str]:
    return {
        "prompt_version": "industry-one-page-v1",
        "model_identifier": "alphapai-agent",
        "tool_version": "openpai-v1",
    }


def test_alphapai_cache_is_immutable_hashed_and_point_in_time(tmp_path: Path) -> None:
    entry = capture_alphapai_response(
        endpoint="agent",
        provenance=_provenance(),
        request_payload=_request(),
        response=_response(),
        fetched_at="2024-01-15T12:00:00+08:00",
        knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
    )
    path = write_alphapai_cache(entry, tmp_path)
    assert path.name == f"{entry.request_sha256}.json"
    assert write_alphapai_cache(entry, tmp_path) == path

    loaded = load_alphapai_cache(
        tmp_path,
        endpoint="agent",
        provenance=_provenance(),
        request_payload=_request(),
        decision_at="2024-01-16T09:30:00+08:00",
    )
    assert loaded.response_sha256 == entry.response_sha256

    with pytest.raises(ResearchAgentError, match="fetched after"):
        load_alphapai_cache(
            tmp_path,
            endpoint="agent",
            provenance=_provenance(),
            request_payload=_request(),
            decision_at="2024-01-14T09:30:00+08:00",
        )


def test_alphapai_cache_fails_closed_on_miss_tamper_and_secrets(tmp_path: Path) -> None:
    with pytest.raises(ResearchAgentError, match="cache miss"):
        load_alphapai_cache(
            tmp_path,
            endpoint="agent",
            provenance=_provenance(),
            request_payload=_request(),
            decision_at="2024-01-16T09:30:00+08:00",
        )
    with pytest.raises(ResearchAgentError, match="credential"):
        capture_alphapai_response(
            endpoint="agent",
            provenance=_provenance(),
            request_payload={**_request(), "api_key": "must-not-be-cached"},
            response=_response(),
            fetched_at="2024-01-15T12:00:00+08:00",
            knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
        )

    entry = capture_alphapai_response(
        endpoint="agent",
        provenance=_provenance(),
        request_payload=_request(),
        response=_response(),
        fetched_at="2024-01-15T12:00:00+08:00",
        knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
    )
    path = write_alphapai_cache(entry, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["response"]["answer"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ResearchAgentError, match="response hash mismatch"):
        load_alphapai_cache(
            tmp_path,
            endpoint="agent",
            provenance=_provenance(),
            request_payload=_request(),
            decision_at="2024-01-16T09:30:00+08:00",
        )


def test_alphapai_capture_rejects_failed_or_future_knowledge() -> None:
    with pytest.raises(ResearchAgentError, match="business request failed"):
        capture_alphapai_response(
            endpoint="agent",
            provenance=_provenance(),
            request_payload=_request(),
            response={"code": 42900, "message": "limited"},
            fetched_at="2024-01-15T12:00:00+08:00",
            knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
        )
    future = _response()
    future["references"][0]["publishDate"] = "2024-02-01"  # type: ignore[index]
    with pytest.raises(ResearchAgentError, match="knowledge cutoff"):
        capture_alphapai_response(
            endpoint="agent",
            provenance=_provenance(),
            request_payload=_request(),
            response=future,
            fetched_at="2024-01-15T12:00:00+08:00",
            knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
        )


def test_hot_topics_dates_are_bounded_by_cutoff() -> None:
    response = {
        "code": 200000,
        "message": "success",
        "data": [{"tradingDay": "2024-01-16", "instBoardList": []}],
    }
    with pytest.raises(ResearchAgentError, match="exceeds knowledge cutoff"):
        capture_alphapai_response(
            endpoint="hot_topics",
            provenance={
                "prompt_version": "not_applicable",
                "model_identifier": "not_applicable",
                "tool_version": "openpai-hot-topics-v1",
            },
            request_payload={"limit": 1},
            response=response,
            fetched_at="2024-01-15T12:00:00+08:00",
            knowledge_cutoff_at="2024-01-15T00:00:00+08:00",
        )
