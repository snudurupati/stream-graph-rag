# Sprint Handoff Notes

## Sprint Completed
Sprint 9 (Week 2, Day 3) — 2026-03-15

## What Was Built

### Sprint 1 — Pathway + Memgraph hot-link
- `hello_pathway.py`: minimal Pathway pipeline printing 3 rows (proves Pathway works)
- `test_connection.py`: connects to Memgraph on port 7687, runs `RETURN 1` query

### Sprint 2 — AccountEvent Pydantic schema (`models/account_event.py`)
- `EventSource` enum: SEC_EDGAR, SALESFORCE, ZENDESK
- `RiskSignal` enum: TAKEOVER_BID, EARNINGS_MISS, EXECUTIVE_DEPARTURE, CRITICAL_SUPPORT, CONTRACT_RENEWAL_AT_RISK
- `AccountEvent` model with `company_name` normalization and identifier validation
- 4 pytest tests: 4 passed

### Sprint 3 — Live SEC EDGAR ingestion pipeline (`pipelines/sec_ingestion.py`)
- Polls Atom feed (40 8-Ks) + EFTS JSON every 30 seconds
- Deduplicates by `entry_id`, extracts `AccountEvent` with risk-signal keyword matching
- Pathway connector: `SECFeedSubject` → `pw.io.python.read` → `pw.io.subscribe`

### Sprint 4 — Synthetic CRM & support event generator (`pipelines/synthetic_crm.py`)
- 5 seed companies (Apple, Microsoft, Tesla, JPMorgan, Walmart)
- `SalesforceEventGenerator` + `ZendeskEventGenerator` alternating every 10 seconds
- 47 parametrized pytest tests: 47 passed

### Sprint 5 — Week 1 wrap-up & scaffolding
- Published Week 1 Substack post, updated README and CLAUDE.md
- Created stub files for graph, scoring, dashboard, baseline_rag packages

### Sprint 6 — Graph write-back via Bolt (`graph/memgraph_client.py`)
- `MemgraphClient` with 3-retry backoff, `upsert_account`, `upsert_event`,
  `get_account_with_relationships`
- Both pipelines wired to call `upsert_event()` per event
- 7 integration tests against live Memgraph

### Sprint 7 — Cypher query layer + Agent Context API
- 4 read methods on `MemgraphClient`: `get_account_context`, `get_high_risk_accounts`,
  `get_accounts_updated_since`, `search_accounts`
- `graph/context_api.py`: `get_agent_context()` + `freshness_label()` (LIVE/RECENT/STALE)
- 4 integration tests: 4 passed

### Sprint 8 — SEC feed URL + entry parsing fixes
- `count=40`, CIK parsed from title (not URL), `AccountEvent.timestamp` = filing date
- CLAUDE.md: SEC 8-K Item codes → RiskSignal mapping documented

### Sprint 9 — OpenTelemetry instrumentation + live latency dashboard
- **`observability/telemetry.py`**:
  - `init_tracer(service_name)` → `TracerProvider` + `ConsoleSpanExporter`
  - Global `tracer` instance (`"autonomous-knowledge-fabric"`)
  - `LatencyTracker` class: `record_event_received(event_id, source, company)`,
    `record_graph_written(event_id)`, `get_stats()` → p50/p95/p99/min/max/mean,
    `reset()`, `last_event_monotonic()`
  - Flushes stats to `$TMPDIR/akf_latency_stats.json` after every event for
    cross-process dashboard reads
  - Global `latency_tracker` singleton
- **`observability/latency_dashboard.py`**:
  - Reads `akf_latency_stats.json`, renders live panel every 30s
  - Context freshness derived from `last_event_wall` ISO timestamp via `freshness_label()`
- **`graph/memgraph_client.py`**:
  - `upsert_event()` wrapped in `tracer.start_as_current_span("graph.upsert")`
  - Logs `BOLT_WRITE company={name} elapsed_ms={ms}` per write
- **`pipelines/sec_ingestion.py`**:
  - `record_event_received()` called on first RSS detection (after `_parse_atom_title`)
  - `record_graph_written()` called after successful `upsert_event()`
- **`pipelines/synthetic_crm.py`**: same instrumentation, source = SALESFORCE/ZENDESK
- **`observability/__init__.py`**: package init created
- **`tests/test_telemetry.py`**: 5 unit tests (no live Memgraph required)

