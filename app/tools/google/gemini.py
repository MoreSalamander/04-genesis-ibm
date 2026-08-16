"""Gemini cognition layer (locked §2.7: interpretation, qualitative evaluation
with citations, dossier narrative, recommendation rationale, objective drafting —
while criterion scores, policy findings, verdicts and strengths are computed in
code).

LIVE mode calls Gemini at runtime via the official `google-genai` SDK (accepted
hackathon Google Cloud SDK — imported and actually called). MOCK mode is a
deterministic stand-in so the full loop runs from a clean clone with no keys.
"""
from __future__ import annotations

import json
import re
from typing import Any, Protocol

from app.config import Settings
from app import runtime_proof

ROLE_PROMPTS: dict[str, str] = {
    "criterion_evaluation": (
        "You are the Evaluation Agent of a film studio's Enterprise Decision Intelligence system. "
        "For the given criterion, assess the proposal's evidence QUALITATIVELY. The numeric score is "
        "computed by the system from the evidence values — do NOT produce or dispute numbers; your job "
        "is the reasoning around them. Return JSON: {\"rationale\": str (2-3 sentences grounded ONLY in "
        "the provided evidence items, referencing them by id), \"cited_evidence_ids\": [str], "
        "\"gaps\": [str] (evidence that SHOULD exist for this criterion but does not)}."
    ),
    "dossier_narrative": (
        "You are the Decision Executive of a film studio ('Convergence Studios'). Write the dossier "
        "summary for the Studio Head: what is proposed, what the computed scores say, what governance "
        "found (policy findings and verdict are rule-derived in code — report them faithfully, never "
        "re-litigate them). Return JSON: {\"summary\": str (3-5 sentences, cite finding clauses and "
        "score values verbatim)}."
    ),
    "recommendation": (
        "You are the Decision Executive. Produce the recommendation for the Studio Head. The strength "
        "number is computed by the system — do NOT produce one. Ground every claim in the scores, "
        "policy findings, and verdict given; a BLOCKED verdict means the recommendation must be to "
        "revise or reject, never to approve as-is. Return JSON: {\"action\": str (one imperative "
        "sentence), \"rationale\": str (3-5 sentences citing criteria and policy clauses), "
        "\"caveats\": [str]}."
    ),
    "objective_draft": (
        "You are the Action Liaison. The Studio Head has AUTHORIZED this decision. Draft the "
        "Authorized Software Objective that IBM Bob will execute (a concrete software change in the "
        "studio's tooling). Return JSON: {\"objective\": str (one sentence, imperative), "
        "\"business_purpose\": str, \"requirements\": [str, 3-6 items, each concretely testable], "
        "\"acceptance_criteria\": [str, 2-4 items], \"risk_class\": \"standard\"|\"elevated\"}."
    ),
}


class Cognition(Protocol):
    live: bool

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class GeminiCognition:
    """Real Gemini via google-genai (API key or Vertex AI, auto-detected from env)."""

    live = True

    def __init__(self, settings: Settings):
        from google import genai  # accepted hackathon SDK: google-genai

        self.settings = settings
        self._client = genai.Client()
        self._model = settings.gemini_model

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        from app.observability.tracing import span

        prompt = ROLE_PROMPTS[role] + "\n\nINPUT:\n" + json.dumps(payload, ensure_ascii=False, default=str)
        with span("gemini.generate", role=role, model=self._model) as sp:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"response_mime_type": "application/json", "temperature": 0.2},
            )
            usage = getattr(response, "usage_metadata", None)
            if sp is not None and usage is not None:
                sp.set_attribute("tokens.prompt", getattr(usage, "prompt_token_count", 0) or 0)
                sp.set_attribute("tokens.total", getattr(usage, "total_token_count", 0) or 0)
        # First-hand proof of Google Cloud usage: the call came back.
        runtime_proof.record("gemini", "LIVE",
                             f"{self._model} returned a response this session")
        text = response.text or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise


class MockCognition:
    """Deterministic cognition — the flagship render-farm capex decision."""

    live = False

    def generate_json(self, role: str, payload: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_{role}", None)
        if handler is None:
            raise ValueError(f"MockCognition has no handler for role '{role}'")
        return handler(payload)

    def _criterion_evaluation(self, payload: dict) -> dict:
        criterion = payload.get("criterion", "")
        items = payload.get("evidence", [])
        cited = [i["id"] for i in items][:3]
        texts = {
            "financial": "Payback and utilization evidence supports the spend at the proposed scale; "
                         "the amount sits at the top of the studio's historical capex band.",
            "operational": "Queue saturation and overflow-incident evidence shows the current farm is "
                           "the binding constraint on delivery.",
            "strategic": "Capacity underpins the slate's VFX-heavy titles; the expansion aligns with "
                         "the production roadmap.",
            "risk": "Single-vendor delivery and integration lead time are the main exposures in the "
                    "evidence.",
        }
        return {"rationale": texts.get(criterion, "Evidence reviewed."),
                "cited_evidence_ids": cited,
                "gaps": [] if criterion != "risk" else ["independent vendor delivery-history audit"]}

    def _dossier_narrative(self, payload: dict) -> dict:
        verdict = (payload.get("verdict") or {}).get("outcome", "PENDING")
        return {"summary": f"The proposal requests the stated capital expansion; computed criterion "
                           f"scores are attached with their bases. Governance verdict: {verdict}, "
                           f"derived from the policy findings on record. All numbers and compliance "
                           f"states are computed by the system, not asserted."}

    def _recommendation(self, payload: dict) -> dict:
        verdict = (payload.get("verdict") or {}).get("outcome", "")
        if verdict == "BLOCKED":
            return {"action": "Revise the proposal to resolve the policy violation before any approval.",
                    "rationale": "Governance is BLOCKED: at least one policy violation stands (see the "
                                 "cited clause). The computed scores support the underlying need, so "
                                 "revision — not rejection — is the recommended path.",
                    "caveats": ["Approval is impossible while a VIOLATION finding stands."]}
        return {"action": "Approve the expansion at the proposed amount with the revised vendor split.",
                "rationale": "Computed scores support the spend; governance is clear of violations. "
                             "Operational evidence makes capacity the binding constraint, and the "
                             "revised structure resolves the concentration exposure.",
                "caveats": ["Concentration remains near the cap — re-evaluate at the next capex."]}

    def _objective_draft(self, payload: dict) -> dict:
        return {"objective": "Implement the render-farm capacity expansion configuration in the studio "
                             "provisioning repo, gated by the authorized decision id.",
                "business_purpose": "Convert the authorized capex decision into deployable capacity.",
                "requirements": [
                    "Add the new worker-pool definition with the authorized node count",
                    "Split provisioning across the two approved vendors per the revised proposal",
                    "Wire pool metrics into the existing telemetry labels",
                    "Reference the authorizing decision id in the change manifest",
                ],
                "acceptance_criteria": [
                    "Provisioning config validates and dry-runs clean",
                    "Change manifest carries the decision id and vendor split",
                ],
                "risk_class": "standard"}


def get_cognition(settings: Settings) -> Cognition:
    if settings.gemini_live:
        return GeminiCognition(settings)
    return MockCognition()
