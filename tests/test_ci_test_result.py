"""The diagnostic debugger must not hide CI failures or missing test output."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ci_result", Path(__file__).resolve().parents[1] / "scripts/check_ci_test_result.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "document",
    [
        "<testsuites />",
        '<testsuite tests="0" failures="0" errors="0"/>',
        '<testsuite tests="1" failures="0" errors="0"/>',
        '<testsuite tests="1" failures="0" errors="0"><testcase><failure/></testcase></testsuite>',
        '<testsuite tests="1" failures="0" errors="0"><testcase><error/></testcase></testsuite>',
        '<testsuite tests="1" failures="0" errors="0"><testcase><skipped/></testcase></testsuite>',
        '<testsuite tests="1" failures="1" errors="0"><testcase/></testsuite>',
        '<testsuite tests="1" failures="0" errors="1"><testcase/></testsuite>',
    ],
)
def test_incomplete_or_failed_evidence_is_rejected(tmp_path, document):
    path = tmp_path / "pytest.xml"
    path.write_text(document)
    with pytest.raises(ValueError):
        module.check(path)


def test_missing_or_malformed_evidence_is_rejected(tmp_path):
    path = tmp_path / "pytest.xml"
    with pytest.raises(FileNotFoundError):
        module.check(path)
    path.write_text("<testsuite")
    with pytest.raises(module.ET.ParseError):
        module.check(path)


@pytest.mark.parametrize("wrapper", [False, True])
def test_completed_evidence_counts_success_and_keeps_declared_skips(tmp_path, wrapper):
    xml = '<testsuite tests="2" failures="0" errors="0"><testcase/>'
    xml += '<testcase><skipped/></testcase></testsuite>'
    if wrapper:
        xml = f"<testsuites>{xml}</testsuites>"
    path = tmp_path / "pytest.xml"
    path.write_text(xml)
    assert module.check(path) == 1
