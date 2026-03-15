# graph/memgraph_client.py
# Bolt connection pool + Cypher helpers for reading/writing the knowledge graph.

import time
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, SessionExpired

from models.account_event import AccountEvent

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
