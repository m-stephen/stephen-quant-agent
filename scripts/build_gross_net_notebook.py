"""Execute reviewable audit cells under ordinary Python; no new market experiment."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path


def build():
    deps = {
        n: importlib.util.find_spec(n) is not None for n in ("nbformat", "nbclient", "ipykernel")
    }
    cells = []

    def md(body):
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

    md(
        "## tl;dr\n\nV11.20 frozen-policy diagnosis; not a new Alpha or a refit. Both original primary candidates remain failed.\n"
    )
    md(
        "## Context & Methods\n\n12 zero-fee replays versus24 immutable paid paths,2023–2024 reused history,CNY3m continuous.\n### Key Assumptions\n\nTargets are byte-frozen;cash compounding means fee addback is not a zero-cost run. Original16models/32fits are inherited;newfits0. No2025/26.\nRequiresPython3.10+ andDuckDB;local ignored operation files are required for full reproduction.\n"
    )
    md("## Data\n\n### 1. Verify immutable evidence and debt\n")
    code("""import json,hashlib,math
from pathlib import Path
import duckdb
repo=Path.cwd()
if not (repo/'docs/V11_20_RESULT.summary.json').exists(): repo=repo.parent
operation=repo/'artifacts/gross-net/epoch-001'
summary=json.loads((repo/'docs/V11_20_RESULT.summary.json').read_text(encoding='utf-8'))
audit=json.loads((operation/'INDEPENDENT_AUDIT.json').read_text(encoding='utf-8'))
result=json.loads((operation/'RESULT.json').read_text(encoding='utf-8'))
assert audit['pass'] and summary['independent_audit_pass'] and not summary['validated_alpha']
assert hashlib.sha256((operation/'RESULT.json').read_bytes()).hexdigest()==summary['source_result_sha256']
assert len(summary['rows'])==36 and summary['raw_trial_lower_bound']==3660
print({'accounts':36,'debt':3660,'new_fits':summary['new_fits'],'inherited_fits':summary['inherited_fit_receipts']})
""")
    md("### 2. Check source query and frozen target byte identity without rerunning source reads\n")
    code("""assert (repo/'scripts/gross_net_source_audit.sql').read_text(encoding='utf-8')==audit['source_query']
parent=Path(result['spec']['parent_dir'])
for plan in result['spec']['plans']:
    rel='targets/'+plan['target_key']+'.json'
    assert (operation/rel).read_bytes()==(parent/rel).read_bytes()
assert summary['new_fits']==0 and summary['inherited_models']==16
print({'frozen_target_sets':12,'same_source_query':True})
""")
    md("## Results\n\n### 3. Independently recompute all36 saved account aggregates\n")
    code("""actual={}
template=(repo/'scripts/lead_challenge_audit.sql').read_text(encoding='utf-8')
for folder in (operation,parent):
    with duckdb.connect() as con:
        cur=con.execute(template.replace('__ACCOUNT_GLOB__',(folder/'accounts/*.jsonl').as_posix()))
        names=[d[0] for d in cur.description]
        for r in cur.fetchall():
            assert r[0] not in actual
            actual[r[0]]=dict(zip(names,r))
assert len(actual)==36
for row in summary['rows']:
    for k in ('net_return','final_nav','cost_cny','max_drawdown'):
        assert math.isclose(row[k],actual[row['account_key']][k],rel_tol=1e-10,abs_tol=1e-6)
print({'independent_saved_account_aggregates':36,'pass':True})
""")
    md("### 4. Review primary paths and complete comparisons\n")
    code("""for row in summary['rows']:
    if row['policy']=='full':
        print({k:row[k] for k in ('account_key','return2023','return2024','net_return','cost_cny')})
assert len(summary['attribution']['increments'])==42
assert len(summary['attribution']['path_drag'])==24
assert result['statistics']=={'dsr':None,'pbo':None,'placebo':None,'status':'NOT_RUN'}
assert result['screen_survived']=={'linear':False,'quadratic':False}
print({'diagnostic_only':True,'validated_alpha':False})
""")
    md(
        "## Takeaways\n\nZero fees cannot promote a failed paid candidate. Gross/net cross-differences are descriptive,not causal or independentOOS. Register a genuinely different follow-on mechanism or train-prefix objective; do not retune these targets.\nCells executed under ordinaryPython,not a Jupyter kernel. Jupyter frontend QA is NOT_RUN.\nOptional dependency availability at build: "
        + json.dumps(deps)
        + "\n"
    )
    namespace, count = {}, 0
    for i, cell in enumerate(cells):
        cell["id"] = f"gross-net-audit-{i + 1}"
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
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
    }
    path = Path("notebooks/V11_20_AUDIT.ipynb")
    with path.open("x", encoding="utf-8", newline="\n") as f:
        json.dump(nb, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    assert json.loads(path.read_text(encoding="utf-8")) == nb
    print(
        json.dumps(
            {
                "executed_python_cells": count,
                "jupyter_frontend_qa": "NOT_RUN",
                "optional_dependencies": deps,
            }
        )
    )


if __name__ == "__main__":
    build()
