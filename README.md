# 🚀 Autonomous Knowledge Fabric
### A Real-Time Account Intelligence Reference Architecture

> *"Most enterprise AI agents are failing in production because they rely on stale context — we're feeding 2026-speed models with 1996-speed batch pipelines."*

**stream-graph-rag** is a 90-day, build-in-public project that solves the **"Missing Middle"** of the enterprise AI stack: the gap between high-velocity business events and the context your agents actually reason over.

Built with **Pathway** (stateful stream processing) + **Memgraph** (live knowledge graph) to deliver sub-60-second account intelligence — directly from SEC filings, CRM webhooks, and support events.

---

## 📖 The Problem: Context Debt

Batch-based RAG creates a **"Context Debt"** — a growing gap between what your agent *believes* and what is *actually true* — that is the primary cause of production AI failures in relationship-intensive enterprise workflows.

**The QBR Scenario:**
A Sales Director walks into a Quarterly Business Review with "Global Corp." Their RAG agent says the account is *"Stable."* In reality, 20 minutes ago:
- An SEC filing hit the wire showing a hostile takeover bid
- A support ticket was just escalated to "Critical" for their main subsidiary

Traditional RAG misses this. **stream-graph-rag** flags it in under 60 seconds.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Event Sources                           │
│   SEC EDGAR RSS    Synthetic CRM    Synthetic Zendesk       │
└──────────┬──────────────┬─────────────────┬────────────────┘
           │              │                 │
           ▼              ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│              Pathway Stream Processor (Single Container)    │
