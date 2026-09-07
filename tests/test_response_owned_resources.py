import os
import subprocess
import sys

import pytest

from stephen_quant.discovery.response_resources import child_process_memory


@pytest.mark.skipif(os.name != "nt", reason="Windows owned-child kernel memory measurement")
def test_owned_child_measurement_uses_that_process_not_parent():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        env={
            k: v
            for k, v in os.environ.items()
            if k not in ("ALPHAPAI_API_KEY", "ALPHAPAI_BASE_URL")
        },
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        result = child_process_memory(process)
        assert result["pid"] == process.pid != os.getpid()
        assert result["peak_rss_bytes"] > 0
        assert result["peak_private_commit_bytes"] > 0
        assert result["physical_total_bytes"] > result["physical_available_bytes"] > 0
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.skipif(os.name == "nt", reason="Non-Windows explicit capability gap")
def test_other_platforms_do_not_fabricate_child_peak_measurements():
    with pytest.raises(OSError, match="requires Windows"):
        child_process_memory(None)
