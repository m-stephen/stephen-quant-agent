from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
import time
from calendar import monthrange
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from stephen_quant.qmt.pit_staging import CorporateActionPIT, validate_corporate_actions

VERSION = "alphapai-corporate-actions-0.1.0"
SHANGHAI = timezone(timedelta(hours=8))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def retry(call, attempts: int = 10):
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            result = call()
            if isinstance(result, dict) and result.get("code") != 200000:
                raise RuntimeError(f"AlphaPai business error {result.get('code')}")
            return result
        except Exception as exc:  # noqa: BLE001 - provider/network failures are retried uniformly
            error = exc
            if attempt + 1 < attempts:
                delay = 60 if "42900" in str(exc) else min(30, 2 ** attempt)
                time.sleep(delay)
    assert error is not None
    raise error


def month_partitions(start: date, end: date):
    cursor = start.replace(day=1)
    while cursor <= end:
        last = min(end, cursor.replace(day=monthrange(cursor.year, cursor.month)[1]))
        yield cursor, last
        cursor = (last + timedelta(days=1)).replace(day=1)


def local_time(value: str | None, fallback: str) -> tuple[str, str]:
    raw = value or fallback
    parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
    if value:
        return parsed.isoformat(), parsed.isoformat()
    return parsed.isoformat(), (parsed + timedelta(days=1)).isoformat()


def first_date(text: str, labels: tuple[str, ...]) -> str | None:
    compact = re.sub(r"\s+", "", text)
    for label in labels:
        match = re.search(
            label + r"(?:为)?[：:]?(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?",
            compact,
        )
        if match:
            return f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}"
    return None


def table_dates(text: str) -> tuple[str | None, str | None]:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "股权登记日" not in line or not any(token in line for token in ("除权", "除息")):
            continue
        window = " ".join(lines[index:index + 4])
        values = re.findall(r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})", window)
        if len(values) >= 2:
            dates = [f"{int(y):04d}-{int(m):02d}-{int(d):02d}" for y, m, d in values]
            return dates[0], dates[-2] if len(dates) >= 3 else dates[1]
    return None, None


def per_share(text: str, pattern: str) -> str | None:
    match = re.search(pattern, re.sub(r"\s+", "", text))
    if not match:
        return None
    return format(Decimal(match[1].replace(",", "")) / Decimal(10), "f")


