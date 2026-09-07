"""Known causal synthetic price/flow generator; never a market data adapter.

No production response/predictor/selector calculation is imported. A planted
relationship is deliberately strong for a recoverability test, not realistic
Alpha evidence. Its paired null uses exactly the same exogenous shocks.
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np

from stephen_quant.qmt.reliable_panel import file_sha
from stephen_quant.workflows.v114_reliable_epoch import write_json

from .search_power_dsl import sha256_json

SEED = 184021
STOCKS = 160
VERSION = "response-source-power-1"


def synthetic_calendar():
    start, stop = date(2022, 1, 3), date(2024, 12, 31)
    return [
        str(start + timedelta(days=i))
        for i in range((stop - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    ]


def generator_contract():
    return {
        "version": VERSION,
        "synthetic_only": True,
        "seed": SEED,
        "stocks": STOCKS,
        "calendar": synthetic_calendar(),
        "case_strength": {"planted": 0.06, "null": 0.0},
        "return": "log_return_t=.002*x_t+.004*(1+.15*(stock_index%5))*e_t+strength*sum(s[t-20:t])/20",
        "shocks": "independent standard normal x/e, clipped to[-2.5,2.5]; same PCG64 stream in both cases",
        "signal": "tanh(z_x_t)*tanh(z_simple_return_t-corr_past(x,simple_return)/1.01*z_x_t)",
        "signal_window": "60 strictly earlier observations; zero before60; no current/future fit",
        "prices": "open_t=close_(t-1);close_t=open_t*exp(log_return_t);initialclose10;adjustment1",
        "flow": "net_inflow_CNY=.02*x_t*amount_thousands*1000",
        "amount_thousands": "100000+1000*stock_index; always above the frozen ADV minimum",
        "available": "daily17:00 andflow18:00 Shanghai on the observation date",
        "oracle": "digests stored separately, never part of input manifest or features",
        "empirical_trial_delta": 0,
        "interpretation": "known synthetic mechanism,not estimated market power or false positive rate",
    }


def simulate(calendar, *, case, stocks=STOCKS):
    full = synthetic_calendar()
    if case not in ("planted", "null") or type(stocks) is not int or not 80 <= stocks <= STOCKS:
        raise ValueError("fixed synthetic case and bounded80..160stock count required")
    if not 64 <= len(calendar) <= len(full) or list(calendar) != full[: len(calendar)]:
        raise ValueError("explicit synthetic weekday prefix required")
    rng = np.random.Generator(np.random.PCG64(SEED))
    opening = np.zeros((len(calendar), stocks))
    closing, flows, signals, carry = [np.zeros_like(opening) for _ in range(4)]
    px, past_x, past_r, past_signal = (
        np.full(stocks, 10.0),
        deque(maxlen=60),
        deque(maxlen=60),
        deque(maxlen=20),
    )
    noise_scale = 0.004 * (1 + 0.15 * (np.arange(stocks) % 5))
    strength = generator_contract()["case_strength"][case]
    for i in range(len(calendar)):
        x, e = [np.clip(rng.standard_normal(stocks), -2.5, 2.5) for _ in range(2)]
        # The current day never enters its own carry or response-estimation prefix.
        effect = strength * np.sum(past_signal, axis=0) / 20 if past_signal else np.zeros(stocks)
        opening[i] = px
        simple = np.expm1(0.002 * x + noise_scale * e + effect)
        px = px * (1 + simple)
        if not np.isfinite(px).all() or (px <= 0).any():
            raise ValueError("synthetic price overflow")
        signal = np.zeros(stocks)
        if len(past_x) == 60:
            xx, rr = np.asarray(past_x), np.asarray(past_r)
            xm, rm, xs, rs = xx.mean(0), rr.mean(0), xx.std(0), rr.std(0)
            if (xs <= 1e-12).any() or (rs <= 1e-12).any():
                raise ValueError("degenerate synthetic response prefix")
            beta = np.mean(((xx - xm) / xs) * ((rr - rm) / rs), axis=0) / 1.01
            zx, zy = (x - xm) / xs, (simple - rm) / rs
            signal = np.tanh(zx) * np.tanh(zy - beta * zx)
        closing[i], flows[i], signals[i], carry[i] = px, 0.02 * x, signal, effect
        past_x.append(x)
        past_r.append(simple)
        past_signal.append(signal)
    return {
        "open": opening,
        "close": closing,
        "flow_ratio": flows,
        "oracle_signal": signals,
        "oracle_carry": carry,
    }


def write_synthetic_sources(root, *, case, calendar=None, stocks=STOCKS):
    root = Path(root)
    if root.exists():
        raise FileExistsError("synthetic source directory already exists")
    calendar = synthetic_calendar() if calendar is None else list(calendar)
    values = simulate(calendar, case=case, stocks=stocks)
    root.mkdir(parents=True, exist_ok=False)
    # NumPy scan has one input-array row per SQL column. No extra Pandas dependency.
    n = len(calendar)
    indexes = np.tile(np.arange(stocks), n)
    offsets = np.repeat([(date.fromisoformat(d) - date(2022, 1, 3)).days for d in calendar], stocks)
    amounts = 100000 + 1000 * indexes
    numeric = np.vstack(
        (
            offsets,
            600000 + indexes,
            values["open"].ravel(),
            values["close"].ravel(),
            amounts,
            values["flow_ratio"].ravel() * amounts * 1000,
        )
    )
    with duckdb.connect(":memory:") as conn:
        conn.register("numeric", numeric)
        conn.execute("""CREATE TABLE raw AS SELECT DATE '2022-01-03'+CAST(column0 AS INTEGER) trade_date,
            printf('%06d',CAST(column1 AS INTEGER)) instrument,column2 AS open,column3 AS close,
            column4 AS amount,column5 AS net_inflow_amount FROM numeric""")
        sources = []
        for source in ("daily", "fund_flow"):
            projection = (
                "trade_date,instrument,'Example' AS name,open,close,amount,"
                "100000.0 AS volume,1.0 AS adjustment_factor"
                if source == "daily"
                else "trade_date,instrument,net_inflow_amount"
            )
            hour = "17" if source == "daily" else "18"
            path = root / (source + ".parquet")
            conn.execute(
                f"""COPY (SELECT {projection},CAST(CAST(trade_date AS VARCHAR)||
                'T{hour}:00:00+08:00' AS TIMESTAMPTZ) available_at FROM raw
                ORDER BY trade_date,instrument) TO ? (FORMAT PARQUET)""",
                [str(path)],
            )
            sources.append(
                {
                    "source": source,
                    "file": path.name,
                    "sha256": file_sha(path),
                    "rows": n * stocks,
                    "min_date": calendar[0],
                    "max_date": calendar[-1],
                    "authorized_start": "2022-01-01",
                    "authorized_end": "2024-12-31",
                }
            )
    sources.extend(
        {"source": name, "file": name + ".parquet", "sha256": "a" * 64, "rows": 0}
        for name in ("auction", "chip", "minute")
    )
    manifest = {
        "sources": sources,
        "snapshot_sha256": sha256_json(sources),
        "exposed_sealed_rows": 0,
    }
    write_json(root / "manifest.json", manifest)
    oracle = {k: sha256_json(v.tolist()) for k, v in values.items() if k.startswith("oracle_")}
    write_json(
        root / "SYNTHETIC_CONTRACT.json",
        generator_contract()
        | {
            "case": case,
            "actual_stocks": stocks,
            "actual_calendar": calendar,
            "oracle_sha256": oracle,
            "snapshot_sha256": manifest["snapshot_sha256"],
        },
    )
    return calendar, manifest["snapshot_sha256"], oracle
