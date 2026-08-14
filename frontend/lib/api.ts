// Typed client for the Enterprise Decision Intelligence API (via the runtime proxy).

export interface SystemStatus {
  system: string;
  banner: string;
  gemini_live: boolean;
  confluent_live: boolean;
  policy_engine: string;
  decisions: number;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  statement: string;
  metric: string;
  value: number | null;
  unit: string;
  source: string;
}

export interface CriterionScore {
  id: string;
  criterion: string;
  weight: number;
  score: number;
  basis: string;
  rationale: string;
  cited_evidence_ids: string[];
}

export interface PolicyFinding {
  id: string;
  policy_id: string;
  policy_version: string;
  clause: string;
  state: "COMPLIANT" | "VIOLATION" | "NEEDS_REVIEW" | "EXEMPT";
  observed: Record<string, unknown>;
  threshold: Record<string, unknown>;
  detail: string;
}

export interface GovernanceVerdict {
  outcome: "CLEAR" | "BLOCKED" | "ESCALATED";
  required_tier: string;
  basis: string;
  policy_version: string;
}

export interface Recommendation {
  action: string;
  rationale: string;
  strength: number;
  caveats: string[];
}

export interface AuthorizationRecord {
  decision: string;
  note: string;
  by: string;
  at: string;
}

export interface SoftwareActionObjective {
  id: string;
  objective: string;
  business_purpose: string;
  requirements: string[];
  acceptance_criteria: string[];
  risk_class: string;
}

export interface ActionRecord {
  delivered_by: string;
  summary: string;
  evidence_refs: string[];
  at: string;
}

export interface Decision {
  id: string;
  status: string;
  round: number;
  revision_guidance: string[];
  proposal: {
    title: string;
    description: string;
    category: string;
    amount_usd: number;
    vendor: string;
    requested_by: string;
    evidence: EvidenceItem[];
  };
  scores: CriterionScore[];
  policy_findings: PolicyFinding[];
  verdict: GovernanceVerdict | null;
  recommendation: Recommendation | null;
  authorizations: AuthorizationRecord[];
  objective: SoftwareActionObjective | null;
  action_record: ActionRecord | null;
  promotion: { datahub_urns: string[] } | null;
  escalated: boolean;
  incomplete_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface DecisionSummary {
  id: string;
  title: string;
  category: string;
  amount_usd: number;
  vendor: string;
  status: string;
  round: number;
  verdict: string | null;
  findings: Record<string, number>;
  strength: number | null;
  created_at: string;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json();
}

export const getStatus = () => req<SystemStatus>("/status");
export const listDecisions = () => req<DecisionSummary[]>("/decisions");
export const getDecision = (id: string) => req<Decision>(`/decisions/${id}`);
export const submitDecision = (proposal: unknown) =>
  req<{ id: string; execution: string }>("/decisions", {
    method: "POST",
    body: JSON.stringify({ proposal }),
  });
export const sendAuthorization = (id: string, decision: string, note: string) =>
  req<{ status: string }>(`/decisions/${id}/authorization`, {
    method: "POST",
    body: JSON.stringify({ decision, note }),
  });
export const getEvents = (limit = 60) => req<Record<string, unknown>[]>(`/events?limit=${limit}`);
