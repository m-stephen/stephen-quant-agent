from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from stephen_quant.qmt.pit_staging import (
    PIT_STAGING_VERSION,
    ingest_alphapai_announcement_partitions,
    write_pit_bundle,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a candidate-only AlphaPai PIT bundle")
    parser.add_argument("--config", required=True, help="Git-ignored local JSON configuration")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    partitions = []
    source_files = []
    for partition in config["partitions"]:
        responses = []
        for page_number, raw_path in enumerate(partition["pages"], start=1):
            path = Path(raw_path).resolve()
            raw = path.read_bytes()
            responses.append(json.loads(raw.decode("utf-8-sig")))
            source_files.append({
                "partition": partition["name"],
                "page": page_number,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        partitions.append(tuple(responses))
    rows, ledger = ingest_alphapai_announcement_partitions(
        tuple(partitions), query_start=config["query_start"], query_end=config["query_end"],
        ingested_at=config["ingested_at"],
    )
    bundle_hash = write_pit_bundle(
        financial=rows, industry=(), corporate_actions=(), output=output_dir / "pit-bundle.json"
    )
    (output_dir / "remote-retrieval-ledger.json").write_text(
        ledger.to_json() + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": PIT_STAGING_VERSION,
        "query_start": config["query_start"],
        "query_end": config["query_end"],
        "ingested_at": config["ingested_at"],
        "bundle_sha256": bundle_hash,
        "inferential_trial_delta": 0,
        "formal_research_eligible": False,
        "files": source_files,
    }
    (output_dir / "source-page-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "success", "rows": len(rows), "bundle_sha256": bundle_hash,
        "inferential_trial_delta": 0, "formal_research_eligible": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
