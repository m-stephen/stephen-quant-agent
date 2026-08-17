from __future__ import annotations

import argparse
import json
from pathlib import Path

from stephen_quant.qmt.corporate_action_maintenance import (
    merge_corporate_action_operations,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    result = merge_corporate_action_operations(Path(args.config))
    print(json.dumps({
        "status": "success", "rows": result.rows,
        "operation_manifests": result.operation_manifests,
        "bundle_sha256": result.bundle_sha256,
        "manifest_sha256": result.manifest_sha256,
        "formal_research_eligible": False, "inferential_trial_delta": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
