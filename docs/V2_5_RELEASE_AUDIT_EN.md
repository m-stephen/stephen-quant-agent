# V2.5 Research-preview Release Audit

## Classification

- Package version: 2.5.0
- Class: `research-preview`
- Engineering decision: `RESEARCH_PREVIEW_READY`
- Alpha decision: `PROMOTE_RESEARCH_ONLY`
- Autonomous live trading: disabled and unauthorized
- Sealed windows: 2025/2026 unopened

## Release evidence

- the 35-period V2.3 execution metrics replay exactly;
- regime classification uses only five-day momentum visible before execution;
- all three policies share exactly the same execution dates;
- exactly two inferential trials were added, for a cumulative count of 47;
- every policy has zero capacity clipping;
- strategy-family PBO is explicitly limited to portfolio-policy selection;
- JSON and bilingual results support offline hash replay;
- local paths, raw data, reports, and registries remain outside Git.

## Risk disclosure

The cash gate improves research-period metrics, but PBO, DSR, and return concentration fail.
Release authorizes the research infrastructure and its positive and negative evidence only. It
does not authorize opening sealed windows, relaxing gates, or deploying trading. The next test
must be genuinely independent in time rather than another threshold adjustment on 2022–2024.
