from stephen_quant.cli import build_parser
from stephen_quant.workflows.v48_historical_falsification import V48HistoricalConfig


def test_historical_falsification_identity_is_frozen() -> None:
    config = V48HistoricalConfig()
    config.validate()

    for changed in (
        V48HistoricalConfig(test_start="2020-01-02"),
        V48HistoricalConfig(buffer_ranks=5),
        V48HistoricalConfig(nav=2_000_000),
        V48HistoricalConfig(universe_top_n=40),
    ):
        try:
            changed.validate()
        except ValueError:
            pass
        else:
            raise AssertionError("changed historical identity must fail closed")


def test_historical_cli_requires_prior_ledgers_and_local_paths() -> None:
    args = build_parser().parse_args(
        [
            "v4.8-historical-falsification",
            "--paths-config",
            "configs/qd-paths.local.json",
            "--v46-registry",
            "artifacts/v46.sqlite3",
            "--v47-registry",
            "artifacts/v47.sqlite3",
        ]
    )

    assert args.paths_config == "configs/qd-paths.local.json"
    assert args.v46_registry == "artifacts/v46.sqlite3"
    assert args.v47_registry == "artifacts/v47.sqlite3"
    assert args.output == "reports/v4.8-historical-falsification"
