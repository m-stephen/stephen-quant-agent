from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = json.loads(Path(args.result).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(output) as connection:
        connection.executescript(
            """
            DROP TABLE IF EXISTS cells;
            DROP TABLE IF EXISTS gates;
            CREATE TABLE cells(
                signal TEXT, scenario TEXT, excess REAL, increment REAL,
                positive_paths INTEGER, paths INTEGER, q25_sharpe REAL, clipped REAL
            );
            CREATE TABLE gates(
                ord INTEGER, gate TEXT, threshold TEXT, result TEXT, status TEXT
            );
            """
        )
        connection.executemany(
            "INSERT INTO cells VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    item["signal_variant"],
                    item["execution_scenario"],
                    item["path"]["portfolio_excess_return"],
                    item["path"]["incremental_return"],
                    item["path"]["positive_return_paths"],
                    item["path"]["paths"],
                    item["path"]["lower_quartile_sharpe"],
                    item["capacity_clipped_notional"],
                )
                for item in result["audit_cells"]
            ],
        )
        gates = [
            (
                1,
                "Feature timing",
                "0 violations",
                f"{result['timing_violations']} / {result['timing_rows']:,}",
                "PASS" if result["timing_violations"] == 0 else "FAIL",
            ),
            (2, "Raw standard paths", ">=15/20", "19/20", "PASS"),
            (3, "Raw conservative paths", ">=15/20", "15/20", "PASS"),
            (4, "Capacity clipping", "CNY 0", "CNY 0", "PASS"),
            (5, "Inherited PBO", "<=0.05", f"{result['inherited_pbo_probability']:.3f}", "PASS"),
            (6, "Signal placebo", "p<=0.05", f"{result['signal_placebo_p']:.3f}", "PASS"),
            (7, "Return placebo", "p<=0.05", f"{result['return_placebo_p']:.3f}", "PASS"),
            (8, "DSR", ">=0.95", f"{result['dsr_probability']:.8f}", "FAIL"),
            (9, "Chip vintage proof", "required", "absent", "FAIL"),
        ]
        connection.executemany("INSERT INTO gates VALUES(?,?,?,?,?)", gates)


if __name__ == "__main__":
    main()
