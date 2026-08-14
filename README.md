# Genesis OS — Enterprise Decision Intelligence

**IBM track (built with IBM Bob) · Google Cloud Agentic Cinema Hackathon · Convergence Studios**

A standalone decision-governance system for a film studio. Where its siblings discover
(Parallel), operate (Grafana), and remember (ClickHouse), this system **decides**:

> *"Given everything we know — what should we do, are we allowed to do it, and who must say yes?"*

Proposals arrive with evidence. Criterion scores are **computed in code** from declared
weights (Gemini evaluates qualitative criteria with citations, never emits the aggregate).
A versioned **policy engine — built with IBM Bob — judges compliance in code**
(`COMPLIANT / VIOLATION / NEEDS_REVIEW / EXEMPT`, each finding citing its clause). The
governance verdict is a function of findings. Authorization is a durable Temporal signal
held for a human. Approved decisions emit an **Authorized Software Objective executed by
IBM Bob** — the decision literally becomes software, with the delivery evidence attached
to the dossier.

```
Proposal → Evidence Package → Criterion Scores (code) → Policy Findings (code, Bob-built engine)
  → Governance Verdict → RECOMMENDED → Studio Head signal (approve / reject / request revision)
  → AUTHORIZED → Authorized Software Objective → IBM Bob → ACTIONED → CLOSED → DataHub
```

## Built with IBM Bob (track requirement)

| Evidence | Where |
|---|---|
| Bob-built policy engine + policy packs | [`app/governance/`](app/governance/) · [`policy/`](policy/) |
| Bob-built console dossier panel | [`frontend/components/PolicyFindings.tsx`](frontend/components/PolicyFindings.tsx) |
| Session records, plans, diffs | [`docs/bob-evidence/`](docs/bob-evidence/) |
| Software-Action delivery (flagship demo) | attached to the decision dossier + video |

Bob is used exactly as the track prescribes — **in the development process** — while the
shipped runtime's AI is Gemini via `google-genai` (Vertex AI) only.

## Runtime proof (hackathon compliance)

| Requirement | Where |
|---|---|
| Google Cloud AI at runtime (`google-genai`, Vertex Gemini) | [`app/tools/google/gemini.py`](app/tools/google/gemini.py) |
| IBM Bob in the development process (demonstrable) | [`docs/bob-evidence/`](docs/bob-evidence/) + README table above |
| Confluent (encouraged) — decision-ledger stream | [`app/events/ledger.py`](app/events/ledger.py) |

## Quickstart

```bash
cd ops && docker compose up -d && cd ..                 # PG · NATS · Temporal · Redis · MinIO
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                                    # optional — boots in MOCK mode without it
.venv/bin/python -m seed.proposals                      # flagship proposal fixture
.venv/bin/uvicorn app.main:app --port 8030              # API
.venv/bin/python -m app.workflows.worker                # Temporal worker
cd frontend && npm install && npm run dev               # governance chamber on :3030
```

`GENESIS_MOCK=1` runs the full loop from a clean clone with no keys and no Docker.

## Architecture

Locked review: [`docs/architecture/system-04-ibm.v2.locked.md`](docs/architecture/system-04-ibm.v2.locked.md).
Preserved production stack, all deployed: PostgreSQL (durable dossiers) · Temporal (durable
DecisionWorkflow, human authorization signal with a bounded revision loop) · NATS
(`genesis.enterprise.events`) · **Confluent Cloud** (`genesis.enterprise.ledger`
system-of-record stream) · Redis (decision latch) · MinIO (dossier snapshots) · DataHub
(decisions + policy packs with lineage) · OpenTelemetry → Cloud Trace.

Part of the **Genesis OS** federation (five standalone partner systems + a coordination
layer none of them depend on). This system runs entirely alone.

## License

MIT — see [LICENSE](LICENSE).
