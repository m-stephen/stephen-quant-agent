"""Standard-library notebook scaffold and ordered Python-cell execution.

nbformat/nbclient/ipykernel are absent on this host. Cells use plain Python only;
we execute every cell in order and record outputs, without claiming Jupyter UI QA.
"""

import contextlib
import io
import json
from pathlib import Path


def build():
    summary = json.loads(Path("docs/V11_17_RESULT.summary.json").read_text())
    if not summary["independent_audit_pass"]:
        raise ValueError("audited input required")
    survivors = sum(summary["screen_survived"].values())
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
        f"## tl;dr\n\nV11.17: {survivors}/6 exploratory survivors; certified Alpha remains0.\n"
        "本笔记复核已审计结果，不重新搜索、不拟合模型、不打开封存数据。\n"
    )
    markdown(
        "## Context & Methods\n\nCompanion to the bilingual V11.17 reports and Issue184.\n"
        "### Key Assumptions\n\n2023–2024 are reused development history; CNY3m;82/164bps.\n"
        "Statistical peers are not actual supply chains. All50 account outcomes remain visible.\n"
        "Install project research extras to obtain DuckDB; the code cells need only standard Python and DuckDB.\n"
        "Raw-feature and graph checks are implemented in `scripts/peer_source_audit.sql` and `scripts/audit_peer_information.py`.\n"
    )
    markdown("## Data\n\n### 1. Read bounded audit evidence\n")
    code("""import json
from pathlib import Path
import hashlib
import duckdb

repo = Path.cwd()
if not (repo / 'docs/V11_17_RESULT.summary.json').exists():
    repo = repo.parent
operation = repo / 'artifacts/peer-information/epoch-001'
summary = json.loads((repo / 'docs/V11_17_RESULT.summary.json').read_text(encoding='utf-8'))
audit = json.loads((operation / 'INDEPENDENT_AUDIT.json').read_text(encoding='utf-8'))
assert audit['pass'] and summary['independent_audit_pass']
assert hashlib.sha256((operation / 'RESULT.json').read_bytes()).hexdigest() == summary['source_result_sha256']
assert len(summary['rows']) == 50 and summary['raw_trial_lower_bound'] == 3556
print({'accounts': 50, 'source_rows_checked': summary['input_rows'], 'debt': 3556,
       'graph_checks': summary['graph_checks'], 'coverage': summary['coverage']})
""")
    markdown(
        "### 2. Verify the saved source-query identity\n\nThis checks the query bound by the completed audit; it does not claim to re-execute the heavy raw-source join here.\n"
    )
    code("""source_sql = (repo / 'scripts/peer_source_audit.sql').read_text(encoding='utf-8')
assert source_sql == audit['source_query']
print({'raw_source_query_bound': True, 'query_lines': len(source_sql.splitlines())})
""")
    markdown("## Results\n\n### 3. Recompute all50 account aggregates with independent SQL\n")
    code("""import math
query = (repo / 'scripts/lead_challenge_audit.sql').read_text(encoding='utf-8')
query = query.replace('__ACCOUNT_GLOB__', (operation / 'accounts/*.jsonl').as_posix())
with duckdb.connect() as connection:
    cursor = connection.execute(query)
    columns = [column[0] for column in cursor.description]
    recomputed = {row[0]: dict(zip(columns, row)) for row in cursor.fetchall()}
assert len(recomputed) == 50
for row in summary['rows']:
    actual = recomputed[row['account_key']]
    for field in ('net_return', 'final_nav', 'cost_cny', 'max_drawdown'):
        assert math.isclose(actual[field], row[field], rel_tol=1e-10, abs_tol=1e-6)
print({'independently_recomputed_accounts': len(recomputed), 'aggregate_reconciliation': True})
""")
    markdown("### 4. Inspect every primary identity, without winner-only filtering\n")
    code("""for row in summary['rows']:
    if row['policy'] == 'peer':
        print({key: row[key] for key in ('identity', 'roundtrip_bps', 'return2023', 'return2024', 'net_return', 'sharpe', 'max_drawdown')})
print({'exploratory_survivors': summary['screen_survived'], 'validated_alpha': summary['validated_alpha']})
""")
    markdown(
        f"## Takeaways\n\n{survivors}/6 pass the full exploratory screen, not Alpha Court.\n"
        "All native trial, graph and account evidence remains available locally. No final-test reopening or trading is authorized.\n"
        "Validation: every plain-Python code cell executed in order by `scripts/build_peer_notebook.py`.\n"
        "Jupyter frontend/kernel QA was not run: nbformat,nbclient and ipykernel are not installed.\n"
        "Optional frontend check after installing Jupyter: `python -m jupyter nbconvert --execute --to notebook --inplace notebooks/V11_17_AUDIT.ipynb`.\n"
    )
    namespace = {}
    execution = 0
    for i, cell in enumerate(cells):
        cell["id"] = f"peer-audit-{i + 1}"
        if cell["cell_type"] == "code":
            execution += 1
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                # Only the fixed, reviewed cell literals authored above; no external code input.
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
    assert all(
        isinstance(c["source"], list) and c["cell_type"] in ("code", "markdown") for c in cells
    )
    target = Path("notebooks/V11_17_AUDIT.ipynb")
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
