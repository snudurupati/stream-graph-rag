# tests/test_telemetry.py
# Unit tests for LatencyTracker — no live Memgraph required.

import time

import pytest

from observability.telemetry import LatencyTracker


@pytest.fixture
def tracker() -> LatencyTracker:
    t = LatencyTracker()
    yield t
    t.reset()


def test_record_event_received_stores_entry(tracker: LatencyTracker) -> None:
    """record_event_received stores a pending entry keyed by event_id."""
    tracker.record_event_received("evt-1", "SEC_EDGAR", "acme")
    assert "evt-1" in tracker._pending
    assert tracker._pending["evt-1"]["source"] == "SEC_EDGAR"
    assert tracker._pending["evt-1"]["company"] == "acme"


def test_record_graph_written_calculates_elapsed(tracker: LatencyTracker) -> None:
    """record_graph_written records a non-negative elapsed_ms and removes pending entry."""
    tracker.record_event_received("evt-2", "SEC_EDGAR", "beta corp")
    time.sleep(0.01)  # ensure measurable elapsed time
    tracker.record_graph_written("evt-2")

    assert "evt-2" not in tracker._pending
    assert len(tracker._elapsed_ms) == 1
    assert tracker._elapsed_ms[0] >= 10.0  # at least 10ms


def test_get_stats_known_values(tracker: LatencyTracker) -> None:
    """get_stats returns correct percentiles for a known input set."""
    # Inject 10 known latency values directly.
    tracker._elapsed_ms = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    stats = tracker.get_stats()

    assert stats["total_events_tracked"] == 10
    assert 50.0 <= stats["p50_ms"] <= 60.0
    assert 90.0 <= stats["p95_ms"] <= 100.0
    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 100.0
    assert stats["mean_ms"] == 55.0
    assert "last_event_wall" in stats


def test_reset_clears_all_state(tracker: LatencyTracker) -> None:
    """reset() clears pending entries, elapsed samples, and last_event_ts."""
    tracker.record_event_received("evt-3", "SALESFORCE", "delta")
    tracker._elapsed_ms = [5.0, 10.0]
    tracker._last_event_ts = time.monotonic()

    tracker.reset()

    assert tracker._pending == {}
    assert tracker._elapsed_ms == []
    assert tracker._last_event_ts is None
    assert tracker.get_stats()["total_events_tracked"] == 0


def test_record_graph_written_unknown_event_id_is_noop(tracker: LatencyTracker) -> None:
    """record_graph_written for an unknown event_id does not raise."""
    tracker.record_graph_written("does-not-exist")  # must not raise
    assert tracker._elapsed_ms == []
