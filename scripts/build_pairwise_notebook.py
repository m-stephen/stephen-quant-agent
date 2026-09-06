"""Bounded audit notebook; execute literal cells in plain Python, not a Jupyter kernel."""

import contextlib
import io
import json
from pathlib import Path


def build():
    cells = []

    def markdown(body):
        cells.append({"cell_type": "markdown", "metadata": {}, "source": body.splitlines(True)})

    def code(body):
        cells.append(
            {
                "cell_type": "code",
                "metadata": {},
                "source": body.splitlines(True),
                "execution_count": None,
                "outputs": [],
            }
        )

    markdown(
        "## tl;dr\n\nV11.19.1 pairwise ranking / 成对排序。This verifies saved evidence,not a new experiment or Alpha certificate.\n"
    )
    markdown(
        "## Context & Methods\n\n24 continuousCNY3m accounts,two primary identities,2023–2024 reused development,2022 training.\n"
        "### Key Assumptions\n\nOverlapping pairs are not independent observations;gross proxy labels omit execution costs.\n"
        "The initial numerical abort charged24Trials;corrected24adds to debt3648. No2025/26 access.\n"
        "RequiresPython3.10+ andDuckDB; install project research extras if missing.\n"
    )
    markdown("## Data\n\n### 1. Check the immutable result and independent audit\n")
    code("""import json,hashlib,math
from pathlib import Path
import duckdb
repo = Path.cwd()
if not (repo/'docs/V11_19_RESULT.summary.json').exists():
    repo = repo.parent
operation = repo/'artifacts/pairwise-ranking/epoch-002'
summary = json.loads((repo/'docs/V11_19_RESULT.summary.json').read_text(encoding='utf-8'))
audit = json.loads((operation/'INDEPENDENT_AUDIT.json').read_text(encoding='utf-8'))
assert audit['pass'] and summary['independent_audit_pass']
assert hashlib.sha256((operation/'RESULT.json').read_bytes()).hexdigest()==summary['source_result_sha256']
assert len(summary['rows'])==24 and summary['raw_trial_lower_bound']==3648
print({'accounts':24,'debt':3648,'training_pairs':summary['training_pairs'],'rank_dates':summary['rank_dates']})
""")
    markdown(
        "### 2. Check source-query identity and training horizons\n\nThis binds the completed raw-source audit without repeating its market query.\n"
    )
    code("""assert (repo/'scripts/pairwise_source_audit.sql').read_text(encoding='utf-8')==audit['source_query']
for key,m in summary['models_summary'].items():
    assert m['maximum_label_end']<=m['fit_cutoff']<str(m['year'])+'-01-01'
    assert m['training_signal_dates']>=30
print({'models':len(summary['models_summary']),'mature_prefixes_verified':True})
""")
    markdown("## Results\n\n### 3. Reconcile all24 saved accounts using independent SQL\n")
    code("""query = (repo/'scripts/lead_challenge_audit.sql').read_text(encoding='utf-8')
query = query.replace('__ACCOUNT_GLOB__',(operation/'accounts/*.jsonl').as_posix())
with duckdb.connect() as con:
    cur=con.execute(query)
    fields=[d[0] for d in cur.description]
    actual={r[0]:dict(zip(fields,r)) for r in cur.fetchall()}
assert len(actual)==24
for row in summary['rows']:
    for key in ('net_return','final_nav','cost_cny','max_drawdown'):
        assert math.isclose(row[key],actual[row['account_key']][key],rel_tol=1e-10,abs_tol=1e-6)
print({'account_aggregate_checks':24,'pass':True})
""")
    markdown("### 4. Inspect every primary result at both costs\n")
    code("""for row in summary['primary_comparisons']:
    print({k:row[k] for k in ('identity','roundtrip_bps','return2023','return2024','net_return','sharpe','minimum_control_increment','failed_gates')})
print({'exploratory_survivors':summary['screen_survived'],'validated_alpha':summary['validated_alpha']})
""")
    markdown(
        "## Takeaways\n\nOnly full survivors can be frozen for preregistered deeper challenges;history reuse is not independentOOS.\n"
        "Cells execute in order under ordinaryPython. nbformat,nbclient,ipykernel are absent on the checked host;Jupyter frontend/kernel QA is NOT_RUN.\n"
        "After installing optional dependencies: `python -m jupyter nbconvert --execute --to notebook --inplace notebooks/V11_19_AUDIT.ipynb`.\n"
    )
    namespace, count = {}, 0
    for i, cell in enumerate(cells):
        cell["id"] = f"pairwise-audit-{i + 1}"
        if cell["cell_type"] == "code":
            count += 1
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                exec(compile("".join(cell["source"]), f"cell-{count}", "exec"), namespace)  # noqa: S102
            cell["execution_count"] = count
            cell["outputs"] = [
                {
                    "output_type": "stream",
                    "name": "stdout",
                    "text": stream.getvalue().splitlines(True),
                }
            ]
    survived = sum(namespace["summary"]["screen_survived"].values())
    cells[0]["source"].append(
        f"\nObserved complete exploratory survivors:{survived}/2;certified usable Alpha:0.\n"
    )
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
    }
    path = Path("notebooks/V11_19_AUDIT.ipynb")
    path.parent.mkdir(exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(notebook, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    assert json.loads(path.read_text(encoding="utf-8")) == notebook
    print(
        json.dumps(
            {
                "notebook": path.as_posix(),
                "executed_python_cells": count,
                "jupyter_frontend_qa": "NOT_RUN_MISSING_OPTIONAL_DEPENDENCIES",
            }
        )
    )


if __name__ == "__main__":
    build()
