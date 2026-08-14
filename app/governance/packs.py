"""Policy pack loader — Bob-built subsystem (locked §2.5a, session 1).

Loads versioned YAML policy packs from `policy/` and evaluates a
`DecisionProposal` against every applicable rule, returning a list of
`PolicyFinding` objects that `engine.verdict_from()` turns into a
`GovernanceVerdict`.

Pure, deterministic, no network, no LLM calls.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from app.models.enterprise import DecisionProposal, PolicyFinding, PolicyState


# ---------------------------------------------------------------------------
# Spend-baseline stub (replaced in Session 2 by spend_history.py)
# ---------------------------------------------------------------------------

def get_vendor_share(vendor: str) -> float | None:  # noqa: ARG001
    """Return the vendor's trailing-12-month share of studio spend, or None
    when no baseline is available.  Session 1: always None → fail-closed."""
    return None


# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------

_VERSION_RE = re.compile(r"-v(\d+(?:\.\d+)*)\.yaml$", re.IGNORECASE)


def _pack_files(policy_dir: Path) -> dict[str, Path]:
    """Return {version_str: path} for all *-v*.yaml files in policy_dir."""
    found: dict[str, Path] = {}
    for p in policy_dir.glob("*-v*.yaml"):
        m = _VERSION_RE.search(p.name)
        if m:
            found[m.group(1)] = p
    return found


def _semver_key(v: str) -> tuple[int, ...]:
    """Convert '1', '1.2', '1.2.3' → tuple for numeric comparison."""
    return tuple(int(x) for x in v.split("."))


def _resolve_version(policy_dir: Path, requested: str) -> tuple[str, Path] | tuple[None, None]:
    """Return (resolved_version, pack_path), or (None, None) when no pack matches.

    Never raises — callers treat (None, None) as the degraded/missing state.
    """
    try:
        packs = _pack_files(policy_dir)
    except OSError:
        return None, None
    if not packs:
        return None, None
    if requested == "latest":
        version = max(packs, key=_semver_key)
        return version, packs[version]
    if requested in packs:
        return requested, packs[requested]
    # Fallback: try matching by YAML internal version field
    for ver, path in packs.items():
        try:
            raw = yaml.safe_load(path.read_text())
            if str(raw.get("version", "")) == requested:
                return ver, path
        except OSError:
            continue
    return None, None


# ---------------------------------------------------------------------------
# Rule evaluators
# ---------------------------------------------------------------------------

def _applies(policy: dict[str, Any], proposal: DecisionProposal) -> bool:
    applies_to = policy.get("applies_to", "*")
    if applies_to == "*":
        return True
    if isinstance(applies_to, str):
        return proposal.category == applies_to
    return proposal.category in applies_to


def _state_for_amount(amount: float, rule: dict[str, Any]) -> tuple[PolicyState, float]:
    """Return (state, threshold) for the given amount against an amount_max rule.

    Thresholds list is ordered: the first entry whose `max` is ≥ amount and whose
    `above` state applies when amount > previous_max defines the bracket.

    Simpler mental model (two-bracket case as in the pack):
      amount ≤ first_max  → COMPLIANT
      first_max < amount ≤ second_max → NEEDS_REVIEW
      amount > second_max → VIOLATION
    """
    thresholds: list[dict[str, Any]] = rule.get("thresholds", [])
    # Sort ascending by max so we test lowest threshold first
    sorted_t = sorted(thresholds, key=lambda t: t["max"])
    prev_max = 0.0
    for t in sorted_t:
        cap = float(t["max"])
        if prev_max < amount <= cap:
            state_str: str = t["above"]
            return PolicyState(state_str), cap
        prev_max = cap
    # above all thresholds → VIOLATION (should be caught by sentinel bracket in YAML)
    return PolicyState.VIOLATION, prev_max


def _make_finding(
    policy: dict[str, Any],
    pack_version: str,
    state: PolicyState,
    observed: dict[str, Any],
    threshold: dict[str, Any],
    detail: str = "",
) -> PolicyFinding:
    return PolicyFinding(
        policy_id=policy["id"],
        policy_version=pack_version,
        clause=policy["clause"],
        state=state,
        observed=observed,
        threshold=threshold,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# PackPolicyEngine
# ---------------------------------------------------------------------------

_INTEGRITY_POLICY: dict[str, Any] = {
    "id": "pack-integrity",
    "clause": (
        "Policy pack could not be loaded (missing directory or no matching pack file). "
        "All proposals require human review until the pack is restored."
    ),
}


class PackPolicyEngine:
    """YAML-driven policy engine.  Satisfies the PolicyEngine protocol."""

    def __init__(self, policy_dir: str | Path, version: str = "latest") -> None:
        self._policy_dir = Path(policy_dir)
        resolved_ver, pack_path = _resolve_version(self._policy_dir, version)
        if resolved_ver is None or pack_path is None:
            # Degraded state: missing dir or no matching packs — never raise
            self._version = "missing"
            self._policies: list[dict[str, Any]] = []
            self._degraded = True
        else:
            self._version = resolved_ver
            raw = yaml.safe_load(pack_path.read_text())
            self._policies = raw.get("policies", [])
            self._degraded = False

    @property
    def version(self) -> str:
        return self._version

    def evaluate(self, proposal: DecisionProposal) -> list[PolicyFinding]:
        if self._degraded:
            return [
                PolicyFinding(
                    policy_id="pack-integrity",
                    policy_version=self._version,
                    clause=_INTEGRITY_POLICY["clause"],
                    state=PolicyState.NEEDS_REVIEW,
                    observed={"policy_dir": str(self._policy_dir)},
                    threshold={},
                    detail="Pack missing — fail-closed; restore policy directory to clear",
                )
            ]
        findings: list[PolicyFinding] = []
        for policy in self._policies:
            if not _applies(policy, proposal):
                continue
            rule: dict[str, Any] = policy.get("rule", {})
            rule_type: str = rule.get("type", "")
            finding = self._dispatch(policy, rule, rule_type, proposal)
            if finding is not None:
                findings.append(finding)
        return findings

    def _dispatch(
        self,
        policy: dict[str, Any],
        rule: dict[str, Any],
        rule_type: str,
        proposal: DecisionProposal,
    ) -> PolicyFinding | None:
        if rule_type == "amount_max":
            return self._eval_amount_max(policy, rule, proposal)
        if rule_type == "vendor_concentration":
            return self._eval_vendor_concentration(policy, rule, proposal)
        if rule_type == "risk_class":
            return self._eval_risk_class(policy, rule, proposal)
        # Unknown rule type — fail-closed
        return _make_finding(
            policy, self._version,
            PolicyState.NEEDS_REVIEW,
            observed={"rule_type": rule_type},
            threshold={},
            detail=f"Unknown rule type {rule_type!r} — fail-closed",
        )

    # ------------------------------------------------------------------
    # Individual rule evaluators
    # ------------------------------------------------------------------

    def _eval_amount_max(
        self,
        policy: dict[str, Any],
        rule: dict[str, Any],
        proposal: DecisionProposal,
    ) -> PolicyFinding:
        amount = proposal.amount_usd
        state, cap = _state_for_amount(amount, rule)
        if state in (PolicyState.VIOLATION, PolicyState.NEEDS_REVIEW):
            pass  # state already correct
        elif amount <= 0:
            state = PolicyState.COMPLIANT
        # Build observed/threshold dicts
        observed = {"amount_usd": amount}
        threshold = {"max_usd": cap, "state_above": state.value}
        return _make_finding(
            policy, self._version, state,
            observed=observed,
            threshold=threshold,
            detail=f"amount_usd={amount:,.0f} evaluated against cap={cap:,.0f}",
        )

    def _eval_vendor_concentration(
        self,
        policy: dict[str, Any],
        rule: dict[str, Any],
        proposal: DecisionProposal,
    ) -> PolicyFinding:
        vendor = proposal.vendor or ""
        max_share: float = float(rule.get("max_share", 0.25))
        share = get_vendor_share(vendor)
        if share is None:
            return _make_finding(
                policy, self._version,
                PolicyState.NEEDS_REVIEW,
                observed={"vendor": vendor, "share": None},
                threshold={"max_share": max_share},
                detail="No spend baseline available — fail-closed pending Session 2",
            )
        state = PolicyState.VIOLATION if share > max_share else PolicyState.COMPLIANT
        return _make_finding(
            policy, self._version, state,
            observed={"vendor": vendor, "share": share},
            threshold={"max_share": max_share},
            detail=f"vendor={vendor!r} share={share:.2%} cap={max_share:.2%}",
        )

    def _eval_risk_class(
        self,
        policy: dict[str, Any],
        rule: dict[str, Any],
        proposal: DecisionProposal,
    ) -> PolicyFinding:
        # Risk class may be present in evidence items or defaulted to "standard"
        risk_class = self._extract_risk_class(proposal)
        classes: dict[str, str] = rule.get("classes", {})
        state_str = classes.get(risk_class, classes.get("standard", "NEEDS_REVIEW"))
        state = PolicyState(state_str)
        return _make_finding(
            policy, self._version, state,
            observed={"risk_class": risk_class},
            threshold={"classes": classes},
            detail=f"risk_class={risk_class!r} → {state.value}",
        )

    @staticmethod
    def _extract_risk_class(proposal: DecisionProposal) -> str:
        """Read risk_class from evidence metrics; default to 'standard'."""
        for item in proposal.evidence:
            if item.metric == "risk_class" and item.statement:
                return item.statement.strip().lower()
        return "standard"
