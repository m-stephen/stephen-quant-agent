# V11.18 continuation / 恢复点

Issue184;branch codex/v11.18-conditional-risk,stacked on PR195 finalade50a9.
PR195 final CI34058274198SUCCESS and nowReady;no main merge.
Root codex/v4-8-sealed-alpha-court still has23 unrelated dirty files;do not touch.

PREMARKET checkpoint: core,exclusive driver,independent source/model/target/native
auditor and raw-price/cap checks implemented. 30new synthetic cases PASS3.18s.
Complete982passed1skipped175.58s. RuffPASS. No real V11.18 numerical run or Trial
reserved at this checkpoint. Read actual operation/claims before any launch;
this note will be supplemented by later comments/evidence. Never retry/overwrite
an operation or bypass its parent claim.

Exactly44accounts,debt3556->3600:2bases x2meanrules x4policies x2costs=32;
4risk-only controls;8original/full-target versus unscaled/target_changes anchors.
Four primary identities. No new stock selector;frozen lowvol and stable_lowrisk
target bytes from ORIGINAL V11.11tree. Models predict gross 200-name basket
five-session open-to-open returns and second moments,not executable basket P&L.
Daily only;market breadth20/meanret20/meanvol20/dispersion1;30minimum nonoverlap
train samples. Annual past-prefix fit removes final5sessions and honors full
label maturity;ridge lambda1,γ10,clipped.25..1,quarter-step exposure.
Exposure refresh every5sessions,no annual reset. All exact details in DESIGN.

Source snapshot remains original V11.4 epoch-002 five-source
b813a94d5342013488b8192e8ecf940c898ce984e47fbe2fdcb95a3c570c5a51.
2022train,2023/24reuseddevelopment,no2025/26. Parent V11.17 RESULT
948ab8dc763fbfc319153ef956c107bc57d7cac111ee7995fa85b2b132276aa5 isCOMPLETE,
0/6candidates,50trials,debt3556;do NOT rerun V11.17orV11.16.

Before real values: commit runtime,preregister exact design/budget inIssue184,
put returned comment ID in ignored artifacts/conditional-risk/run.local.json.
Run scripts/run_conditional_risk.py --config artifacts/conditional-risk/run.local.json
with PYTHONPATH=src and modest BLAS threads;clear AlphaPai env only in child.
Runner reserves all44nativeTrials before values and writes all four models;
36nonanchor accounts bind2native supervised stages each (72fits total).
No-fit anchors bind explicit empty stages. Shared fitted predictions are checked
against actual immutable artifacts before use. All raw sources remain read-only.

After RESULT completes, run scripts/audit_conditional_risk.py --output
artifacts/conditional-risk/epoch-001 --inputs [original frozen input directory].
Check states,all proxy labels/components,normal equations/calibration,actual
source capacity/current-close marks,22targetsets,44cash/NAV/cost paths and72fits.
Auditor-only engineering errors may be repaired with evidence/regressions;
do not rerun market,alter results or edit source runtime/driver after start.
Build complete bilingual reports,44aggregate rows,native report schema validation
and executed notebook companion. Renderer/UI QA must respect userquiet;explicitly
record deferral rather than claiming visible delivery. Check latest headCI before
PRReady. No automatic mainmerge,trading or raw-source/credential publication.

Screens unchanged:both costs,both years positive,SR>=.7,DD>=-.25,>=3pp total
increment versus EVERY same-base fixed/lag20/shuffle/risk-only/unscaled/original
control,annual difference>=-5pp,95%statecoverage andallintegrity/accountchecks.
Fixed exposure is matched on TRAINING mean,not exact future exposure/turnover;
report realized risk,cash,cost and turnover differences. A volatility/cash benefit
is not stock-selection Alpha. No one-permutation placebo p-value,DSR/PBO/CourtPASS
from reuseddevelopment. Preserve all negative evidence.

If a full survivor exists, freeze its identity/model/targets and cumulativeTrial
lineage before further finite predeclared delay/capacity/regime/falsification
checks. Do not tune finalwindow,lower DSR.95/PBO.05/placebo.05orpath/costlimits.
Ordinary negative/noncertified results go to reports/GitHub,quietly. The existing
v10-alpha30minute continuation staysactive;only notify usableAlpha,actionable
blocker ormajorfault. Any next mechanism requires a new finite preregistration,
never retrospective sign/threshold/horizon selection on this batch.
