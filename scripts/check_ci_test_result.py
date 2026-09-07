"""Fail closed on missing, partial or failing pytest JUnit evidence."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def check(path):
    root = ET.parse(Path(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError("no completed pytest test suite")
    total = 0
    for suite in suites:
        declared = int(suite.attrib["tests"])
        cases = suite.findall("testcase")
        if declared != len(cases) or any(c.find("failure") is not None for c in cases):
            raise ValueError("incomplete or failing test cases")
        if any(c.find("error") is not None for c in cases):
            raise ValueError("test case error")
        if int(suite.attrib["failures"]) or int(suite.attrib["errors"]):
            raise ValueError("failed test suite")
        total += sum(c.find("skipped") is None for c in cases)
    if total <= 0:
        raise ValueError("no successful test cases")
    return total


if __name__ == "__main__":
    print(f"Completed JUnit evidence: {check(sys.argv[1])} successful test cases")
