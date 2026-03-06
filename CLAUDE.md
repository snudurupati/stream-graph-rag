# stream-graph-rag — CLAUDE.md

## Project Mission
Reference architecture for real-time Account Intelligence using
Pathway (stream processing) + Memgraph (knowledge graph).

## Core Use Case
Sales Director QBR scenario: detect SEC filings + CRM events
and update account risk score in <60 seconds.

## Stack
- Stream processor: Pathway (Python/Rust, single container)
- Graph DB: Memgraph (Docker, port 7687)
- Schema validation: Pydantic
- Entity resolution: 3-Tier (Hash → Graph Neighbor → LLM Judge)
- Observability: OpenTelemetry from Day 1
- Demo UI: Streamlit

## Current Sprint
[Update this every sprint]

## Conventions
- All Pydantic models live in /models
- Pathway pipelines live in /pipelines
- Tests use pytest, run via `pytest tests/`
- Docker stack starts with `docker compose up -d`
