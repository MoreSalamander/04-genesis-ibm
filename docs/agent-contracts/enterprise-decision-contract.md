# Enterprise Decision Contract (federation boundary)

The interface Genesis OS will consume through an adapter (Handoff §16). The
standalone owns this API; the federation calls it — never the reverse. No code
is shared: this document is the contract, vendored per repo.

## Direction

Genesis OS → **Enterprise Decision Contract** → IBM-system adapter → this API.

## Request

`POST /api/decisions` — `{"proposal": DecisionProposal}` → `202 {"id", "status", "execution"}`
One decision in governance at a time (Redis latch) — `409` with the holder's id otherwise.

`DecisionProposal`: `{title, description, category, amount_usd, vendor, requested_by,
evidence: [{kind: financial|operational|strategic|risk, statement, metric, value, unit,
source}]}` — the evidence package is where the federation injects what the three
intelligence systems produced (external signals, operational state, institutional
findings become evidence items with `source` pointing at the producing system).

`POST /api/decisions/{id}/authorization` — `{"decision": "approved"|"rejected"|"revise",
"note"}` — routed through the durable Temporal signal; "revise" loops governance with the
note as guidance (bounded rounds).

`POST /api/decisions/{id}/action` — `{"summary", "evidence_refs": [...]}` — attaches the
IBM Bob delivery evidence to the authorized objective, closing the decision.

## Result (decision dossier payload)

`GET /api/decisions/{id}` → the full dossier:

| Field | Meaning |
|---|---|
| `scores[]` | criterion scores **computed in code** (weights + normalized metrics); Gemini rationales cite evidence ids |
| `policy_findings[]` | rule-derived `state` ∈ COMPLIANT/VIOLATION/NEEDS_REVIEW/EXEMPT with clause, observed, threshold, pack version (engine built with IBM Bob) |
| `verdict` | `outcome` ∈ CLEAR/BLOCKED/ESCALATED + `required_tier` — a function of findings |
| `recommendation` | action, rationale, `strength` (computed from scores + verdict), caveats |
| `authorizations[]` | the human decision trail |
| `objective` | the **Authorized Software Objective** issued on approval — the §17 handoff artifact |
| `action_record` | IBM Bob delivery evidence (summary + evidence refs) |

## Events

NATS `genesis.enterprise.events` + JSONL audit: `decision.submitted/evaluated`,
`policy.finding`, `governance.verdict`, `recommendation.created`,
`authorization.decided`, `action.objective_issued`, `action.delivered`,
`decision.closed/incomplete`, `knowledge.promoted`. Ledger-grade events
(`authorization.decided`, `decision.closed`, `action.delivered`) additionally
stream to the Confluent topic `genesis.enterprise.ledger`.

## Guarantees

- Scores, findings, verdicts and strengths are computed in code — never model-asserted.
- A standing VIOLATION cannot be approved past — approval attempts force a revision round.
- Authorization is always a human signal on a durable workflow.
- Substrate failure yields `INCOMPLETE` with a reason — never fabricated governance.
