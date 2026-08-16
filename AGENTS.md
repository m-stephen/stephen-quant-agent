# Codex Instructions — Stephen Quant Agent

## Mission
Build an integrity-first quantitative research system. A result is not an alpha candidate until the system can show how it was produced and can actively try to falsify it.

## Non-negotiable rules
1. Never use future information at prediction time.
2. Every dataset used in an experiment must have a frozen snapshot hash.
3. Every experiment and hyperparameter attempt increments the trial ledger.
4. Every transform must eventually be fit inside the training fold only.
5. Never use random K-fold for time-series evaluation.
6. Research validation will use purge/embargo and CPCV; deployment simulation will use walk-forward.
7. Transaction costs and slippage must be explicit in later backtests.
8. LLM-generated factors are candidates only; they must pass statistical validation and placebo tests.
9. Do not optimize against the final test window.
10. Prefer simple baselines before adding PPO/GNN/LLM complexity.
11. Never commit QMT raw data, account identifiers, credentials, or terminal-specific paths.

## V1.0 scope
- Experiment Registry
- Point-in-Time metadata model
- Frozen data snapshot + SHA-256 manifest
- Trial counter / multiplicity ledger foundation
- Feature timing audit
- CI tests

## Next milestones
- V1.1 factor definitions + factor registry
- V1.2 IC/RankIC/ICIR + Alpha Card
- V1.3 purge/embargo + CPCV
- V1.4 placebo/falsification engine + PBO/DSR
- V1.5 momentum baseline
- V1.6 PPO allocation layer
- V1.7 LLM factor research agent
- V1.8 QMT data adapter + end-to-end out-of-sample backtest
- V1.8.1 official xtquant local-cache exporter (no binary reverse engineering)
- V1.8.2 version-locked, read-only QMT daily DAT adapter for terminals without xtquant service
- V1.8.3 one-command DAT engineering backtest validation on the long-lived data-test branch
- V1.8.4 read-only DividData corporate actions + point-in-time back-ratio adjustment
- V1.8.5 QD date-partitioned CSV adapter + historical daily backtest validation
- V1.8.6 training-only QD universe + benchmark comparison + placebo audit
- V1.8.7 validation-only diagnostics + conservative open-limit execution constraints

## Engineering style
- Python >= 3.10.
- Keep core integrity code dependency-light.
- Add tests for every leakage or provenance rule.
- Store machine-generated artifacts outside git unless they are tiny fixtures.
- Make all experiments reproducible from a command plus a config and snapshot ID.
