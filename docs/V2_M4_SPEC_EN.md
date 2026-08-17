# V2 M4: Structured Failure Store and Frozen Research Epochs

## Objective

Failures no longer live only in prose reports. They become typed SQLite nodes, edges and events linked to epoch, family, candidate, stage and reason code. All records are append-only.

## Epoch discipline

- Freeze the policy hash and family/candidate/compute/token/statistical budgets at epoch start.
- Intermediate results may append failures and events but cannot change policy within the epoch.
- A next epoch can be created only after the current epoch is closed.
- Next-epoch actions are restricted to Explore, Exploit, Mutate, Recombine or STOP_FAMILY.
- A family reaching the exhaustion threshold must receive zero budget in the next epoch.

## Decision mapping

Duplicate, high-cost or no-marginal-value failures trigger single-dimension Mutate. Multiple failure types may trigger Recombine. CPCV/placebo failures require exploration of a new mechanism. Unready data or an exhausted family triggers STOP_FAMILY. Exploit is allowed only when no failure is recorded. Every decision stores source failure-node IDs and a reason code.

## Acceptance

The same frozen failure graph must produce the same next-epoch budget and actions. Open epochs cannot update policy, and UPDATE or DELETE against failure/history/decision records must fail.
