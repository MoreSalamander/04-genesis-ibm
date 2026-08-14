# System 04 — IBM + Bob — Architecture Review V2 (DRAFT — awaiting Studio Head approval)

> Prepared 2026-08-13 by the builder under the locking protocol: technology deep dive first,
> then the proposed architecture. On approval this exact document locks as
> `system-04-ibm.v2.locked.md`. Classification discipline applies throughout:
> **VERIFIED REQUIREMENT** (checked against live official sources) · **ARCHITECTURAL
> DECISION** (Genesis OS choice) · **RECOMMENDATION** (proposed, not locked) ·
> **INFERENCE** (derived, not explicitly stated).

---

## PART 1 — TECHNOLOGY DEEP DIVE

### 1.1 What IBM Bob is

**VERIFIED (live sources, 2026-08-13):** IBM Bob is IBM's AI-first software-development
partner, **generally available since 2026-04-28**. It plans, executes, validates and governs
multi-step software development and modernization tasks across the SDLC. It is a development
tool a human developer drives — an editor UI plus **BobShell**, which "extends the product
into terminal workflows."

### 1.2 What it does

**VERIFIED:**
- **Five specialized modes**: coding · asking questions about a codebase · planning ·
  advanced work · orchestration (multi-agent capabilities added 2026-07).
- **BobShell**: terminal workflows with "access to files, shell and command execution,
  documentation generation, and external tools through Model Context Protocol integrations."
- **Multi-model orchestration**: "a mix of frontier LLMs, open-source models, small language
  models (SLMs) and IBM's Granite SLM family" — the platform picks the model per task.
- **Enterprise controls**: security embedded in workflows (prompt-injection and data-exposure
  screening); **Bobalytics** gives organizations visibility into productivity/quality/cost.
- **Plans**: Pro $20/mo (40 Bobcoins) · Ultra $200/mo (500 Bobcoins) · **complimentary
  30-day SaaS trial** (July 2026 announcement) · IBM Z package in private preview.

