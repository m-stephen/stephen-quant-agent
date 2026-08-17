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
    if "document_hashes" in config:
        raise ValueError("document_hashes is forbidden; provide document_files for byte verification")
    document_files = config.get("document_files", {})
    document_hashes = {}
    document_evidence = []
    for transient_hash, document_path in document_files.items():
        path = Path(document_path).resolve()
        raw = path.read_bytes()
        document_hashes[transient_hash] = hashlib.sha256(raw).hexdigest()
        document_evidence.append({
            "transient_id_hash": transient_hash, "size": len(raw),
            "sha256": document_hashes[transient_hash],
        })
    quarantined_ids = set(config.get("quarantined_transient_id_hashes", []))
    output_root = Path(config["output_dir"]).resolve()
    operation_id = str(config["operation_id"]).strip()
    if not operation_id or operation_id in {".", ".."} or Path(operation_id).name != operation_id:
        raise ValueError("operation_id must be one safe path component")
    partitions = []
    source_files = []
    source_paths = [
        Path(raw_path).resolve()
        for partition in config["partitions"]
        for raw_path in partition["pages"]
    ] + [Path(path).resolve() for path in document_files.values()]
    if any(output_root == path.parent or output_root.is_relative_to(path.parent)
           for path in source_paths):
        raise ValueError("output_dir must be physically disjoint from every source-page directory")
    for partition in config["partitions"]:
        responses = []
        for raw_path in partition["pages"]:
            path = Path(raw_path).resolve()
            raw = path.read_bytes()
            response = json.loads(raw.decode("utf-8-sig"))
            envelope = response.get("data")
            if not isinstance(envelope, dict):
                raise TypeError("source page has no pagination envelope")
            page_number = int(envelope.get("pageNum", 0))
            total_pages = int(envelope.get("totalPageNum", 0))
            total_size = int(envelope.get("totalSize", -1))
            page_items = envelope.get("data")
            empty_partition = page_number == 1 and total_pages == 0 and total_size == 0 \
                and page_items == []
            if page_number <= 0 or total_pages < 0 or total_size < 0 or (
                total_pages == 0 and not empty_partition
            ):
                raise ValueError("source page has invalid pagination metadata")
            for item in envelope.get("data", []):
                transient_id = str(item.get("announcementId") or "")
                transient_hash = hashlib.sha256(transient_id.encode()).hexdigest()
                if transient_hash in document_hashes:
                    item["sourceDocumentHash"] = document_hashes[transient_hash]
                if transient_hash in quarantined_ids:
                    item["_pitQuarantined"] = True
            responses.append(response)
            source_files.append({
                "partition": partition["name"],
                "page": page_number,
                "total_pages": total_pages,
                "total_size": total_size,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            })
        partitions.append(tuple(responses))
    rows, ledger = ingest_alphapai_announcement_partitions(
        tuple(partitions), query_start=config["query_start"], query_end=config["query_end"],
        ingested_at=config["ingested_at"],
    )
    operation_dir = output_root / operation_id
    operation_dir.mkdir(parents=True, exist_ok=False)
    bundle_hash = write_pit_bundle(
        financial=rows, industry=(), corporate_actions=(),
        output=operation_dir / "pit-bundle.json",
    )
    with (operation_dir / "remote-retrieval-ledger.json").open(
        "x", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(ledger.to_json() + "\n")
    manifest = {
        "schema_version": PIT_STAGING_VERSION,
        "operation_id": operation_id,
        "query_start": config["query_start"],
        "query_end": config["query_end"],
        "ingested_at": config["ingested_at"],
        "bundle_sha256": bundle_hash,
        "inferential_trial_delta": 0,
        "formal_research_eligible": False,
        "quarantined_source_records": ledger.quarantined_source_records,
        "quarantined_transient_id_hashes": sorted(quarantined_ids),
        "quarantine_set_sha256": hashlib.sha256(
            json.dumps(sorted(quarantined_ids), separators=(",", ":")).encode()
        ).hexdigest(),
        "document_evidence": sorted(
            document_evidence, key=lambda row: row["transient_id_hash"]
        ),
        "files": sorted(source_files, key=lambda row: (row["partition"], row["page"])),
    }
    with (operation_dir / "source-page-manifest.json").open(
        "x", encoding="utf-8", newline="\n"
    ) as handle:
        handle.write(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
    print(json.dumps({
        "status": "success", "rows": len(rows), "bundle_sha256": bundle_hash,
        "inferential_trial_delta": 0, "formal_research_eligible": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
