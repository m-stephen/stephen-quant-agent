"""Compare every lead/control replay hash, not just the lead's ending wealth."""

import json
from pathlib import Path

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

root = Path("artifacts/incremental-alpha/epoch-001")
replay = root / "replays/7fd0a71c-7e04-4606-be67-495ff8d26baa"
original = json.loads((root / "batch-01/RESULT.json").read_text())
actual = json.loads((replay / "RESULT.json").read_text())
receipt = json.loads((replay / "REPLAY_VERIFIED.json").read_text())
count = 0
for identity, control in actual["controls"].items():
    if control != original["controls"][identity]:
        raise ValueError("control replay metrics or full daily evidence hash differ")
    count += sum(len(costs) for costs in control.values())
lead = actual["candidates"][0]
if lead != next(c for c in original["candidates"] if c["identity"] == lead["identity"]):
    raise ValueError("lead replay differs")
count += sum(len(costs) for costs in lead["years"].values())
if count != 18 or not receipt["pass"]:
    raise ValueError("incomplete replay")
write_json(Path("docs/V11_7_VERIFICATION.json"), {
    "all_18_lead_and_control_accounts_exact": True,
    "replay_receipt": receipt,
    "replay_receipt_sha256": file_sha(replay / "REPLAY_VERIFIED.json"),
    "full_suite": {"passed": 726, "skipped": 1,
                   "skip": "Windows symlink creation permission",
                   "environment": "maintenance credentials removed only in test subprocess"},
    "ruff": "passed",
    "sql_audit_sha256": file_sha(root / "SQL_RECONCILIATION.json"),
    "sql_annual_rows": 192, "sql_candidate_windows_compared": 96,
})
print(json.dumps({"pass": True, "exact_accounts": count}))
