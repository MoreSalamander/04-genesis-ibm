"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Decision,
  DecisionSummary,
  SystemStatus,
  getDecision,
  getEvents,
  getStatus,
  listDecisions,
  sendAuthorization,
  submitDecision,
} from "@/lib/api";
import { PolicyFindings } from "@/components/PolicyFindings";

const STAGES = ["SUBMITTED", "EVALUATING", "GOVERNANCE_REVIEW", "RECOMMENDED",
                "AWAITING_AUTHORIZATION", "AUTHORIZED", "ACTIONED", "CLOSED"];
const TERMINAL = new Set(["CLOSED", "REJECTED", "INCOMPLETE"]);

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
    try {
      const amendments = decision === "revise" && amendVendor.trim()
        ? { vendor: amendVendor.trim() } : {};
      await sendAuthorization(active.id, decision, note, amendments);
      setNote(""); setAmendVendor("");
      await refresh();
    } catch (err) {
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
              <div>Gemini {status.gemini_live ? <span className="live">LIVE</span> : "MOCK"}</div>
              <div>Confluent ledger {status.confluent_live ? <span className="live">LIVE</span> : <span className="stub">STUBBED</span>}</div>
              <div>policy engine: <span className={status.policy_engine.includes("pending") ? "stub" : "live"}>{status.policy_engine}</span></div>
            </>
          ) : (
            "backend offline — start uvicorn on :8030"
          )}
        </div>
      </header>

      <div className="intake">
        <span className="label">Bring a decision before the chamber</span>
        <button className="btn solid" onClick={submit} disabled={busy}>
          SUBMIT THE FLAGSHIP PROPOSAL — $2.8M RENDER-FARM EXPANSION
        </button>
        {error && <div className="error-note">{error}</div>}
      </div>

      {active && (
        <>
          <div className="stage-rail">
            {STAGES.map((stage, i) => (
              <div key={stage}
                   className={"stage" + (i < stageIndex ? " done" : "") + (i === stageIndex ? " current" : "")}>
                {i === STAGES.length - 1 && TERMINAL.has(active.status) ? active.status : stage.replace("_", " ")}
              </div>
            ))}
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
                      <div className="evidence-item" key={item.id}>
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

              <section className="section">
                <h2>Criterion scores <span className="tag">computed in code · rationale by Gemini</span></h2>
                {active.scores.map((score) => (
                  <div className="score-row" key={score.id}>
                    <div>
                      <div className="name">{score.criterion}</div>
                      <div className="value">{score.score.toFixed(3)}</div>
                      <div className="hint">w {score.weight}</div>
                    </div>
                    <div>
                      <div className="score-bar"><div className="fill" style={{ width: `${score.score * 100}%` }} /></div>
                      <div className="basis">{score.basis}</div>
                      {score.rationale && <div className="rationale">{score.rationale}</div>}
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
                <div className="error-note">
                  INCOMPLETE — {active.incomplete_reason ?? "substrate unavailable"}; nothing was fabricated.
                </div>
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

      <section className="section">
        <h2>Decision ledger <span className="tag">{ledger.length} on record</span></h2>
        {ledger.map((item) => (
          <div className="ledger-item" key={item.id} onClick={() => open(item.id)}>
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
    </div>
  );
}
