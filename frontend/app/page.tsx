"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Decision,
  DecisionSummary,
  SystemStatus,
  VendorAlternate,
  getDecision,
  getEvents,
  getStatus,
  getVendorAlternates,
  listDecisions,
  sendAuthorization,
  submitDecision,
} from "@/lib/api";
import { PolicyFindings } from "@/components/PolicyFindings";
import { Elapsed, EmptyState, Note, Pulse, RuntimeBar, cascade, proofItems } from "@/lib/alive";

const STAGES = ["SUBMITTED", "EVALUATING", "GOVERNANCE_REVIEW", "RECOMMENDED",
                "AWAITING_AUTHORIZATION", "AUTHORIZED", "ACTIONED", "CLOSED"];
const TERMINAL = new Set(["CLOSED", "REJECTED", "INCOMPLETE"]);
// Stages where the chamber is actually working. RECOMMENDED and
// AWAITING_AUTHORIZATION wait on the Studio Head — no clock, no shimmer.
const WORKING = new Set(["SUBMITTED", "EVALUATING", "GOVERNANCE_REVIEW", "AUTHORIZED"]);

// Flagship fixture mirror (seed/proposals.py) — the intake button submits this.
const FLAGSHIP = {
  title: "Render-farm capacity expansion — 2,400 GPU-node hours/day",
  description:
    "Expand the studio render farm by 2,400 GPU-node hours/day ahead of the FY27 VFX-heavy slate. " +
    "Single-vendor build-out with HelioCompute under the existing master services agreement; " +
    "delivery in two tranches over 14 weeks.",
  category: "capex",
  amount_usd: 2_800_000,
  vendor: "HelioCompute",
  requested_by: "studio-operations",
  evidence: [
    { kind: "financial", metric: "payback_months", value: 19, unit: "months", source: "finance/capex-model-fy27",
      statement: "Chargeback model projects 19-month payback at current render pricing." },
    { kind: "financial", metric: "capex_share_of_annual", value: 0.061, unit: "share", source: "finance/fy27-capital-plan",
      statement: "Request equals 6.1% of the FY27 capital budget." },
    { kind: "financial", metric: "projected_utilization", value: 0.86, unit: "share", source: "ops/demand-model-q3",
      statement: "Demand model projects 86% steady-state utilization of the expanded pool." },
    { kind: "operational", metric: "queue_saturation_pct", value: 91, unit: "%", source: "ops/telemetry-quarterly",
      statement: "Render queue has run at 91% average saturation for the trailing quarter." },
    { kind: "operational", metric: "overflow_incidents_90d", value: 9, unit: "count", source: "ops/incident-log",
      statement: "Nine queue-overflow incidents in the last 90 days forced overnight re-prioritization." },
    { kind: "strategic", metric: "slate_vfx_titles", value: 5, unit: "titles", source: "production/slate-fy27",
      statement: "Five FY27 titles are VFX-heavy and depend on in-house render capacity." },
    { kind: "risk", metric: "vendor_delivery_slip_days", value: 12, unit: "days", source: "procurement/vendor-history",
      statement: "HelioCompute's last two deliveries slipped 12 days on average." },
    { kind: "risk", metric: "integration_lead_weeks", value: 9, unit: "weeks", source: "ops/integration-history",
      statement: "Farm integration and burn-in historically takes 9 weeks." },
  ],
};

