from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .models import ResearchAgentError

ALPHAPAI_CACHE_VERSION = "alphapai-point-in-time-cache-1.0.0"
_SECRET_MARKERS = ("api_key", "apikey", "app-agent", "authorization", "password", "secret", "token")


def _canonical(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _aware(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchAgentError(f"invalid AlphaPai {field}: {value}") from exc
    if parsed.tzinfo is None:
        raise ResearchAgentError(f"AlphaPai {field} must include a timezone")
    return parsed


def _contains_secret(payload: object) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker.replace("-", "_") in normalized for marker in _SECRET_MARKERS):
                return True
            if _contains_secret(value):
                return True
    elif isinstance(payload, (list, tuple)):
        return any(_contains_secret(item) for item in payload)
    return False


def _published_date(reference: dict[str, object]) -> date | None:
    value = reference.get("publishDate")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError as exc:
        raise ResearchAgentError(f"invalid AlphaPai reference publishDate: {value}") from exc


@dataclass(frozen=True)
class AlphaPaiCacheEntry:
    cache_version: str
    endpoint: str
    request_payload: dict[str, object]
    request_sha256: str
    response_sha256: str
    fetched_at: str
    knowledge_cutoff_at: str
    response: dict[str, object]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False)


def capture_alphapai_response(
    *,
    endpoint: str,
    request_payload: dict[str, object],
    response: dict[str, object],
    fetched_at: str,
    knowledge_cutoff_at: str,
) -> AlphaPaiCacheEntry:
    """Validate and freeze one already-received AlphaPai response without credentials."""

    if not endpoint.strip():
        raise ResearchAgentError("AlphaPai endpoint cannot be empty")
    if _contains_secret(request_payload):
        raise ResearchAgentError("AlphaPai cache request contains a credential-like field")
    fetched = _aware(fetched_at, "fetched_at")
    cutoff = _aware(knowledge_cutoff_at, "knowledge_cutoff_at")
    if response.get("code") != 200000:
        message = response.get("message", response.get("msg", "unknown error"))
        raise ResearchAgentError(f"AlphaPai business request failed: {message}")
    if endpoint == "agent" and (
        not isinstance(response.get("answer"), str) or not str(response["answer"]).strip()
    ):
        raise ResearchAgentError("AlphaPai Agent cache requires a non-empty answer")
    references = response.get("references", [])
    if not isinstance(references, list):
        raise ResearchAgentError("AlphaPai references must be an array")
    for reference in references:
        if not isinstance(reference, dict):
            raise ResearchAgentError("AlphaPai reference must be an object")
        published = _published_date(reference)
        if published is not None and published > cutoff.date():
            raise ResearchAgentError("AlphaPai reference exceeds the declared knowledge cutoff")
    if endpoint == "hot_topics":
        data = response.get("data")
        if not isinstance(data, list):
            raise ResearchAgentError("AlphaPai hot-topics cache requires list data")
        for board in data:
            if not isinstance(board, dict) or not isinstance(board.get("tradingDay"), str):
                raise ResearchAgentError("AlphaPai hot-topics board is malformed")
            try:
                board_date = date.fromisoformat(str(board["tradingDay"]))
            except ValueError as exc:
                raise ResearchAgentError("AlphaPai hot-topics date is invalid") from exc
            if board_date > cutoff.date():
                raise ResearchAgentError("AlphaPai hot-topics data exceeds knowledge cutoff")
    # Fetch time is the earliest time this project can prove it possessed the response.
    # It may be later than the requested knowledge cutoff, but historical use will fail closed.
    return AlphaPaiCacheEntry(
        cache_version=ALPHAPAI_CACHE_VERSION,
        endpoint=endpoint.strip(),
        request_payload=request_payload,
        request_sha256=_sha256({"endpoint": endpoint.strip(), "request": request_payload}),
        response_sha256=_sha256(response),
        fetched_at=fetched.isoformat(),
        knowledge_cutoff_at=cutoff.isoformat(),
        response=response,
    )


def write_alphapai_cache(entry: AlphaPaiCacheEntry, cache_dir: str | Path) -> Path:
    directory = Path(cache_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{entry.request_sha256}.json"
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != entry.to_json() + "\n":
            raise ResearchAgentError("AlphaPai cache entry is immutable and already differs")
        return path
    path.write_text(entry.to_json() + "\n", encoding="utf-8", newline="\n")
    return path


def load_alphapai_cache(
    cache_dir: str | Path,
    *,
    endpoint: str,
    request_payload: dict[str, object],
    decision_at: str,
) -> AlphaPaiCacheEntry:
    """Load an exact frozen response; never performs an online cache-miss fallback."""

    if _contains_secret(request_payload):
        raise ResearchAgentError("AlphaPai cache request contains a credential-like field")
    decision = _aware(decision_at, "decision_at")
    request_hash = _sha256({"endpoint": endpoint.strip(), "request": request_payload})
    path = Path(cache_dir).expanduser().resolve() / f"{request_hash}.json"
    if not path.is_file():
        raise ResearchAgentError("AlphaPai cache miss; online fallback is forbidden")
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        entry = AlphaPaiCacheEntry(**payload)
    except (OSError, TypeError, json.JSONDecodeError) as exc:
        raise ResearchAgentError("AlphaPai cache entry is malformed") from exc
    if entry.cache_version != ALPHAPAI_CACHE_VERSION:
        raise ResearchAgentError("unsupported AlphaPai cache version")
    if entry.request_sha256 != request_hash:
        raise ResearchAgentError("AlphaPai cache request hash mismatch")
    if entry.response_sha256 != _sha256(entry.response):
        raise ResearchAgentError("AlphaPai cache response hash mismatch")
    if _aware(entry.fetched_at, "fetched_at") > decision:
        raise ResearchAgentError("AlphaPai response was fetched after the decision time")
    if _aware(entry.knowledge_cutoff_at, "knowledge_cutoff_at") > decision:
        raise ResearchAgentError("AlphaPai knowledge cutoff exceeds the decision time")
    return entry
