"""Native lineage entry point for future registered residual experiments.

Does not rerun the closed V11.10 market epoch or turn its appendix into native evidence.
"""

from __future__ import annotations

from itertools import pairwise

from stephen_quant.integrity.fit_lineage import FitStage

from .residual_mechanisms import MECHANISMS, POLICIES, targets_for


def fit_stages(years=(2023, 2024)):
    return tuple(
        FitStage(str(year), "2022-01-01", f"{year - 1}-12-31", f"{year}-01-01", f"{year}-12-31")
        for year in years
    )


def guarded_targets(registry, trial_id, days, models, policy, model_paths, cache=None):
    """Verify all model stages before targets_for may inspect any feature values.

    Contract () explicitly denotes an unfitted control; missing/legacy is not equivalent.
    Native contracts must be specified in TrialSpec before data access and fitting.
    """
    if policy not in POLICIES:
        raise ValueError("unregistered policy")
    lineage = registry.fit_lineage(trial_id)
    if policy not in MECHANISMS:
        if lineage["stages"]:
            raise ValueError("unfitted control requires empty native fit contract")
    else:
        if not lineage["stages"]:
            raise ValueError("learned policy requires native model stages")
        for previous, day in pairwise(days):
            year = int(day.date[:4])
            registry.assert_prediction_fit(
                trial_id,
                model=models[year],
                artifact_path=model_paths[year],
                prediction_date=day.date,
                signal_date=previous.date,
            )
    return targets_for(days, models, policy, cache)
