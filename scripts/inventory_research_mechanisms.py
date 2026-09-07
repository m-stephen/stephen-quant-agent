"""Explicit source-only inventory; never imports generators or reads market artifacts."""

import argparse
import json
from pathlib import Path

from stephen_quant.mechanism_inventory import source_inventory

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = source_inventory(Path.cwd())
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "source_files": len(report["files"]),
                "source_units": len(report["units"]),
                "sha256": report["inventory_sha256"],
                "market_rows_read": 0,
                "empirical_trials_added": 0,
                "not_complete_runtime_enumeration": True,
            }
        )
    )
