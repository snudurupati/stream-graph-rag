# pipelines/sec_ingestion.py
# Pathway pipeline: poll SEC EDGAR RSS + EFTS → normalize → emit AccountEvent.

import re
import time as time_module
import warnings
from html import unescape
from typing import Optional

import feedparser
import pathway as pw
import requests
from pydantic import ValidationError

from graph.memgraph_client import MemgraphClient
from models.account_event import AccountEvent, EventSource, RiskSignal
from observability.telemetry import latency_tracker

# ---------------------------------------------------------------------------
# Feed URLs
# ---------------------------------------------------------------------------

ATOM_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=8-K&dateb=&owner=include&count=40&search_text=&output=atom"
)

EFTS_URL = (
    "https://efts.sec.gov/LATEST/search-index"
    "?q=%22hostile+takeover%22&dateRange=custom&startdt=2025-01-01&forms=8-K"
)

# SEC rate-limit policy requires a descriptive User-Agent.
_HEADERS = {"User-Agent": "stream-graph-rag research@example.com"}

POLL_INTERVAL_SECS = 30

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

# Atom title: "8-K - Reservoir Media, Inc. (0001824403) (Filer)"
# Group 1 = company name, Group 2 = CIK number
_ATOM_TITLE_RE = re.compile(r"^[\w/\-]+ - (.+?)\s*\((\d+)\)")
# Strip HTML tags from summary
_HTML_TAG_RE = re.compile(r"<[^>]+>")

# EFTS display_names: "COMPANY NAME  (TICKER)  (CIK 0000946563)"
_EFTS_NAME_RE = re.compile(r"^(.+?)\s{2,}\(")
_EFTS_CIK_RE = re.compile(r"CIK\s+(\d+)", re.I)

# Risk-signal keyword patterns
_SIGNAL_PATTERNS: list[tuple[re.Pattern, RiskSignal]] = [
    (
        re.compile(r"takeover|acquisition|merger|hostile|Item\s+2\.01", re.I),
        RiskSignal.TAKEOVER_BID,
    ),
    (
        re.compile(r"departure|resign|terminat|Item\s+5\.02", re.I),
        RiskSignal.EXECUTIVE_DEPARTURE,
    ),
    (
        re.compile(r"restatement|miss|Item\s+4\.02", re.I),
        RiskSignal.EARNINGS_MISS,
    ),
]


def _extract_signals(text: str) -> list[RiskSignal]:
    return [sig for pat, sig in _SIGNAL_PATTERNS if pat.search(text)]


def _strip_html(text: str) -> str:
    return unescape(_HTML_TAG_RE.sub(" ", text)).strip()


def _parse_atom_title(title: str) -> tuple[str, Optional[str]]:
    """Return (company_name, cik_number) parsed from Atom entry title."""
    m = _ATOM_TITLE_RE.match(title)
    if m:
        return m.group(1).strip(), m.group(2)
    return title, None


def _efts_company_name(display_names: list[str]) -> str:
    if not display_names:
        return ""
    m = _EFTS_NAME_RE.match(display_names[0])
    return m.group(1).strip() if m else display_names[0].strip()


# ---------------------------------------------------------------------------
# Feed fetchers  →  list[dict]  (homogeneous schema)
# ---------------------------------------------------------------------------

def _fetch_atom_entries() -> list[dict]:
    feed = feedparser.parse(ATOM_FEED_URL, request_headers=_HEADERS)
    results = []
    for e in feed.entries:
        summary_raw = e.get("summary", e.get("title", ""))
        results.append(
            {
                "entry_id": e.get("id") or e.get("link", ""),
                "title": e.get("title", ""),
                "link": e.get("link", ""),
                "summary": _strip_html(summary_raw),
                "filing_date": e.get("updated", ""),
                "feed_source": "atom",
            }
        )
    return results


def _fetch_efts_entries() -> list[dict]:
    try:
        r = requests.get(EFTS_URL, timeout=10, headers=_HEADERS)
        r.raise_for_status()
        hits = r.json().get("hits", {}).get("hits", [])
        results = []
        for hit in hits:
            src = hit.get("_source", {})
            cik = (src.get("ciks") or [""])[0].lstrip("0") or None
            display_names = src.get("display_names") or []
            entity = _efts_company_name(display_names)
            form = src.get("form", "8-K")
            file_date = src.get("file_date", "")
            adsh = src.get("adsh", "")
            results.append(
                {
                    "entry_id": f"efts:{hit['_id']}",
                    "title": f"{form} - {entity}",
                    "link": (
                        f"https://www.sec.gov/cgi-bin/browse-edgar"
                        f"?action=getcompany&CIK={cik}"
                    )
                    if cik
                    else "",
                    "summary": (
                        f"{entity} filed {form} on {file_date}. "
                        f"Items: {', '.join(src.get('items', []))}. "
                        f"Accession: {adsh}"
                    ),
                    "filing_date": file_date,
                    "feed_source": "efts",
                }
            )
        return results
    except Exception as exc:
        warnings.warn(f"EFTS fetch failed: {exc}")
        return []


