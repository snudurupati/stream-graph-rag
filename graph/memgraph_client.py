# graph/memgraph_client.py
# Bolt connection pool + Cypher helpers for reading/writing the knowledge graph.

import time
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from models.account_event import AccountEvent
from observability.telemetry import tracer

_BOLT_URI = "bolt://localhost:7687"
_AUTH = ("admin", "admin")


class MemgraphClient:
    def __init__(
        self,
        uri: str = _BOLT_URI,
        auth: tuple[str, str] = _AUTH,
        max_retries: int = 3,
        retry_backoff_secs: float = 2.0,
    ) -> None:
        self._uri = uri
        self._auth = auth
        self._max_retries = max_retries
        self._retry_backoff_secs = retry_backoff_secs
        self._driver = self._connect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                driver = GraphDatabase.driver(self._uri, auth=self._auth)
                driver.verify_connectivity()
                return driver
            except Exception as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(self._retry_backoff_secs)
        raise ConnectionError(
            f"Could not connect to Memgraph at {self._uri} "
            f"after {self._max_retries} attempts: {last_exc}"
        )

    def _run(self, cypher: str, params: dict | None = None) -> list[dict]:
        """Execute a Cypher query with retry on transient errors."""
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                with self._driver.session() as session:
                    result = session.run(cypher, params or {})
                    return [dict(r) for r in result]
            except (ServiceUnavailable, SessionExpired) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    self._driver = self._connect()
            except Exception as exc:
                raise exc
        raise ConnectionError(f"Query failed after {self._max_retries} retries: {last_exc}")

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------
    # Graph writes
    # ------------------------------------------------------------------

    def upsert_account(self, event: AccountEvent) -> None:
        """Merge Account node and attach RiskSignal nodes with HAS_SIGNAL edges."""
        now_iso = datetime.now(timezone.utc).isoformat()

        self._run(
            """
            MERGE (a:Account {company_name: $company_name})
            SET a.domain       = $domain,
                a.cik_number   = $cik_number,
                a.account_id   = $account_id,
                a.last_updated = $last_updated,
                a.source       = $source
            """,
            {
                "company_name": event.company_name,
                "domain":       event.company_domain,
                "cik_number":   event.cik_number,
                "account_id":   event.account_id,
                "last_updated": now_iso,
                "source":       event.source.value,
            },
        )

        for signal in event.risk_signals:
            self._run(
                """
                MERGE (s:RiskSignal {name: $signal_name})
                WITH s
                MATCH (a:Account {company_name: $company_name})
                MERGE (a)-[r:HAS_SIGNAL {signal: $signal_name}]->(s)
                SET r.timestamp = $ts
                """,
                {
                    "signal_name":  signal.value,
                    "company_name": event.company_name,
                    "ts":           now_iso,
                },
            )

    def upsert_event(self, event: AccountEvent) -> None:
        """Upsert Account + RiskSignals, then create a raw Event node with FILED edge."""
        with tracer.start_as_current_span("graph.upsert") as span:
            span.set_attribute("company_name", event.company_name)
            span.set_attribute("source", event.source.value)
            t0 = time.perf_counter()
            self._upsert_event_inner(event)
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            span.set_attribute("elapsed_ms", elapsed_ms)
            print(f"BOLT_WRITE company={event.company_name} elapsed_ms={elapsed_ms}", flush=True)

    def _upsert_event_inner(self, event: AccountEvent) -> None:
        self.upsert_account(event)

        now_iso = datetime.now(timezone.utc).isoformat()
        self._run(
            """
            MERGE (e:Event {event_id: $event_id})
            SET e.source     = $source,
                e.raw_text   = $raw_text,
                e.timestamp  = $timestamp
            WITH e
            MATCH (a:Account {company_name: $company_name})
            MERGE (a)-[:FILED]->(e)
            """,
            {
                "event_id":     event.event_id,
                "source":       event.source.value,
                "raw_text":     event.raw_text,
                "timestamp":    event.timestamp.isoformat(),
                "company_name": event.company_name,
            },
        )

    # ------------------------------------------------------------------
    # Graph reads
    # ------------------------------------------------------------------

    def get_account_context(self, company_name: str) -> dict | None:
        """Return structured account context for LLM agent consumption."""
        rows = self._run(
            """
            MATCH (a:Account {company_name: $name})
            OPTIONAL MATCH (a)-[:FILED]->(e:Event)
            OPTIONAL MATCH (a)-[:HAS_SIGNAL]->(s:RiskSignal)
            RETURN
              a.company_name AS company,
              a.cik_number AS cik,
              a.last_updated AS last_updated,
              COLLECT(DISTINCT e.raw_text)[..3] AS recent_events,
              COLLECT(DISTINCT s.name) AS risk_signals,
              COUNT(DISTINCT e) AS total_events
            """,
            {"name": company_name},
        )
        if not rows or rows[0]["company"] is None:
            return None

        row = rows[0]
        last_updated = row["last_updated"]
        context_age_seconds: float = 0.0
        if last_updated:
            try:
                updated_dt = datetime.fromisoformat(last_updated)
                now = datetime.now(timezone.utc)
                context_age_seconds = (now - updated_dt).total_seconds()
            except ValueError:
                pass

        return {
            "company_name": row["company"],
            "cik_number": row["cik"],
            "last_updated": last_updated,
            "total_events": row["total_events"],
            "recent_events": row["recent_events"] or [],
            "risk_signals": row["risk_signals"] or [],
            "context_age_seconds": int(context_age_seconds),
        }

    def get_high_risk_accounts(self) -> list[dict]:
        """Return accounts ordered by risk signal count (descending), max 20."""
        rows = self._run(
            """
            MATCH (a:Account)-[:HAS_SIGNAL]->(s:RiskSignal)
            RETURN
              a.company_name AS company,
              COLLECT(DISTINCT s.name) AS signals,
              COUNT(DISTINCT s) AS signal_count
            ORDER BY signal_count DESC LIMIT 20
            """
        )
        return [dict(r) for r in rows]

    def get_accounts_updated_since(self, seconds_ago: int) -> list[dict]:
        """Return accounts whose last_updated is within the given window."""
        rows = self._run(
            """
            MATCH (a:Account)
            RETURN a.company_name AS company, a.last_updated AS last_updated, a.cik_number AS cik
            """
        )
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=seconds_ago)
        result = []
        for row in rows:
            lu = row.get("last_updated")
            if lu:
                try:
                    dt = datetime.fromisoformat(lu)
                    if dt >= cutoff:
                        result.append(dict(row))
                except ValueError:
                    pass
        return result

    def search_accounts(self, query: str) -> list[dict]:
        """Case-insensitive substring search on company_name, returns up to 10."""
        rows = self._run(
            """
            MATCH (a:Account)
            WHERE toLower(a.company_name) CONTAINS toLower($query)
            RETURN a.company_name, a.last_updated, a.cik_number
            LIMIT 10
            """,
            {"query": query},
        )
        return [dict(r) for r in rows]

    def get_account_with_relationships(self, company_name: str) -> dict | None:
        """Return the Account node and all 1-hop relationships as a dict."""
        rows = self._run(
            """
            MATCH (a:Account {company_name: $company_name})
            OPTIONAL MATCH (a)-[r]->(n)
            RETURN a, collect({rel_type: type(r), target: n, props: properties(r)}) AS rels
            """,
            {"company_name": company_name},
        )
        if not rows:
            return None

        row = rows[0]
        account_node = dict(row["a"]) if row["a"] else {}
        rels = []
        for rel in row["rels"]:
            if rel.get("rel_type"):
                rels.append(
                    {
                        "type":   rel["rel_type"],
                        "target": dict(rel["target"]) if rel["target"] else {},
                        "props":  rel["props"] or {},
                    }
                )

        return {"account": account_node, "relationships": rels}
