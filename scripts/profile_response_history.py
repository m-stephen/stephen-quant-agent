"""Exclusive SYNTHETIC history/cache resource probe; never opens market inputs.

Development helper intentionally reuses the tested synthetic source generator.
No predictive score, account, Alpha selection or empirical Trial is produced.
"""

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_flow_response_history import frozen_sources

from stephen_quant.discovery.flow_response_history import (
    VERSION,
    VerifiedHistoryCache,
    build_history_from_frozen,
)
from stephen_quant.discovery.flow_response_series import DAILY_SUPPORT, response_stages
from stephen_quant.discovery.response_resources import process_memory
from stephen_quant.discovery.search_power_dsl import sha256_json
from stephen_quant.integrity.models import ExperimentSpec, TrialSpec
from stephen_quant.integrity.registry import ExperimentRegistry
from stephen_quant.integrity.snapshot import build_composite_snapshot_manifest
from stephen_quant.workflows.v114_reliable_epoch import write_json


def run(output, *, stocks):
    output = Path(output).resolve()
    allowed = (ROOT / "artifacts/flow-response/probes").resolve()
    if allowed not in output.parents or type(stocks) is not int or not 80 <= stocks <= 640:
        raise ValueError("bounded synthetic probe inside artifacts/flow-response/probes required")
    output.mkdir(parents=True, exist_ok=False)
    start = perf_counter()
    stages = {"start": {"seconds": 0.0, **process_memory()}}

    def checkpoint(name):
        stages[name] = {"seconds": perf_counter() - start, **process_memory()}
        print(json.dumps({"stage": name, **stages[name]}), flush=True)

    try:
        calendar, manifest = frozen_sources(output / "inputs", span_days=770, stock_count=stocks)
        checkpoint("synthetic_sources")
        registry = ExperimentRegistry(output / "registry.sqlite3")
        sid = registry.register_snapshot(
            build_composite_snapshot_manifest({"response_inputs": manifest})
        )
        eid = registry.create_experiment(
            ExperimentSpec(
                "synthetic_resource_probe",
                "not a market experiment",
                sid,
                "development-resource-probe",
            )
        )
        params = {
            "response_history_version": VERSION,
            "response_support_policy": DAILY_SUPPORT,
            "response_manifest_sha256": manifest,
            "response_calendar_sha256": sha256_json(calendar),
        }
        provider, _ = registry.create_trial(
            TrialSpec(
                eid,
                "provider",
                "synthetic_only",
                json.dumps(params),
                184,
                "2022-01-01",
                "2024-12-31",
                "unused",
                "unused",
                "unused",
                "unused",
                fit_stages=response_stages(calendar),
            )
        )
        consumer, _ = registry.create_trial(
            TrialSpec(
                eid,
                "consumer",
                "synthetic_only",
                json.dumps(params),
                184,
                "2022-01-01",
                "2024-12-31",
                "unused",
                "unused",
                "unused",
                "unused",
                fit_stages=(),
            )
        )
        registry.declare_feature_sources(provider, ())
        registry.declare_feature_sources(consumer, (provider,))
        history = build_history_from_frozen(
            registry,
            provider,
            (consumer,),
            input_folder=output / "inputs",
            output_folder=output / "history",
            calendar=calendar,
            manifest_sha256=manifest,
        )
        checkpoint("native_history")
        cache = VerifiedHistoryCache(registry, consumer, history)
        cache.get(registry, consumer, history)
        checkpoint("verified_cache")
        result = {
            "kind": "synthetic_resource_probe",
            "stocks": stocks,
            "sessions": len(calendar),
            "source_rows_each": stocks * len(calendar),
            "history_bytes": history.stat().st_size,
            "bundle_bytes": sum(p.stat().st_size for p in history.parent.glob("response-*.json")),
            "stages": stages,
            "empirical_trial_delta": 0,
            "validated_alpha": False,
            "interpretation": "one process peak including imports/source/build/cache;not whole research/audit or real market scale",
        }
        write_json(output / "RESOURCE_RESULT.json", result)
        return result
    except Exception as exc:
        write_json(
            output / "ABORTED.json",
            {
                "kind": "synthetic_resource_probe",
                "exception_type": type(exc).__name__,
                "stages": stages,
                "empirical_trial_delta": 0,
            },
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--stocks", type=int, default=320)
    args = parser.parse_args()
    run(args.output, stocks=args.stocks)
