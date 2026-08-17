from __future__ import annotations

import argparse
import json
from pathlib import Path

from stephen_quant.qmt.source_completion import (
    build_source_completion_report,
    write_source_completion_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the QD source-completion gate report")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = build_source_completion_report(Path(args.config))
    report_hash = write_source_completion_report(report, Path(args.output))
    print(json.dumps({
        "status": "passed" if report.gate_pass else "blocked",
        "report_sha256": report_hash, "blockers": report.blockers,
        "formal_research_eligible": False,
    }, ensure_ascii=False, sort_keys=True))
    if not report.gate_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
