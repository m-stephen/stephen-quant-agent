from datetime import datetime

from stephen_quant.discovery.response_resources import process_memory


def test_process_peak_memory_is_measured_not_guessed():
    result = process_memory()
    assert result["pid"] > 0 and result["peak_rss_bytes"] > 0
    assert datetime.fromisoformat(result["measured_at"]).tzinfo is not None
    if result.get("current_rss_bytes"):
        assert result["peak_rss_bytes"] >= result["current_rss_bytes"]
    if result["physical_total_bytes"] is not None:
        assert result["physical_total_bytes"] >= result["physical_available_bytes"] > 0
