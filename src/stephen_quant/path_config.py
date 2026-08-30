from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


class PathConfigError(ValueError):
    """Raised when a machine-local path configuration is invalid."""


ALLOWED_PATH_KEYS = frozenset(
    {
        "qd_audit_snapshot_root",
        "qd_audit_allowlist_manifest",
        "qd_audit_output_dir",
        "qd_single_user_data_root",
        "qd_single_user_manifest_dir",
        "qd_single_user_ledger_dir",
        "qd_data_maintenance_control_manifest",
        "qd_daily_dir",
        "qd_fundamental_dir",
        "qd_concept_membership_csv",
        "csi300_csv",
        "csi500_csv",
        "dynamic_membership_jsonl",
        "discovery_stock_file",
        "alphapai_cache_dir",
        "qd_auction_dir",
        "qd_fund_flow_dir",
        "qd_industry_dir",
        "qd_margin_dir",
        "qd_chip_dir",
        "qd_limit_event_dir",
        "qd_asset_root",
        "qd_warehouse_root",
        "qd_7zip_executable",
    }
)


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PathConfigError(f"duplicate path-config key: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class LocalPathConfig:
    source: Path | None
    paths: dict[str, Path]

    def choose(self, key: str, cli_value: str | None, option: str) -> str:
        """Prefer an explicit CLI value, otherwise use the local ignored config."""

        if cli_value:
            return str(Path(cli_value).expanduser().resolve())
        configured = self.paths.get(key)
        if configured is None:
            raise PathConfigError(
                f"{option} is required, either directly or through --paths-config key {key!r}"
            )
        return str(configured)


def load_local_path_config(source: str | Path | None) -> LocalPathConfig:
    if source is None:
        return LocalPathConfig(source=None, paths={})
    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise PathConfigError(f"path config does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except json.JSONDecodeError as exc:
        raise PathConfigError(f"invalid path-config JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise PathConfigError("path config must be an object with version 1")
    raw_paths = payload.get("paths")
    if not isinstance(raw_paths, dict):
        raise PathConfigError("path config must contain a paths object")
    unknown = sorted(set(raw_paths) - ALLOWED_PATH_KEYS)
    if unknown:
        raise PathConfigError(f"unknown path-config keys: {unknown}")
    resolved: dict[str, Path] = {}
    for key, value in raw_paths.items():
        if not isinstance(value, str) or not value.strip():
            raise PathConfigError(f"path-config value {key!r} must be a non-empty string")
        expanded = Path(os.path.expandvars(value.strip())).expanduser()
        resolved[key] = (
            expanded.resolve() if expanded.is_absolute() else (path.parent / expanded).resolve()
        )
    return LocalPathConfig(source=path, paths=resolved)
