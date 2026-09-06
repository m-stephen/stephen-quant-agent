"""Build and execute a bounded audit notebook with plain Python cells."""

import contextlib
import io
import json
from pathlib import Path


def build():
    cells = []

    def markdown(text):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(True)})

    def code(text):
        cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "source": text.splitlines(True),
                "execution_count": None,
                "outputs": [],
            }
        )

    markdown(
        "## tl;dr\n\nV11.18 条件风险配置 / Conditional risk allocation.\n"
        "This notebook verifies saved evidence; it does not start a new experiment or certify alpha.\n"
    )
    markdown(
        "## Context & Methods\n\n44 accounts, four primary identities, CNY3m, 82/164bps; "
        "2022 training and reused 2023–2024 development. No 2025/26 data access.\n"
        "### Key Assumptions\n\nConditional risk allocation is not a new stock selector. "
        "Gross basket proxy labels differ from executable portfolio returns. All 44 outcomes remain visible.\n"
        "Required cell dependencies: Python3.10+ and DuckDB (`pip install -e '.[research]'`).\n"
    )
    markdown("## Data\n\n### 1. Verify bounded evidence and immutable result identity\n")
    code("""import json, hashlib, math
from pathlib import Path
import duckdb
repo = Path.cwd()
if not (repo / 'docs/V11_18_RESULT.summary.json').exists():
    repo = repo.parent
operation = repo / 'artifacts/conditional-risk/epoch-001'
summary = json.loads((repo / 'docs/V11_18_RESULT.summary.json').read_text(encoding='utf-8'))
audit = json.loads((operation / 'INDEPENDENT_AUDIT.json').read_text(encoding='utf-8'))
assert audit['pass'] and summary['independent_audit_pass']
assert hashlib.sha256((operation/'RESULT.json').read_bytes()).hexdigest() == summary['source_result_sha256']
assert len(summary['rows']) == 44 and summary['raw_trial_lower_bound'] == 3600
print({'accounts':44, 'states':summary['states'], 'labels':summary['proxy_labels'],
       'coverage':summary['coverage'], 'raw_trial_lower_bound':3600})
""")
    markdown(
        "### 2. Verify the source-query identity and fit horizons\n\n"
        "This binds the query already executed by the independent audit; the notebook does not rerun the raw-source join.\n"
    )
    code("""query_source = (repo/'scripts/conditional_risk_source_audit.sql').read_text(encoding='utf-8')
assert query_source == audit['source_query']
for identity, model in summary['models_summary'].items():
    assert model['maximum_label_end'] <= model['fit_cutoff']
    assert model['training_signal_dates'] >= 30
    print(identity, model)
""")
    markdown("## Results\n\n### 3. Independently recompute all 44 saved account aggregates\n")
    code("""query = (repo/'scripts/lead_challenge_audit.sql').read_text(encoding='utf-8')
query = query.replace('__ACCOUNT_GLOB__', (operation/'accounts/*.jsonl').as_posix())
with duckdb.connect() as con:
    cursor = con.execute(query)
    fields = [x[0] for x in cursor.description]
    actual = {r[0]:dict(zip(fields,r)) for r in cursor.fetchall()}
assert len(actual) == 44
for row in summary['rows']:
    for field in ('net_return','final_nav','cost_cny','max_drawdown'):
        assert math.isclose(actual[row['account_key']][field], row[field], rel_tol=1e-10, abs_tol=1e-6)
print({'independently_recomputed_accounts':44,'aggregate_reconciliation':True})
""")
    markdown("### 4. Inspect all primary identities and both costs\n")
    code("""for r in summary['primary_comparisons']:
    print({k:r[k] for k in ('identity','roundtrip_bps','return2023','return2024','net_return',
                          'sharpe','max_drawdown','minimum_control_increment','mean_cash_fraction')})
print({'exploratory_survivors':summary['screen_survived'],'validated_alpha':summary['validated_alpha']})
""")
    markdown(
        "## Takeaways\n\nOnly complete screen survivors may be frozen for deeper registered challenges. "
        "Reused development evidence does not establish independent alpha. Cash/risk reduction is not alpha.\n"
        "All plain-Python code cells are executed in order by scripts/build_conditional_risk_notebook.py. "
        "nbformat, nbclient and ipykernel are absent on this host; Jupyter kernel/frontend and pixel QA were not run. "
        "Optional after installation: `python -m jupyter nbconvert --execute --to notebook --inplace notebooks/V11_18_AUDIT.ipynb`.\n"
    )
    namespace, execution = {}, 0
    for index, cell in enumerate(cells):
        cell["id"] = f"conditional-risk-audit-{index + 1}"
        if cell["cell_type"] == "code":
            execution += 1
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                # Fixed reviewed literals above, not external code or data.
                exec(compile("".join(cell["source"]), f"cell-{execution}", "exec"), namespace)  # noqa: S102
            cell["execution_count"] = execution
            cell["outputs"] = [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": output.getvalue().splitlines(True),
                }
            ]
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
    }
    target = Path("notebooks/V11_18_AUDIT.ipynb")
    target.parent.mkdir(exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(notebook, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    assert json.loads(target.read_text(encoding="utf-8")) == notebook
    print(
        json.dumps(
            {
                "notebook": target.as_posix(),
                "executed_python_cells": execution,
                "jupyter_frontend_qa": "NOT_RUN_MISSING_OPTIONAL_DEPENDENCIES",
            }
        )
    )


if __name__ == "__main__":
    build()