# ---------------------------------------------------------------------------
# Pathway schema
# ---------------------------------------------------------------------------

class RawEntrySchema(pw.Schema):
    entry_id: str
    title: str
    link: str
    summary: str
    filing_date: str
    feed_source: str


# ---------------------------------------------------------------------------
# Pathway input connector
# ---------------------------------------------------------------------------

# Tracks monotonic timestamp of self.next_json() per entry_id so _on_change
# can compute fetch_ms = time from submission to handler dispatch.
_submitted_ts: dict[str, float] = {}


class SECFeedSubject(pw.io.python.ConnectorSubject):
    """Polls both SEC feeds every POLL_INTERVAL_SECS; deduplicates by entry_id."""

    def run(self) -> None:
        seen: set[str] = set()
        while True:
            batch = _fetch_atom_entries() + _fetch_efts_entries()
            new_count = 0
            for entry in batch:
                eid = entry["entry_id"]
                if eid and eid not in seen:
                    seen.add(eid)
                    _submitted_ts[eid] = time_module.monotonic()
                    self.next_json(entry)
                    new_count += 1
            print(
                f"[poll] fetched {len(batch)} entries, "
                f"{new_count} new, {len(seen)} total seen",
                flush=True,
            )
            time_module.sleep(POLL_INTERVAL_SECS)


# ---------------------------------------------------------------------------
# AccountEvent extraction
# ---------------------------------------------------------------------------

def _row_to_account_event(row: dict) -> Optional[AccountEvent]:
    from datetime import datetime, timezone

    title: str = row.get("title", "")
    summary: str = row.get("summary", "")
    filing_date_str: str = row.get("filing_date", "")

    raw_text = summary or title
    company_name, cik_number = _parse_atom_title(title)

    if not company_name:
        warnings.warn(f"Skipping entry with empty company_name: {title!r}")
        return None

    timestamp = datetime.now(timezone.utc)
    if filing_date_str:
        try:
            timestamp = datetime.fromisoformat(filing_date_str)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    try:
        return AccountEvent(
            source=EventSource.SEC_EDGAR,
            company_name=company_name,
            cik_number=cik_number,
            raw_text=raw_text,
            risk_signals=_extract_signals(raw_text),
            timestamp=timestamp,
        )
    except ValidationError as exc:
        warnings.warn(f"Skipping malformed entry {title!r}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Pathway output subscriber
# ---------------------------------------------------------------------------

_event_count = 0
_graph_client: MemgraphClient | None = None


def _get_graph_client() -> MemgraphClient:
    global _graph_client
    if _graph_client is None:
        _graph_client = MemgraphClient()
    return _graph_client


def _on_change(key: pw.Pointer, row: dict, time: int, is_addition: bool) -> None:
    global _event_count
    if not is_addition:
        return

    eid = row.get("entry_id", "")
    t_submitted = _submitted_ts.pop(eid, None)

    # --- parse phase ---
    t_parse_start = time_module.monotonic()
    event = _row_to_account_event(row)
    t_parse_end = time_module.monotonic()

    if event is None:
        return
    _event_count += 1

    # Measurement starts HERE: parse is complete, company name is known.
    latency_tracker.record_event_received(eid, "SEC_EDGAR", event.company_name)

    # --- write phase ---
    try:
        _get_graph_client().upsert_event(event)
        t_write_end = time_module.monotonic()
        latency_tracker.record_graph_written(eid)

        signals_str = ", ".join(s.value for s in event.risk_signals) or "none"
        parse_ms = (t_parse_end - t_parse_start) * 1000
        write_ms = (t_write_end - t_parse_end) * 1000
        total_ms = parse_ms + write_ms
        fetch_ms = (t_parse_start - t_submitted) * 1000 if t_submitted else None

        print(
            f"Graph updated: {event.company_name} [{signals_str}] in {total_ms:.1f}ms",
            flush=True,
        )

        if _event_count <= 3:
            fetch_str = f"{fetch_ms:.1f}ms" if fetch_ms is not None else "n/a"
            print(
                f"  [DEBUG #{_event_count}] fetch_ms={fetch_str} "
                f"parse_ms={parse_ms:.1f} write_ms={write_ms:.1f} total_ms={total_ms:.1f}",
                flush=True,
            )
    except Exception as exc:
        warnings.warn(f"Graph write failed for {event.company_name}: {exc}")

    print(f"\n=== AccountEvent #{_event_count} ===")
    print(event.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    subject = SECFeedSubject()
    table = pw.io.python.read(subject, schema=RawEntrySchema, format="json")
    pw.io.subscribe(table, on_change=_on_change)
    pw.run()


if __name__ == "__main__":
    main()
