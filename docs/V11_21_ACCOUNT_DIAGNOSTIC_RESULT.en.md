# B17 actual account root-cause review

## Conclusion

The original first account failure was reproduced and explained: skipping a tiny nonzero fill on the previous day leaves a false residual holding after the next day's liquidation. The corrected full-account audit passed. The preregistered same-day explanation condition did not pass, so the original RESULT/terminal remain UNRESOLVED, never retroactively changed to PASS.

No usable Alpha conclusion. This was a risk-control account/bookkeeping diagnostic, not complete candidate/control double-cost evaluation or Alpha Court.

## Actual execution

- Runtime35aecba0dbd7910dabc687ebb45b39476f55cd7c; actual CI34116673812:1468 passed,2 skipped,484.80s,Ruff PASS.
- Issue184 preregistration5569943831; plan80e6132fa1c45e7ed0e9aae06defb0cb1298073667e95b3a75b7fcc6388071ac.
- Claimed2026-09-07 11:37:49 UTC; terminal11:39:34 UTC,UNRESOLVED. One new native attempt,zero new fits,global lower bound3707.
- Owned child102.04s/506samples; peak private8954900480bytes,min free9960460288bytes; normal exit,no resource stop.
- Complete UNVERIFIED_ACCOUNT retained; original first failure2024-06-12; corrected full account passed.77 nonzero fills had absolute notional<=1e-12CNY.

## Append-only read-only explanation

Issue184comment5570120165 first declared a bounded arithmetic check: the original first-discrepant identity,up to its first failure date,only source opening prices required by saved fills. No account generation,target/model change or new Trial; debt remains3707. Whole-file SHA and exact date/identity boundaries were checked; mmap extracts small source objects without reloading the full history matrix.

The old audit skipped the tiny June11 sale while execution updated shares. After June12 liquidation,actual holdings were zero but the old audit retained approximately3.64e-12 shares. Exact identity,source opening prices,fill notionals and full quantities stay in ignored local trace evidence; no raw market records are committed.

This is cumulative share divergence exposed by later cancellation,not necessarily a same-day tiny fill. The reconstructed shares exactly matched saved marks without epsilon relaxation or execution changes. The same-day acceptance rule was too narrow; this explanation supplements rather than replaces that failed diagnostic.

## Evidence and limitations

- RESULT SHA52a3e2ddbe5b90753d0f7a078158a7aae7d93fa776e94d5cf3a3f337a82cc0e8.
- Registry SHAa8b26f47e8848f3fc086919361e5da6bc5ccb572a730287c0c8da2ea1c1b7d38.
- Account SHA7ee205b643e8ea58e2d16594fda2931e14ee514d978aa99d7271f831d9e91d78.
- Read-only trace plan file SHAe187a4d946e315120087dc7c383df92e448a212d837be7810c273b877bf6284a.
- Trace script SHA94e9dbc17bbd955d84dd108680a152753d931703fc915661d074b5f120bfcccd.
- Local companion:artifacts/flow-response/checkpoints/b17-cumulative-fill-diagnostic.ipynb; trace_b17_saved_fills.py,plan and result retained.

An additional synthetic prior-day tiny-sale/later-liquidation regression passed with the diagnostic and existing tiny-fill tests:34 passed in1.53s,Ruff PASS. This subset overlaps prior full CI; counts are not additive. All3 notebook code cells executed sequentially in fresh plain Python,checking exact shares and read-only native counts. nbformat/nbclient/Jupyter are absent; no Jupyter-kernel execution is claimed.

The first identity's cumulative cause is explained; this is not every later old-audit state,full independent source/model/selection verification or broker-certified integer-lot execution. No selection from other partial candidate returns,no2025/2026,new sources or old artifact modifications.

## Next

Separately preregister finite complete22-account continuation using frozen history and14 annual models. Preserve double costs,all controls and independent audit. Generate missing targets only from frozen models, count new native account attempts and inherit3707. Never replay old002/003/B17 or copy incomplete native results as completed. This later experiment is not yet executed;main is unchanged.
