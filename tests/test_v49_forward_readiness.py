from pathlib import Path

from stephen_quant.workflows.v49_forward_readiness import run_v49_forward_readiness


def _files(root: Path, days: range) -> None:
    root.mkdir(parents=True)
    for day in days:
        (root / f"202608{day:02d}.csv").write_text("fixture\n", encoding="utf-8")


def test_v49_requires_twenty_five_shared_post_cutoff_dates(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("daily", "flow", "auction")]
    _files(roots[0], range(17, 32))
    _files(roots[1], range(17, 31))
    _files(roots[2], range(17, 30))
    report = run_v49_forward_readiness(
        *roots, output_dir=tmp_path / "output", as_of="2026-08-31"
    )
    assert report.common_new_dates == 13
    assert not report.ready
    assert report.decision == "WAIT_FOR_NEW_COMMON_DATA"


def test_v49_ignores_future_named_files(tmp_path: Path) -> None:
    roots = [tmp_path / name for name in ("daily", "flow", "auction")]
    for root in roots:
        _files(root, range(17, 20))
        (root / "20990101.csv").write_text("future\n", encoding="utf-8")
    report = run_v49_forward_readiness(
        *roots, output_dir=tmp_path / "output", as_of="2026-08-18"
    )
    assert report.common_new_dates == 2
    assert report.latest_common_date == "2026-08-18"
