from __future__ import annotations

import argparse
import json
from pathlib import Path

from stephen_quant.qmt.authoritative_sources import build_authoritative_source_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Build authoritative candidate-only PIT sources")
    parser.add_argument("--config", required=True, help="Git-ignored local JSON configuration")
    args = parser.parse_args()
    result = build_authoritative_source_bundle(Path(args.config))
    print(json.dumps({
        "status": "success",
        "operation_id": result.operation_id,
        "bundle_sha256": result.bundle_sha256,
        "manifest_sha256": result.manifest_sha256,
        "industry_rows": result.industry_rows,
        "corporate_action_rows": result.corporate_action_rows,
        "announcement_links": result.announcement_links,
        "inferential_trial_delta": 0,
        "formal_research_eligible": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
