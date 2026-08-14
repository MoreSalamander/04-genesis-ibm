// ── THE BOB PANEL SLOT ──────────────────────────────────────────────────────
// This component is scheduled to be BUILT BY IBM BOB (docs/bob-evidence/
// SESSION-PLAN.md, session 3) as part of the track's built-with-Bob evidence.
// Until that session lands, this deliberately minimal fallback renders the
// findings plainly and says so. Do not polish it here — Bob does.
import { PolicyFinding } from "@/lib/api";

export function PolicyFindings({ findings }: { findings: PolicyFinding[] }) {
  return (
    <div>
      <div className="bob-slot">
        ◈ PANEL PENDING — this dossier panel is built by IBM Bob (session 3); fallback rendering below
      </div>
      {findings.map((finding) => (
        <div className={`finding-row ${finding.state}`} key={finding.id}>
          <span className={`pchip ${finding.state}`}>{finding.state.replace("_", " ")}</span>
          <div>
            <div className="clause">
              <b>{finding.policy_id}</b> — {finding.clause}
            </div>
            {(Object.keys(finding.observed).length > 0 || Object.keys(finding.threshold).length > 0) && (
              <div className="values">
                observed {JSON.stringify(finding.observed)} · threshold {JSON.stringify(finding.threshold)}
                {" "}· pack {finding.policy_version}
              </div>
            )}
            {finding.detail && <div className="values">{finding.detail}</div>}
          </div>
        </div>
      ))}
      {findings.length === 0 && <div className="hint">Governance review pending…</div>}
    </div>
  );
}
