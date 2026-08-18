# V4.9 Append-Only Forward Continuation Protocol

V4.9 does not create a replacement factor from the consumed 2026 window. It keeps candidate
fingerprint `49bbaa53abab3f00a43011565235529629d807e8712eafc163e020f10ab9fec7` frozen and waits for
new data strictly after 2026-08-16.

The readiness gate reads file names and sizes only. It requires at least 25 dates shared by daily
bars, fund flow and auction sources. Files dated after the explicit `as_of` date are ignored. Until
the gate passes, factor values, returns and Alpha Court statistics must not be recomputed.

Once ready, the continuation must preserve the V4.8 candidate identity, standard and doubled cost
models, path thresholds, placebo threshold 0.05, PBO threshold 0.05 and DSR threshold 0.95. All new
observations are appended; no earlier observation may be removed or relabeled.