**UNVERIFIED (thin public detail — resolve empirically once the user's trial is active):**
the exact export format of Bob session records/audit trails, and repo-integration mechanics.
The build plan treats evidence capture as an empirical first step, exactly like 03's MCP probe.

### 1.3 Track requirements (VERIFIED verbatim, live rules 2026-08-13)

> "your project must be built using **IBM Bob as part of the development process**. Use of
> **Confluent** is optional but strongly encouraged to power real-time data and event-driven
> workflows. **Projects that do not demonstrate usage of IBM Bob will not meet the
> requirements for the IBM track, regardless of how the code was written.** Strong submissions
> should also demonstrate how AI meaningfully improves a workflow, enhances decision-making,
> elevates a customer experience, or drives a measurable operational outcome."

And the AI-limitation clause permits, alongside Google Cloud AI, "the **built-in AI-powered
features of the specific Partner's product** relevant to your chosen track."

### 1.4 The critical architectural reading

**INFERENCE (load-bearing, stated plainly):** unlike Parallel/Grafana/ClickHouse — whose
requirement is *runtime* integration — the IBM track's requirement is **development-time**:
the project must be *built with* Bob, demonstrably. Bob's non-Google internal models are
compliant precisely because Bob is the partner product used as the track prescribes; the
**shipped system's runtime AI remains Gemini-only** (google-genai, Vertex). Therefore:

- Bob is the **construction partner and the executor of authorized software actions during
  development** — structurally essential and demonstrable, never a runtime API dependency.
- This also satisfies Handoff §4's locked conceptual flow — `Authorized Software Objective →
  IBM Bob → Understand → Plan → Implement → Test → Validate → Deliver` — as a demonstrated
  development-process path.

### 1.5 What 04 must NOT be (locked, Handoff §4–§8)

One submission (IBM + Bob together, not two partners). Independently runnable — no Genesis OS
dependency, no Replit dependency in either direction. Bob is not a footnote. Do not redesign
the locked role: **Enterprise Decision Intelligence** — evaluation, governance, authorization,
decision execution where appropriate, decision monitoring.

---

## PART 2 — PROPOSED ARCHITECTURE

### 2.1 Identity

```
SYSTEM:  Genesis OS — Enterprise Decision Intelligence
FUNCTION: Decision & Governance
PARTNER: IBM (+ IBM Bob)
MISSION: Turn proposals plus evidence into governed, authorized, actioned decisions —
         with the policy engine in code and the authority in human hands.
```

**Studio Head question:** *"Given everything we know — what should we do, are we allowed to
do it, and who must say yes?"*

01 discovers, 02 operates, 03 remembers; **04 decides**. That separation keeps the five
submissions "unique and substantially different" (VERIFIED clause).

### 2.2 The decision lineage (ARCHITECTURAL DECISION — mirrors the locked evidence discipline)

```
Decision Proposal → Evidence Package → Criterion Scores → Policy Findings →
Governance Verdict → Authorization Record → Software Action Record → Closure
```

Anti-"AI-said-so" mechanics, same spine as 03:
1. **Criterion scores are computed in code** from declared weights over the evidence package;
   Gemini evaluates qualitative criteria with citations into the evidence, never emits the
   aggregate number.
2. **Policy findings are rule-derived, never model-asserted**: the policy engine (code)
   evaluates versioned policy packs and yields `COMPLIANT / VIOLATION / NEEDS_REVIEW /
   EXEMPT` per policy, each with the triggering clause and values.
3. **The governance verdict is a function of policy findings** (any VIOLATION blocks;
   NEEDS_REVIEW escalates the required authorization tier) — computed, auditable.
4. Gemini writes the dossier narrative and the recommendation rationale; every number and
   every compliance outcome traces to code.

### 2.3 Agent organization

| Agent | Owns | Permissions |
|---|---|---|
| **Decision Executive** | the decision objective: intake → dossier → recommendation | read, analyze, recommend |
| **Evaluation Agent** | multi-criteria analysis (financial, operational, strategic, risk) over the evidence package | read, analyze |
| **Governance Agent** | policy-pack evaluation IN CODE; findings + verdict + required authorization tier | read, analyze |
| **Action Liaison** | approved decision → **Authorized Software Objective** (Bob task package); delivery-evidence tracking | read, package |
| Studio Head (human) | authorization: approve / reject / request revision — always human for consequential decisions | authorize |

Cognitive roles instantiated per decision, not permanent processes (locked pattern).

### 2.4 Data, policy & event architecture

- **PostgreSQL :5436** — durable decision dossiers (the 01/02/03 document-store pattern).
- **Policy packs**: versioned YAML in-repo (`policy/*.yaml`) — diffable, auditable studio
  policy as data: budget thresholds, vendor-concentration caps, risk-class rules, approval
  tiers. The engine loads a named pack version; the dossier records which version judged it.
- **Temporal :7236/UI :8236** — durable `DecisionWorkflow`; the authorization is the proven
  **human-decision signal** (approve / reject / request-revision loops back with guidance,
  bounded — 03's deeper-analysis pattern).
- **NATS :4226** — `genesis.enterprise.events` + JSONL audit.
- **Redis :6383** — one-active-decision latch (acquire before persist). **MinIO :9020/:9021**
  — dossier + evidence snapshots. **DataHub** — decisions and policy packs registered with
  lineage (decision ← evidence ← policies). **OTel → Cloud Trace.**
- **Confluent — INCLUDED (ARCHITECTURAL DECISION, Studio Head 2026-08-13)** — "optional but
  strongly encouraged" (VERIFIED). Confluent Cloud (free tier, user account) carries the
  **decision-ledger stream**: every `authorization.decided` / `decision.closed` event is
  mirrored to a Confluent topic (`genesis.enterprise.ledger`) as the enterprise
  system-of-record feed. It *adds* an enterprise integration; NATS keeps its locked
  internal-fabric role. Degrades to NATS+JSONL with a surfaced warning if unreachable.

### 2.5 IBM Bob integration (the heart of the track)

Two demonstrable, development-time paths — both evidence-captured:

**(a) BUILT WITH BOB (scope decided, Studio Head 2026-08-13).** Defined subsystems of this
repo are built in Bob sessions on the user's trial account (builder-guided): the **policy
engine + policy packs** (self-contained, testable, demo-relevant) and one console component
(the policy-findings dossier panel). Every session's plan,
transcript/BobShell record, and diff lands in `docs/bob-evidence/` (format verified
empirically at first session — the 1.2 UNVERIFIED note), plus a README "Built with IBM Bob"
section and a video segment showing Bob working on this exact repo.

**(b) THE SOFTWARE-ACTION PATH.** When the Studio Head authorizes the flagship decision, the
Action Liaison emits the **Authorized Software Objective** — and during development that
objective is executed BY BOB, demonstrably (Handoff §4's flow): Bob implements the authorized
change (e.g. the render-capacity provisioning config + its tests) and the delivery evidence
(diff, test run, session record) attaches to the decision dossier as the Software Action
Record. The demo shows an authorized decision *becoming software* through Bob.

**Runtime compliance stated plainly (VERIFIED alignment):** the deployed 04 runtime calls
Gemini only. Bob's usage is the development process itself — exactly what the track requires
and demonstrates.

### 2.6 The decision loop (locked global loop, instantiated)

```
SUBMITTED → EVALUATING → GOVERNANCE_REVIEW → RECOMMENDED →
AWAITING_AUTHORIZATION (durable Temporal pause; human signal) →
  approved → AUTHORIZED → ACTIONED (Bob evidence) → CLOSED → DataHub promotion
  rejected → CLOSED(REJECTED)
  request-revision → loops to EVALUATING with guidance (bounded rounds)
substrate failure at any stage → INCOMPLETE (honest; latch released; never fabricated)
```

### 2.7 Gemini / Google Cloud roles

Gemini (`gemini-flash-latest`, Vertex, global): proposal interpretation, qualitative criterion
evaluation with citations, dossier narrative, recommendation rationale, revision-guidance
incorporation. Google Cloud: Vertex AI, Secret Manager, Cloud Trace; Cloud Run at the hosted
pass (API + console; no partner sidecar — Bob is not a runtime service).

### 2.8 Human boundary, failure, security

- Every consequential decision requires the human signal; policy findings CANNOT be overridden
  by cognition — only by an explicit human exemption recorded in the dossier.
- Failures: substrate down → INCOMPLETE; under-evidenced criteria are scored as such and
  lower the computed recommendation strength; policy engine errors block (fail-closed).
- Scoped permissions per agent; secrets in env/Secret Manager; full audit via events + OTel +
  MinIO dossiers.

### 2.9 Repository & console

`04-genesis-ibm/` mirrors the proven production skeleton (`app/` agents·governance·workflows·
memory·knowledge·events·api, `policy/` packs, `docs/bob-evidence/`, `ops/` compose
[PG·NATS·Temporal·Redis·MinIO], `frontend/` console **:3030**, tests, MIT, README with
runtime-proof + built-with-Bob links). API **:8030**. Console = fourth distinct design —
**the governance chamber**: dark charcoal + brass/gold accents, dossier-centric layout
(proposal → scores → policy findings with clause citations → verdict banner → authorization
panel → action record), nothing like 01's signal desk, 02's ops room, or 03's paper ledger.

### 2.10 Demo (≤3 min, flagship decision)

*"Approve the $2.8M render-farm capacity expansion (vendor: HelioCompute)?"* — intake with
evidence package → computed criterion scores → governance catches a **VIOLATION** (vendor
concentration exceeds the policy cap — clause cited) → Studio Head requests revision → revised
split-vendor proposal → COMPLIANT verdict → authorization (durable signal) → **Authorized
Software Objective → Bob implements the provisioning change on camera** → delivery evidence
attaches → CLOSED + DataHub promotion. Interleaved: Bob building the policy engine itself.

### 2.11 Events

`decision.submitted/evaluated`, `policy.finding`, `governance.verdict`,
`recommendation.created`, `authorization.decided`, `action.objective_issued`,
`action.delivered`, `decision.closed`, `decision.incomplete` — on
`genesis.enterprise.events` + JSONL audit (+ Confluent mirror if included).

### 2.12 Deviations & resolved questions

1. No Appendix E starting hypotheses existed for IBM — this draft derives solely from
   Handoff §4–§8 + the verified track rules; no silent deviations.
2. **RESOLVED (Studio Head, 2026-08-13): Confluent INCLUDED** as the decision-ledger stream
   (Confluent Cloud free tier; §2.4).
3. **RESOLVED (Studio Head, 2026-08-13): flagship decision = the $2.8M render-farm capacity
   expansion** (vendor HelioCompute; §2.10).
4. **RESOLVED (Studio Head, 2026-08-13): Bob build depth = guided sessions on the policy
   subsystem + one console component** (§2.5), with evidence capture from the first session.

### 2.13 User prerequisites for the build

1. **IBM Bob 30-day trial** account (ibm.com — Bob GA) — required before the Bob-built
   subsystem sessions and the Software-Action demo beat; I scaffold everything else first.
2. **Confluent Cloud free-tier** account — cluster + API key for the decision-ledger topic.