## What Broke and How It Was Fixed

| Problem | Fix |
|---|---|
| `feedparser` returned 0 entries from SEC | Added `User-Agent` header |
| `docker-compose.yml` was a shell script | Rewrote to proper YAML |
| Default `.venv` is Python 3.14 — no pyarrow wheels | Use `.venv312/` (Python 3.12) |
| `.venv312/bin/pip` broken after project rename | Use `python3.12 -m pip` |
| `.venv312` accidentally committed (160MB binary) | `git filter-repo` + `.gitignore`, force-push |
| Memgraph requires `admin/admin` auth | Probed both auth configs before writing client |
| `neo4j` driver not in requirements | Installed + frozen (`neo4j==6.1.0`) |
| CIK parsed from URL path (unreliable) | Parse from Atom title directly via updated regex |
| `AccountEvent.timestamp` set to ingest time | Set from `entry.updated` ISO string |
| `latency_tracker` is in-process singleton — dashboard in separate process sees 0 events | Flush stats to `$TMPDIR/akf_latency_stats.json`; dashboard reads file |
| `record_event_received()` called with raw title string as company name | Moved call to after `_parse_atom_title()` so normalized name is logged |

## Real Output Observed

```
pytest tests/ -v
67 passed in 0.96s

Pipeline LATENCY log:
LATENCY event_id=urn:tag:sec.gov,...  company=ispecimen  source=SEC_EDGAR  elapsed_ms=810.1
BOLT_WRITE company=ispecimen elapsed_ms=1

OTel span (ConsoleSpanExporter):
{
  "name": "graph.upsert",
  "attributes": {"company_name": "ispecimen", "source": "SEC_EDGAR", "elapsed_ms": 1},
  "start_time": "2026-03-15T18:27:05.438521Z",
  "end_time":   "2026-03-15T18:27:05.440112Z"
}

Live dashboard (pipeline running):
══════════════════════════════════════════
AUTONOMOUS KNOWLEDGE FABRIC — LIVE STATS
══════════════════════════════════════════
Timestamp:          2026-03-15 18:33:37 UTC
Events tracked:     39
P50 latency:        896.4ms
P95 latency:        914.9ms
P99 latency:        916.4ms
Min latency:        863.2ms
Max latency:        916.9ms
Mean latency:       894.3ms
Context freshness:  LIVE (sub-60s)
══════════════════════════════════════════
```

**Latency notes:**
- Cold-start batch (~810–916ms): first RSS poll emits 139 entries simultaneously;
  Pathway sequences them through `_on_change`, so entries at the back of the queue
  wait for earlier ones — not representative of steady-state latency
- Bolt write latency (warm connection): **0–1ms** per upsert
- Steady-state streaming latency expected: **~20–100ms** (single event, warm pipeline)

## Known Issues (Sprint 10 Cleanup)
- [x] LATENCY log company field showed raw title, not normalized name — fixed this sprint
- Cold-start batch latency (~810ms) is not representative of steady-state streaming
  latency (~20–100ms); needs a single-event benchmark to confirm

## Next Sprint Goal

**Sprint 10 — Risk signal accuracy: Item-code mapping**
- Update `_SIGNAL_PATTERNS` in `sec_ingestion.py` to use correct 8-K Item codes
  per CLAUDE.md mapping:
  - Item 1.02 → CONTRACT_RENEWAL_AT_RISK
  - Item 2.01 → TAKEOVER_BID
  - Item 2.05 → EXECUTIVE_DEPARTURE (currently matching Item 5.02 — wrong item number)
  - Item 2.06 → EARNINGS_MISS
  - Item 3.01 → EARNINGS_MISS (nearest proxy until DELISTING_RISK added in Month 2)
- Add `tests/test_signal_extraction.py` with fixtures covering each Item code
- Implement `scoring/account_health.py`: weighted signal score stored as `a.risk_score`
  in Memgraph (TAKEOVER_BID=40, EXECUTIVE_DEPARTURE=30, EARNINGS_MISS=20,
  CRITICAL_SUPPORT=15, CONTRACT_RENEWAL_AT_RISK=10, clamped to [0,100])
