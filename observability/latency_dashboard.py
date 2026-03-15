# observability/latency_dashboard.py
# Prints live latency stats every 30 seconds. Run alongside a pipeline.

import os
import time
from datetime import datetime, timezone

from graph.context_api import freshness_label
from observability.telemetry import read_stats_file

REFRESH_SECS = 30
BORDER = "═" * 42


def _context_freshness(last_event_wall: str | None) -> str:
    if last_event_wall is None:
        return "NO DATA"
    try:
        last_dt = datetime.fromisoformat(last_event_wall)
        age_secs = int((datetime.now(timezone.utc) - last_dt).total_seconds())
        return freshness_label(age_secs)
    except ValueError:
        return "UNKNOWN"


def _render() -> str:
    stats = read_stats_file()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    freshness = _context_freshness(stats.get("last_event_wall"))
    return (
        f"\n{BORDER}\n"
        f"AUTONOMOUS KNOWLEDGE FABRIC — LIVE STATS\n"
        f"{BORDER}\n"
        f"Timestamp:          {now}\n"
        f"Events tracked:     {stats['total_events_tracked']}\n"
        f"P50 latency:        {stats['p50_ms']}ms\n"
        f"P95 latency:        {stats['p95_ms']}ms\n"
        f"P99 latency:        {stats['p99_ms']}ms\n"
        f"Min latency:        {stats['min_ms']}ms\n"
        f"Max latency:        {stats['max_ms']}ms\n"
        f"Mean latency:       {stats['mean_ms']}ms\n"
        f"Context freshness:  {freshness}\n"
        f"{BORDER}\n"
    )


def main() -> None:
    print("Latency dashboard starting — refreshes every 30s. Ctrl-C to stop.")
    while True:
        os.system("clear")
        print(_render())
        time.sleep(REFRESH_SECS)


if __name__ == "__main__":
    main()