│   ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│   │ Normalization│  │  3-Tier      │  │  OpenTelemetry  │  │
│   │ & Extraction │─▶│  Resolver    │─▶│  Instrumented   │  │
│   │ (Pydantic)   │  │  Engine      │  │  Pipeline       │  │
│   └──────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Memgraph (Live Knowledge Graph / Hot State)    │
│                                                             │
│   [Global Corp]──owns──[Subsidiary A]──has──[CriticalCase]  │
│        │                                                    │
│        └──filing──[SEC: Hostile Takeover Bid]               │
└─────────────────────────────────┬───────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────┐
│         Account Intelligence Agent + Streamlit Dashboard    │
│                                                             │
│   Account: Global Corp    Risk Score: 🔴 CRITICAL           │
│   Context Freshness: 14 seconds ago    ████████░░ 82/100    │
└─────────────────────────────────────────────────────────────┘
```

### The Three-Tier Entity Resolver (Core IP)

| Tier | Method | Catches | LLM Cost |
|------|--------|---------|----------|
| **Tier 1** | Deterministic hashing (normalize, trim, regex) | ~60% of duplicates | $0 |
| **Tier 2** | Graph-contextual neighbor matching in Memgraph | ~30% of remaining | $0 |
| **Tier 3** | LLM-as-Judge via `gpt-4o-mini` + Instructor | Final ~10% ambiguous cases | Minimal |

---

## 🗓️ 90-Day Sprint Roadmap

### MONTH 1 — "The Pulse" Foundation
**Theme: Visibility & Ingestion**
**Goal: Prove the live view works. An observer sees a news item hit the wire and the graph updates its risk score in <60 seconds.**

---

#### Week 1 — Environment & Schema
**The Surgical Start**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 1** | 45 min | Repo setup. Pathway + Memgraph (Docker) hot-linked and verified. |
| **Sprint 2** | 45 min | `AccountEvent` Pydantic schema handling both SEC filings and synthetic CRM webhooks. |
| **Sprint 3** | 45 min | Pathway connected to SEC EDGAR RSS. Raw entities printing to console. |
| **Sprint 4** | 45 min | Synthetic event generator emitting Zendesk tickets for 5 hardcoded seed companies. |

**Week 1 Milestone:** Pipeline is breathing. Events flow from source → console.

**Blog Post:** *"Week 1: Why I Chose Pathway Over Spark for Real-Time AI Context (And What a Senior Spark Engineer Noticed Immediately)"*

---

#### Week 2 — Graph Foundation
**Getting Data Into Memgraph**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 5** | 45 min | Pathway writing normalized entities to Memgraph via Bolt. |
| **Sprint 6** | 45 min | Basic Cypher queries: fetch account node + all 1-hop relationships. |
| **Sprint 7** | 45 min | OpenTelemetry instrumented from source event to graph write. End-to-end latency visible. |
| **Sprint 8** | 45 min | Ghost Node pattern: candidate buffer for low-evidence entities. |

**Week 2 Milestone:** SEC entity lands in Memgraph within 60 seconds of filing. Latency is measured, not claimed.

**Blog Post:** *"Week 2: The 'Ghost Node' Pattern — How We Solve the Entity Resolution Bootstrap Problem"*

---

#### Week 3 — Risk Scoring
**Making the Graph Speak**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 9** | 45 min | Account Health Score model: 4-signal weighted sum (filing severity, support priority, recency, relationship depth). |
| **Sprint 10** | 45 min | Pathway computing and writing risk score delta to Memgraph on each new event. |
| **Sprint 11** | 45 min | Streamlit dashboard v1: account list + risk score + "Context Freshness" counter. |
| **Sprint 12** | 45 min | End-to-end smoke test: SEC filing → graph update → dashboard refresh. |

**Week 3 Milestone:** Dashboard is live. Risk score updates visibly when a new SEC event arrives.

**Blog Post:** *"Week 3: Designing an Explainable Account Health Score — Why We Chose a Weighted Sum Over an LLM"*

---

#### Week 4 — Month 1 Hardening
**Making It Demo-Ready**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 13** | 45 min | Stress test: 100 synthetic events/minute. Measure latency degradation. |
| **Sprint 14** | 45 min | Failure recovery test: kill Memgraph, verify Pathway re-hydrates from log. |
| **Sprint 15** | 45 min | RAG baseline defined and committed: Pinecone + LlamaIndex, nightly batch, same 5 seed companies. |
| **Sprint 16** | 45 min | Month 1 retrospective doc + README updated with real latency numbers. |

**Month 1 Deliverable:** A live dashboard showing real companies, real SEC filings, entities extracted and risk-scored within 60 seconds of publication. Fully observable via OpenTelemetry.

**Blog Post:** *"Month 1 Retrospective: What We Built, What Broke, and Our Real Latency Numbers"*

---

### MONTH 2 — "The Identity" Engine
**Theme: Resolution & Maturity**
**Goal: Solve the "Acme Corp" duplication problem. A Ghost Node successfully merges with its parent after the second confirming event.**

---

#### Week 5 — Tier 1: Deterministic Resolver
**The Zero-Cost Foundation**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 17** | 45 min | Normalization pipeline: lowercase, strip legal suffixes (Inc/LLC/Corp/Ltd), trim whitespace. |
| **Sprint 18** | 45 min | Deterministic hash function. Collision test across 500 synthetic company name variants. |
| **Sprint 19** | 45 min | Tier 1 integrated into Pathway pipeline. Duplicate rate measured on live SEC feed. |
| **Sprint 20** | 45 min | Metrics: Tier 1 catch rate logged to OpenTelemetry. Target: >60% of duplicates resolved. |

**Blog Post:** *"Week 5: How Regex and Hashing Solve 60% of Entity Duplication for Free"*

---

#### Week 6 — Tier 2: Graph-Contextual Resolver
**The Relationship-Aware Shortcut**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 21** | 45 min | 1-hop neighbor query: given new entity, find existing nodes sharing domain/CIK/executive. |
| **Sprint 22** | 45 min | Confidence scoring: shared CIK = 1.0, shared domain = 0.8, shared executive = 0.6. |
| **Sprint 23** | 45 min | Tier 2 merge logic: auto-merge above threshold, flag for Tier 3 below. |
| **Sprint 24** | 45 min | Test: "Acme" + "CEO: John Doe" resolves to existing "Acme Corp" node. Ghost Node committed. |

**Blog Post:** *"Week 6: Why Your Knowledge Graph Is Also Your Best Entity Resolver"*

---

#### Week 7 — Tier 3: LLM-as-Judge
**The Ambiguity Tie-Breaker**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 25** | 45 min | Instructor-structured prompt: Match / No-Match / Merge + confidence + reasoning. |
| **Sprint 26** | 45 min | Batching logic: Tier 3 calls queued and sent in batches of 10. Cost per resolution logged. |
| **Sprint 27** | 45 min | Human-in-the-loop flag: low-confidence Tier 3 decisions surfaced in Streamlit for review. |
| **Sprint 28** | 45 min | End-to-end resolver test: 1000 synthetic entities, measure Tier 1/2/3 split and total LLM cost. |

**Blog Post:** *"Week 7: Using LLMs as a Tie-Breaker, Not a Crutch — The Economics of 3-Tier Resolution"*

---

#### Week 8 — Integration & Operational Hardening
**Making the Full Stack Production-Credible**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 29** | 45 min | Docker Compose v1: full stack starts in one command. Verified cold-start time. |
| **Sprint 30** | 45 min | Salesforce-schema synthetic data: `Account_ID`, `Opportunity_Stage`, `ARR`, `Contract_Renewal_Date`. |
| **Sprint 31** | 45 min | Zendesk-schema synthetic data: `Case_Priority`, `Account_ID`, `Escalation_Time`, `SLA_Breach`. |
| **Sprint 32** | 45 min | Month 2 retrospective. Resolver accuracy documented. Docker Compose confirmed working. |

**Month 2 Deliverable:** The Three-Tier Resolver is live, tested, and cost-documented. A "Ghost Node" for a new subsidiary successfully merges with its parent company after the second confirming event.

**Blog Post:** *"Month 2 Retrospective: Entity Resolution Is Solved — Here Are the Numbers"*

---

### MONTH 3 — "The CFO" Demo
**Theme: ROI & Comparison**
**Goal: Prove value-per-query and operational simplicity. The QBR Hero demo is compelling enough to be shared by a VP of Sales on LinkedIn.**

---

#### Week 9 — The Comparison Setup
**Rigging a Fair Fight**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 33** | 45 min | RAG baseline hardened: same 5 seed companies, same documents, nightly batch refresh confirmed. |
| **Sprint 34** | 45 min | Identical query set defined for both systems: 10 account health questions, logged and frozen. |
| **Sprint 35** | 45 min | Both systems answer query set. Results logged with timestamps. No cherry-picking. |
| **Sprint 36** | 45 min | Latency comparison dashboard: stream-graph-rag vs RAG baseline, side by side. |

**Blog Post:** *"Week 9: How to Run a Fair Comparison — Why We Froze Our Baseline in Month 1"*

---

#### Week 10 — The QBR Hero Demo
**The Cinematic Scenario**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 37** | 45 min | Real SEC filing selected (last 30 days, real public company). Scenario scripted. |
| **Sprint 38** | 45 min | Synthetic Salesforce event created for same company. Escalation timeline built. |
| **Sprint 39** | 45 min | Demo flow: RAG agent says "Stable" → stream-graph-rag flags "Critical" in <60s. Recorded. |
| **Sprint 40** | 45 min | Demo video recorded. Streamlit dashboard polished for screen recording. |

**Blog Post:** *"Week 10: The QBR Demo — Watch an AI Agent Catch a Hostile Takeover in 47 Seconds"*

---

#### Week 11 — The Whitepaper
**Building the CFO Artifact**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 41** | 45 min | Infrastructure cost model: stream-graph-rag vs nightly RAG at 500 accounts / 10K events/day. |
| **Sprint 42** | 45 min | Latency analysis: end-to-end P50/P95/P99 from OpenTelemetry data. Real numbers only. |
| **Sprint 43** | 45 min | Failure recovery section: Memgraph crash → Pathway re-hydration. Time-to-recovery measured. |
| **Sprint 44** | 45 min | "Phase 2: Closed-Loop Intelligence" section written. Agent actions as graph events. |

**Blog Post:** *"Week 11: The Full Cost Model — Is Real-Time Context Worth 3x the Infrastructure?"*

---

#### Week 12 — Publication & Leverage
**Shipping the Honeypot**

| Sprint | Duration | Deliverable |
|--------|----------|-------------|
| **Sprint 45** | 45 min | README finalized. Architecture diagrams polished. Installation guide verified cold. |
| **Sprint 46** | 45 min | Whitepaper README published. All latency/cost claims cited to OpenTelemetry data. |
| **Sprint 47** | 45 min | "Practitioner's Guide" blog: what a senior Spark engineer learned switching to Pathway. |
| **Sprint 48** | 45 min | LinkedIn/Twitter launch post. Demo video published. Repo made public if not already. |

**Month 3 Deliverable:** The QBR Hero demo video. The whitepaper README with real numbers. A Docker Compose that starts the full stack in one command. A public repo with 12 weekly blog posts as the paper trail.

**Blog Post:** *"The Final Demo: stream-graph-rag vs Traditional RAG — A Practitioner's Honest Verdict"*

---

## 📊 Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| End-to-end latency (P50) | < 60 seconds | OpenTelemetry |
| End-to-end latency (P95) | < 120 seconds | OpenTelemetry |
| Tier 1 resolver catch rate | > 60% | Pipeline metrics |
| Tier 3 LLM cost per 1000 entities | < $0.50 | OpenAI usage logs |
| Docker Compose cold-start | < 2 minutes | Manual measurement |
| Memgraph recovery after crash | < 5 minutes | Chaos test logs |

---

## 🛠️ Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Stream processor | [Pathway](https://pathway.com) | Rust core, Python-native, incremental deltas by default |
| Knowledge graph | [Memgraph](https://memgraph.com) | In-memory graph, Bolt protocol, hot-state model |
| Schema validation | [Pydantic](https://docs.pydantic.dev) | Type-safe event models, Pathway-native |
| LLM Judge | [gpt-4o-mini](https://openai.com) + [Instructor](https://python.useinstructor.com) | Structured outputs, minimal cost |
| Observability | [OpenTelemetry](https://opentelemetry.io) | Vendor-neutral, from Day 1 |
| Dashboard | [Streamlit](https://streamlit.io) | Fast iteration, no frontend overhead |
| Baseline RAG | [Pinecone](https://pinecone.io) + [LlamaIndex](https://llamaindex.ai) | Fair, production-representative baseline |

---

## 📁 Repository Structure

```
stream-graph-rag/
├── CLAUDE.md                    # AI co-pilot context (update every sprint)
├── docker-compose.yml           # Full stack: one command
├── models/
│   └── account_event.py         # Core Pydantic schemas
├── pipelines/
│   ├── sec_ingestion.py         # SEC EDGAR RSS → Pathway
│   ├── synthetic_crm.py         # Faker-based CRM event generator
│   └── resolver/
│       ├── tier1_deterministic.py
│       ├── tier2_graph_context.py
│       └── tier3_llm_judge.py
├── graph/
│   └── memgraph_client.py       # Bolt connection + Cypher helpers
├── scoring/
│   └── account_health.py        # Risk score model
├── dashboard/
│   └── app.py                   # Streamlit dashboard
├── baseline_rag/                # Pinecone + LlamaIndex baseline
│   └── nightly_batch.py
├── observability/
│   └── telemetry.py             # OpenTelemetry setup
├── tests/
├── docs/
│   ├── whitepaper.md            # The CFO artifact
│   └── weekly/                  # 12 weekly blog posts
│       ├── week-01.md
│       ├── week-02.md
│       └── ...
└── README.md                    # This file
```

---

## 📝 Weekly Blog Series

All posts published at [nudurupati.co](https://nudurupati.co) and cross-posted to LinkedIn.

| Week | Title | Status |
|------|-------|--------|
| 1 | Why I Chose Pathway Over Spark (From a Spark Veteran) | 🔜 |
| 2 | The Ghost Node Pattern — Solving the Bootstrap Problem | 🔜 |
| 3 | Designing an Explainable Account Health Score | 🔜 |
| 4 | Month 1 Retrospective: Real Latency Numbers | 🔜 |
| 5 | How Regex Solves 60% of Entity Duplication for Free | 🔜 |
| 6 | Why Your Knowledge Graph Is Your Best Entity Resolver | 🔜 |
| 7 | LLMs as a Tie-Breaker, Not a Crutch | 🔜 |
| 8 | Month 2 Retrospective: The Resolver Numbers | 🔜 |
| 9 | How to Run a Fair AI Comparison | 🔜 |
| 10 | Watch an AI Agent Catch a Hostile Takeover in 47 Seconds | 🔜 |
| 11 | Is Real-Time Context Worth 3x the Infrastructure? | 🔜 |
| 12 | The Final Verdict: Practitioner's Honest Assessment | 🔜 |

---

## 🗺️ What's Next (Phase 2)

This reference architecture intentionally scopes to a **one-way flow**: Events → Pipeline → Graph → Agent. Phase 2 closes the loop:

**Closed-Loop Intelligence:** Agent actions (flagging an account, sending an alert, updating a CRM record) flow back into the graph as first-class events. `Agent flagged Global Corp as At-Risk at 09:47` becomes a relationship that future reasoning builds on.

---

## 🤝 Contributing & Feedback

This is a **build-in-public** project. Feedback, issues, and PRs welcome at any stage.

If you're a practitioner who has tried to solve this problem in production — especially if you've hit the entity resolution wall — I want to hear from you.

---

## 📄 License

MIT — use it, fork it, build on it.

---

*Built by [Sreeram Nudurupati](https://www.linkedin.com/in/snudurupati) — a practitioner with 5 years of production Kafka + Spark experience, who got tired of explaining to stakeholders why the AI was confidently wrong.*