def parse_action(item: dict, markdown: str, source_hash: str) -> CorporateActionPIT:
    tags = item.get("stockTag") or []
    if len(tags) != 1 or not tags[0].get("code"):
        raise ValueError("announcement must identify exactly one stock")
    record = first_date(markdown, ("股权登记日", "权益登记日"))
    ex_date = first_date(markdown, ("除权除息日", "除息日", "除权日"))
    table_record, table_ex = table_dates(markdown)
    record = record or table_record
    ex_date = ex_date or table_ex
    if not record or not ex_date:
        raise ValueError("implementation announcement lacks record/ex date")
    announced, available = local_time(item.get("actualPublishTime"), item["publishTime"])
    cash = per_share(markdown, r"每10股[^。；]*?派(?:发)?(?:现金)?(?:红利)?([\d,.]+)元")
    if cash is None:
        direct = re.search(r"每股(?:实际)?派发现金红利(?:为)?(?:人民币)?([\d,.]+)元",
                           re.sub(r"\s+", "", markdown))
        cash = direct[1].replace(",", "") if direct else None
    bonus = per_share(markdown, r"每10股[^。；]*?送([\d,.]+)股")
    transfer = per_share(markdown, r"每10股[^。；]*?转(?:增)?([\d,.]+)股")
    if cash is None and bonus is None and transfer is None:
        raise ValueError("implementation announcement lacks cash/stock distribution ratio")
    split = None
    if bonus is not None or transfer is not None:
        split = format(Decimal(1) + Decimal(bonus or "0") + Decimal(transfer or "0"), "f")
    document_id = digest((item["title"] + "|" + item["publishTime"] + "|" + source_hash).encode())
    return CorporateActionPIT(
        code=tags[0]["code"], event_type="distribution", announcement_at=announced,
        available_at=available, effective_date=ex_date, record_date=record, ex_date=ex_date,
        revision_id=document_id, source_document_id=document_id, source_hash=source_hash,
        cash_dividend_per_share=cash, split_ratio=split,
        parser_version=VERSION,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--metadata-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(args.client_dir).resolve()))
    base = importlib.import_module("alphapai_base")
    command = importlib.import_module("cmd_announcement")
    client = base.AlphaPaiClient(base.require_config())
    root = Path(args.output_root).resolve() / args.operation_id
    root.mkdir(parents=True, exist_ok=False)
    rows: list[CorporateActionPIT] = []
    files: list[dict] = []
    quarantine: list[dict] = []
    seen: set[str] = set()

    for start, end in month_partitions(date.fromisoformat(args.start), date.fromisoformat(args.end)):
        partition = root / f"{start:%Y-%m}"
        partition.mkdir()
        first = retry(lambda start=start, end=end: command.ann_list(
            client, page_num=1, page_size=100, keyword="权益分派实施公告",
            publish_from=start.isoformat(), publish_to=end.isoformat(),
            sort_by="actual_publish_time", sort_order="asc",
        ))
        total_pages = int(first["data"]["totalPageNum"])
        pages = max(1, total_pages)
        expected_total = int(first["data"]["totalSize"])
        for page_number in range(1, pages + 1):
            response = first if page_number == 1 else retry(
                lambda page_number=page_number, start=start, end=end: command.ann_list(
                client, page_num=page_number, page_size=100,
                keyword="权益分派实施公告", publish_from=start.isoformat(),
                publish_to=end.isoformat(), sort_by="actual_publish_time", sort_order="asc",
                )
            )
            envelope = response["data"]
            if int(envelope["pageNum"]) != page_number \
                    or int(envelope["totalPageNum"]) != total_pages \
                    or int(envelope["totalSize"]) != expected_total:
                raise RuntimeError("pagination drift detected")
            raw = (json.dumps(response, ensure_ascii=False, sort_keys=True,
                              separators=(",", ":")) + "\n").encode()
            page_path = partition / f"page-{page_number:04d}.json"
            page_path.write_bytes(raw)
            files.append({"partition": f"{start:%Y-%m}", "role": "metadata",
                          "page": page_number, "path": page_path.relative_to(root).as_posix(),
                          "size": len(raw), "sha256": digest(raw)})
            if args.metadata_only:
                continue
            for item in envelope["data"]:
                transient = str(item.get("announcementId") or "")
                identity = digest(transient.encode())
                if not transient or identity in seen:
                    continue
                seen.add(identity)
                try:
                    pdf_path = partition / f"{identity}.pdf"
                    md_path = partition / f"{identity}.md"
                    retry(lambda transient=transient, pdf_path=pdf_path: command.ann_pdf_download(
                        client, transient, str(pdf_path)
                    ))
                    time.sleep(6)
                    from pypdf import PdfReader

                    extracted = "\n".join(
                        page.extract_text() or "" for page in PdfReader(str(pdf_path)).pages
                    )
                    if not extracted.strip():
                        raise ValueError("PDF has no extractable text")
                    md_path.write_text(extracted, encoding="utf-8")
                    pdf = pdf_path.read_bytes()
                    markdown = md_path.read_text(encoding="utf-8")
                    source_hash = digest(pdf)
                    rows.append(parse_action(item, markdown, source_hash))
                    for role, path in (("document", pdf_path), ("parsing", md_path)):
                        raw_file = path.read_bytes()
                        files.append({"partition": f"{start:%Y-%m}", "role": role,
                                      "identity_hash": identity, "size": len(raw_file),
                                      "sha256": digest(raw_file),
                                      "path": path.relative_to(root).as_posix()})
                except Exception as exc:  # noqa: BLE001 - every rejected source needs quarantine
                    quarantine.append({"identity_hash": identity,
                                       "reason": type(exc).__name__ + ": " + str(exc)})

    normalized = validate_corporate_actions(tuple(rows)) if rows else ()
    bundle_raw = (json.dumps([asdict(row) for row in normalized], ensure_ascii=False,
                             sort_keys=True, separators=(",", ":")) + "\n").encode()
    (root / "corporate-actions.json").write_bytes(bundle_raw)
    files.append({"partition": "all", "role": "normalized_bundle",
                  "path": "corporate-actions.json", "size": len(bundle_raw),
                  "sha256": digest(bundle_raw)})
    quarantine_hashes = sorted(row["identity_hash"] for row in quarantine)
    manifest = {
        "schema_version": VERSION, "operation_id": args.operation_id,
        "query_start": args.start, "query_end": args.end,
        "metadata_only": args.metadata_only, "source_records": len(seen),
        "accepted_rows": len(normalized), "quarantined_records": len(quarantine),
        "quarantined_identity_hashes": quarantine_hashes,
        "quarantine_set_sha256": digest(json.dumps(
            quarantine_hashes, separators=(",", ":")
        ).encode()),
        "bundle_sha256": digest(bundle_raw), "files": files,
        "inferential_trial_delta": 0, "formal_research_eligible": False,
    }
    manifest_raw = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n").encode()
    (root / "manifest.json").write_bytes(manifest_raw)
    (root / "quarantine.json").write_text(
        json.dumps(quarantine, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "success", "manifest_sha256": digest(manifest_raw),
                      "source_records": len(seen), "accepted_rows": len(normalized),
                      "quarantined_records": len(quarantine)}, sort_keys=True))


if __name__ == "__main__":
    main()