export default function Chamber() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [active, setActive] = useState<Decision | null>(null);
  const [ledger, setLedger] = useState<DecisionSummary[]>([]);
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeId = useRef<string | null>(null);
  // Evidence ids cited by the score card under the cursor — item 16's wiring.
  const [litEvidence, setLitEvidence] = useState<string[]>([]);
  // What the chamber is doing right now, shown the instant a signal is sent.
  const [inFlight, setInFlight] = useState("");
  const [alternates, setAlternates] = useState<VendorAlternate[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [s, list, evs] = await Promise.all([getStatus(), listDecisions(), getEvents(40)]);
      setStatus(s);
      setLedger(list);
      setEvents(evs.reverse());
      if (activeId.current) setActive(await getDecision(activeId.current));
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 4000); // self-heals when the backend returns
    return () => clearInterval(timer);
  }, [refresh]);

  // Real state always wins over the in-flight note: the moment the status
  // actually moves, the placeholder goes away.
  useEffect(() => { setInFlight(""); }, [active?.status]);

  // A BLOCKED verdict is the one place the chamber can help resolve its own
  // finding — ask the engine which vendors would clear the cap.
  useEffect(() => {
    if (!active || active.verdict?.outcome !== "BLOCKED") { setAlternates([]); return; }
    let live = true;
    getVendorAlternates(active.id)
      .then((rows) => { if (live) setAlternates(rows); })
      .catch(() => { if (live) setAlternates([]); });
    return () => { live = false; };
  }, [active?.id, active?.verdict?.outcome, active]);

  const submit = async () => {
    setBusy(true); setError("");
    try {
      const res = await submitDecision(FLAGSHIP);
      activeId.current = res.id;
      await refresh();
    } catch (err) {
      setError(String(err instanceof Error ? err.message : err));
    } finally { setBusy(false); }
  };

  const [amendVendor, setAmendVendor] = useState("");

  const authorize = async (decision: string) => {
    if (!active) return;
    setBusy(true); setError("");
    // Speak before the round trip: the chamber must never look asleep between
    // the click and the next poll.
    setInFlight(`Signal “${decision}” sent — the durable workflow is picking it up…`);
    try {
      const amendments = decision === "revise" && amendVendor.trim()
        ? { vendor: amendVendor.trim() } : {};
      const res = await sendAuthorization(active.id, decision, note, amendments);
      setInFlight(
        res.execution === "temporal"
          ? `Signal “${decision}” accepted by the durable workflow — awaiting the next stage.`
          : `Signal “${decision}” accepted — executing in-process (Temporal unavailable).`,
      );
      setNote(""); setAmendVendor("");
      await refresh();
    } catch (err) {
      setInFlight("");
      setError(String(err instanceof Error ? err.message : err));
    } finally { setBusy(false); }
  };

  const open = async (id: string) => {
    activeId.current = id;
    try { setActive(await getDecision(id)); }
    catch (err) { setError(String(err instanceof Error ? err.message : err)); }
  };

  const stageIndex = active
    ? TERMINAL.has(active.status) ? STAGES.length - 1 : STAGES.indexOf(active.status)
    : -1;
  const awaiting = active?.status === "AWAITING_AUTHORIZATION" || active?.status === "RECOMMENDED";
  const working = !!active && WORKING.has(active.status);
  const heartbeat = `${ledger.length}|${active?.status ?? ""}|${active?.scores.length ?? 0}|${events.length}`;

  return (
    <div className="frame">
      <header className="masthead">
        <div>
          <h1><a href="/">GENESIS OS — ENTERPRISE DECISION INTELLIGENCE</a></h1>
          <div className="dept">Convergence Studios · The Governance Chamber · IBM track, built with Bob</div>
        </div>
        <div className="mode">
          {status ? (
            <>
              <div><Pulse signal={heartbeat} /> Gemini {status.gemini_live ? <span className="live">LIVE</span> : "MOCK"}</div>
              <div>Confluent ledger {status.confluent_live ? <span className="live">LIVE</span> : <span className="stub">STUBBED</span>}</div>
              <div>policy engine: <span className={status.policy_engine.includes("pending") ? "stub" : "live"}>{status.policy_engine}</span></div>
            </>
          ) : (
            "backend offline — start uvicorn on :8030"
          )}
        </div>
      </header>

      {!active && ledger.length === 0 ? (
        <div style={{ margin: "30px 0 10px" }}>
          <EmptyState
            eyebrow="Enterprise Decision Intelligence · IBM track, built with Bob"
            title="A governance chamber that scores in code and narrates in Gemini."
            lead="Bring a capital proposal before the chamber and it scores every criterion
                  arithmetically, runs the evidence against a versioned policy pack built with IBM Bob,
                  returns a verdict it can defend clause by clause, and holds for your authorization —
                  then issues the authorized software objective for Bob to execute."
            action={
              <button className="btn solid" onClick={submit} disabled={busy}>
                START HERE — SUBMIT THE FLAGSHIP PROPOSAL · $2.8M RENDER-FARM EXPANSION
              </button>
            }
          />
          {error && <Note tone="bad">{error}</Note>}
        </div>
      ) : (
        <div className="intake">
          <span className="label">Bring a decision before the chamber</span>
          <button className="btn solid" onClick={submit} disabled={busy}>
            SUBMIT THE FLAGSHIP PROPOSAL — $2.8M RENDER-FARM EXPANSION
          </button>
          {error && <Note tone="bad">{error}</Note>}
        </div>
      )}

      {active && (
        <>
          <div className="stage-rail">
            {STAGES.map((stage, i) => {
              const here = i === stageIndex;
              return (
                <div key={stage}
                     className={"stage" + (i < stageIndex ? " done" : "") + (here ? " current" : "")
                                + (here && working ? " alive-active" : "")}>
                  {i === STAGES.length - 1 && TERMINAL.has(active.status) ? active.status : stage.replace("_", " ")}
                  {here && working && <> <Elapsed stage={active.status} running={working} /></>}
                </div>
              );
            })}
          </div>
          {active.round > 1 && (
            <div className="round-flag">
              ROUND {active.round} — revision requested: {active.revision_guidance.join(" · ")}
            </div>
          )}

          <div className="dossier">
            <div>
              <section className="section">
                <h2>Proposal <span className="tag">{active.id}</span></h2>
                <div className="proposal-card">
                  <div className="title">{active.proposal.title}</div>
                  <div className="figures">
                    <span><b>${(active.proposal.amount_usd / 1e6).toFixed(1)}M</b> requested</span>
                    <span>vendor <b>{active.proposal.vendor || "—"}</b></span>
                    <span>category <b>{active.proposal.category}</b></span>
                    <span>by {active.proposal.requested_by}</span>
                  </div>
                  <div className="desc">{active.proposal.description}</div>
                  <div className="evidence-list">
                    {active.proposal.evidence.map((item) => (
                      <div className={`evidence-item${litEvidence.includes(item.id) ? " lit" : ""}`}
                           id={`ev-${item.id}`} key={item.id}>
                        <span className="kind">{item.kind}</span>
                        <div>
                          {item.statement}
                          <div className="metric">{item.metric} = {item.value} {item.unit} · {item.source}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="section alive-cascade">
                <h2>Criterion scores <span className="tag">computed in code · rationale by Gemini</span></h2>
                {active.scores.map((score, i) => (
                  <div className="score-row" style={cascade(i)} key={score.id}>
                    <div>
                      <div className="name">{score.criterion}</div>
                      <div className="value">{score.score.toFixed(3)}</div>
                      <div className="hint">w {score.weight}</div>
                    </div>
                    <div>
                      <div className="score-bar"><div className="fill" style={{ width: `${score.score * 100}%` }} /></div>
                      <div className="basis">{score.basis}</div>
                      {score.rationale && <div className="rationale">{score.rationale}</div>}
                      {score.cited_evidence_ids.length > 0 && (
                        <div className="cited"
                             onMouseLeave={() => setLitEvidence([])}>
                          <span className="cited-label">computed from</span>
                          {score.cited_evidence_ids.map((eid) => (
                            <button
                              className="ev-chip"
                              key={eid}
                              onMouseEnter={() => setLitEvidence([eid])}
                              onFocus={() => setLitEvidence([eid])}
                              onClick={() => {
                                const row = document.getElementById(`ev-${eid}`);
                                if (!row) return;
                                row.scrollIntoView({ behavior: "smooth", block: "center" });
                                row.classList.remove("alive-halo");
                                void row.offsetWidth;   // restart the halo
                                row.classList.add("alive-halo");
                              }}
                              title="Highlight this evidence item in the proposal above"
                            >
                              {eid}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {active.scores.length === 0 && <div className="hint">Evaluation running…</div>}
              </section>

              <section className="section">
                <h2>Policy findings <span className="tag">rule-derived · engine built with IBM Bob</span></h2>
                <PolicyFindings findings={active.policy_findings} />
              </section>

              {active.verdict && (
                <section className="section">
                  <h2>Governance verdict</h2>
                  <div className={`verdict-banner ${active.verdict.outcome}`}>
                    <span className="outcome">{active.verdict.outcome}</span>
                    <span className="tier">required tier: {active.verdict.required_tier} · pack {active.verdict.policy_version}</span>
                    <span className="basis">{active.verdict.basis}</span>
                  </div>
                </section>
              )}

              {active.recommendation && (
                <section className="section">
                  <h2>Recommendation &amp; authorization</h2>
                  <div className="rec-card">
                    <div className="action">{active.recommendation.action}</div>
                    <div className="rationale">{active.recommendation.rationale}</div>
                    <div className="strength-meter">
                      <span className="num">{Math.round(active.recommendation.strength * 100)}%</span>
                      <div className="bar"><div className="fill" style={{ width: `${active.recommendation.strength * 100}%` }} /></div>
                      <span className="lbl">strength = f(scores, verdict)</span>
                    </div>
                    {active.recommendation.caveats.length > 0 && (
                      <ul className="caveats">
                        {active.recommendation.caveats.map((caveat, i) => <li key={i}>{caveat}</li>)}
                      </ul>
                    )}
                    {awaiting ? (
                      <>
                        <div className="authorize-row">
                          <input placeholder="Note for the record (required to request revision)…"
                                 value={note} onChange={(e) => setNote(e.target.value)} />
                          {active.verdict?.outcome === "BLOCKED" && (
                            <input placeholder="Amend vendor (applied on revision)…"
                                   value={amendVendor} onChange={(e) => setAmendVendor(e.target.value)}
                                   style={{ maxWidth: 260 }} />
                          )}
                          <button className="btn solid" disabled={busy} onClick={() => authorize("approved")}>AUTHORIZE</button>
                          <button className="btn" disabled={busy || !note.trim()} onClick={() => authorize("revise")}>REQUEST REVISION</button>
                          <button className="btn danger" disabled={busy} onClick={() => authorize("rejected")}>REJECT</button>
                        </div>
                        {alternates.length > 0 && (
                          <div className="alternates">
                            <span className="alt-label">
                              clears the {alternates[0].cap != null
                                ? `${Math.round(alternates[0].cap * 100)}%`
                                : ""} concentration cap · pack {alternates[0].policy_version}
                            </span>
                            {alternates.map((alt) => (
                              <button className="alt-chip" key={alt.vendor}
                                      onClick={() => setAmendVendor(alt.vendor)}
                                      title={`Amending to ${alt.vendor} puts this proposal at `
                                             + `${(alt.share * 100).toFixed(1)}% of trailing-12-month spend`}>
                                {alt.vendor}
                                <span className="alt-share">{(alt.share * 100).toFixed(1)}%</span>
                              </button>
                            ))}
                          </div>
                        )}
                        {inFlight && <div className="in-flight">{inFlight}</div>}
                      </>
                    ) : (
                      <div className="auth-trail">
                        {active.authorizations.map((auth, i) => (
                          <div className="rec" key={i}>
                            <span className="decision-word">{auth.decision}</span>
                            {auth.note ? ` — ${auth.note}` : ""} · {auth.by}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </section>
              )}

              {active.objective && (
                <section className="section">
                  <h2>Authorized software objective <span className="tag">executed by IBM Bob</span></h2>
                  <div className="objective-card">
                    <div className="obj">{active.objective.objective}</div>
                    <ul>
                      {active.objective.requirements.map((req, i) => <li key={i}>{req}</li>)}
                    </ul>
                    {active.objective.acceptance_criteria.length > 0 && (
                      <div className="acceptance">
                        <div className="acc-head">
                          acceptance criteria
                          <span className="acc-count">
                            {active.action_record
                              ? `${active.objective.acceptance_criteria.length} delivered against`
                              : `${active.objective.acceptance_criteria.length} open`}
                          </span>
                        </div>
                        <ul className="acc-list">
                          {active.objective.acceptance_criteria.map((criterion, i) => (
                            <li key={i} className={active.action_record ? "met" : ""}>
                              <span className="box" aria-hidden="true">
                                {active.action_record ? "☑" : "☐"}
                              </span>
                              {criterion}
                            </li>
                          ))}
                        </ul>
                        {/* Delivery is attached per objective, not per criterion, so
                            this states what is actually known and no more. */}
                        <div className="acc-caveat">
                          {active.action_record
                            ? "Delivery evidence is attached to the objective as a whole — "
                              + "criterion-level proof lives in Bob's session record, not in this console."
                            : "Recorded at authorization · unchecked until Bob's delivery is attached."}
                        </div>
                      </div>
                    )}
                    {active.action_record ? (
                      <div className="action-delivered">
                        DELIVERED by {active.action_record.delivered_by} — {active.action_record.summary}
                        {active.action_record.evidence_refs.length > 0 &&
                          ` · evidence: ${active.action_record.evidence_refs.join(", ")}`}
                      </div>
                    ) : (
                      <div className="hint">Awaiting Bob delivery (SESSION-PLAN session 4) — attach via POST /api/decisions/{active.id}/action</div>
                    )}
                    {active.promotion && active.promotion.datahub_urns.length > 0 && (
                      <div className="promoted-note">promoted to DataHub with policy lineage</div>
                    )}
                  </div>
                </section>
              )}
              {active.status === "INCOMPLETE" && (
                <Note tone="bad">
                  INCOMPLETE — {active.incomplete_reason ?? "substrate unavailable"}; nothing was fabricated.
                </Note>
              )}
            </div>

            <aside>
              <section className="section">
                <h2>Event fabric</h2>
                <div className="event-feed">
                  {events.map((ev, i) => (
                    <div className="ev" key={i}>
                      <b>{String(ev.event)}</b>{" "}
                      {String((ev as { decision_id?: string }).decision_id ?? "")}
                    </div>
                  ))}
                </div>
              </section>
            </aside>
          </div>
        </>
      )}

      <section className="section alive-cascade">
        <h2>Decision ledger <span className="tag">{ledger.length} on record</span></h2>
        {ledger.map((item, i) => (
          <div className="ledger-item" style={cascade(i)} key={item.id} onClick={() => open(item.id)}>
            <span className="t">{item.title}</span>
            <span className="s">
              {item.status} · r{item.round}
              {item.verdict ? ` · ${item.verdict}` : ""}
              {item.strength != null ? ` · ${Math.round(item.strength * 100)}%` : ""}
            </span>
          </div>
        ))}
        {ledger.length === 0 && <div className="hint">No decisions on record — bring one before the chamber.</div>}
      </section>

      <RuntimeBar items={proofItems(status?.runtime_proof, [
        ["gemini", "Gemini"],
        ["confluent", "Confluent"],
        ["policy", "Policy pack"],
        ["temporal", "Temporal"],
        ["datahub", "DataHub"],
      ])} />
    </div>
  );
}
