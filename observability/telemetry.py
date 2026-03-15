# observability/telemetry.py
# OpenTelemetry tracer init + LatencyTracker for end-to-end pipeline instrumentation.

import json
import logging
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

logger = logging.getLogger(__name__)

# Shared stats file — written by pipeline process, read by dashboard process.
STATS_FILE = Path(tempfile.gettempdir()) / "akf_latency_stats.json"


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

def init_tracer(service_name: str) -> trace.Tracer:
    """Initialize an OTel tracer with ConsoleSpanExporter and return it."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)


tracer: trace.Tracer = init_tracer("autonomous-knowledge-fabric")


# ---------------------------------------------------------------------------
# LatencyTracker
# ---------------------------------------------------------------------------

class LatencyTracker:
    """Tracks event-received → graph-written latency across the pipeline."""

    def __init__(self) -> None:
        self._pending: dict[str, dict] = {}   # event_id → {ts, source, company}
        self._elapsed_ms: list[float] = []
        self._last_event_ts: Optional[float] = None
        self._last_event_wall: Optional[str] = None  # ISO string for cross-process use

    def record_event_received(
        self, event_id: str, source: str, company_name: str
    ) -> None:
        """Record that an event entered the pipeline (before any processing)."""
        self._pending[event_id] = {
            "ts": time.monotonic(),
            "source": source,
            "company": company_name,
        }

    def record_graph_written(self, event_id: str) -> None:
        """Calculate elapsed ms and log. No-op for unknown event_id."""
        entry = self._pending.pop(event_id, None)
        if entry is None:
            return
        elapsed_ms = (time.monotonic() - entry["ts"]) * 1000
        self._elapsed_ms.append(elapsed_ms)
        self._last_event_ts = time.monotonic()
        self._last_event_wall = datetime.now(timezone.utc).isoformat()
        logger.info(
            "LATENCY event_id=%s company=%s source=%s elapsed_ms=%.1f",
            event_id, entry["company"], entry["source"], elapsed_ms,
        )
        print(
            f"LATENCY event_id={event_id} company={entry['company']} "
            f"source={entry['source']} elapsed_ms={elapsed_ms:.1f}",
            flush=True,
        )
        self._flush_stats_file()

    def get_stats(self) -> dict:
        """Return percentile stats over all completed events."""
        samples = sorted(self._elapsed_ms)
        n = len(samples)
        if n == 0:
            return {
                "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
                "min_ms": 0.0, "max_ms": 0.0, "mean_ms": 0.0,
                "total_events_tracked": 0,
                "last_event_wall": None,
            }

        def _pct(p: float) -> float:
            idx = (p / 100) * (n - 1)
            lo, hi = int(idx), min(int(idx) + 1, n - 1)
            return samples[lo] + (idx - lo) * (samples[hi] - samples[lo])

        return {
            "p50_ms": round(_pct(50), 1),
            "p95_ms": round(_pct(95), 1),
            "p99_ms": round(_pct(99), 1),
            "min_ms": round(samples[0], 1),
            "max_ms": round(samples[-1], 1),
            "mean_ms": round(sum(samples) / n, 1),
            "total_events_tracked": n,
            "last_event_wall": self._last_event_wall,
        }

    def last_event_monotonic(self) -> Optional[float]:
        """Monotonic timestamp of the most recently written event, or None."""
        return self._last_event_ts

    def reset(self) -> None:
        """Clear all state."""
        self._pending.clear()
        self._elapsed_ms.clear()
        self._last_event_ts = None
        self._last_event_wall = None

    def _flush_stats_file(self) -> None:
        """Write current stats to STATS_FILE for cross-process dashboard reads."""
        try:
            STATS_FILE.write_text(json.dumps(self.get_stats()))
        except OSError:
            pass


def read_stats_file() -> dict:
    """Read stats written by the pipeline process. Returns zero-stats if unavailable."""
    try:
        return json.loads(STATS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0,
            "min_ms": 0.0, "max_ms": 0.0, "mean_ms": 0.0,
            "total_events_tracked": 0,
            "last_event_wall": None,
        }


# Global singleton used by pipelines.
latency_tracker = LatencyTracker()
