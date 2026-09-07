import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def probe():
    path = Path(__file__).resolve().parents[1] / "scripts/profile_response_storage.py"
    spec = importlib.util.spec_from_file_location("response_storage_probe_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resource_fixture_is_canonical_and_has_no_native_claims(tmp_path, probe, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "calendar": [f"day-{i}" for i in range(782)],
                "bars": {"day-0": {str(n): {"price": n + 0.5} for n in range(160)}},
                "ranks": {"day-0": {str(n): {"cell": n % 20} for n in range(160)}},
                "provider_id": "not-copied",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(probe, "SOURCE", source)
    monkeypatch.setattr(probe, "SOURCE_SHA", probe.file_sha(source))
    manifest = probe.fixture(tmp_path, 1)
    data = json.loads((tmp_path / manifest["file"]).read_bytes())
    assert set(data) == {"calendar", "bars", "ranks", "synthetic_only"}
    assert manifest["bars"] == manifest["ranks"] == 160
    assert probe.streaming_sha256_json(data) == manifest["sha256"]
    assert probe.streaming_sha256_json(probe.legacy_freeze(data)) == manifest["sha256"]
    with pytest.raises(FileExistsError):
        probe.fixture(tmp_path, 1)


def test_child_rejects_plan_change_before_fixture_read(tmp_path, probe, monkeypatch):
    (tmp_path / "RESOURCE_PLAN.json").write_text('{"version":1}', encoding="utf-8")
    monkeypatch.setattr(probe, "plan", lambda: {"version": 2})
    with pytest.raises(ValueError, match="plan or code changed"):
        probe.child(tmp_path, 1, "lower-copy")
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize(
    ("commit", "free", "reason"),
    [
        (11 * 1024**3, 20 * 1024**3, "private_commit_limit"),
        (100000, 1024**3, "free_physical_floor"),
        (100000, None, "free_memory_measurement_unavailable"),
    ],
)
def test_supervisor_stops_only_its_owned_child_and_keeps_receipt(
    tmp_path, probe, monkeypatch, commit, free, reason
):
    class Child:
        stopped = False

        def poll(self):
            return -15 if self.stopped else None

        def terminate(self):
            self.stopped = True

        def wait(self, **kwargs):
            assert self.stopped
            return -15

    child = Child()

    def spawn(*args, **kwargs):
        assert "ALPHAPAI_API_KEY" not in kwargs["env"]
        assert "ALPHAPAI_BASE_URL" not in kwargs["env"]
        return child

    monkeypatch.setenv("ALPHAPAI_API_KEY", "unit-test-only")
    monkeypatch.setenv("ALPHAPAI_BASE_URL", "unit-test-only")
    monkeypatch.setattr(probe.subprocess, "Popen", spawn)
    monkeypatch.setattr(probe.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(
        probe,
        "child_process_memory",
        lambda p: {
            "peak_rss_bytes": 10000,
            "peak_private_commit_bytes": commit,
            "physical_available_bytes": free,
        },
    )
    result = probe.supervised_child(tmp_path, 1, "legacy")
    assert child.stopped
    assert result["stopped_by_guard"] == reason and result["exit_code"] == -15
    assert result["samples"] == 1
    assert result["empirical_trial_delta"] == 0
    assert json.loads((tmp_path / "scale-1-legacy/SUPERVISOR.json").read_bytes()) == result
