"""Flagship decision fixture (locked §2.10): the $2.8M render-farm capacity
expansion, vendor HelioCompute — deterministic evidence package with metric
values chosen so the computed scores support the spend while vendor
concentration sits above the policy cap (the caught VIOLATION → revision arc).

Usage:  .venv/bin/python -m seed.proposals          (POSTs to the local API)
        SEED_PRINT=1 .venv/bin/python -m seed.proposals   (print JSON only)
"""
from __future__ import annotations

import json
import os

from app.models.enterprise import DecisionProposal, EvidenceItem

FLAGSHIP = DecisionProposal(
    title="Render-farm capacity expansion — 2,400 GPU-node hours/day",
    description=(
        "Expand the studio render farm by 2,400 GPU-node hours/day ahead of the FY27 "
        "VFX-heavy slate. Single-vendor build-out with HelioCompute under the existing "
        "master services agreement; delivery in two tranches over 14 weeks."
    ),
    category="capex",
    amount_usd=2_800_000,
    vendor="HelioCompute",
    requested_by="studio-operations",
    evidence=[
        EvidenceItem(kind="financial", metric="payback_months", value=19,
                     statement="Chargeback model projects 19-month payback at current "
                               "render pricing.", source="finance/capex-model-fy27"),
        EvidenceItem(kind="financial", metric="capex_share_of_annual", value=0.061,
                     statement="Request equals 6.1% of the FY27 capital budget.",
                     source="finance/fy27-capital-plan"),
        EvidenceItem(kind="financial", metric="projected_utilization", value=0.86,
                     statement="Demand model projects 86% steady-state utilization of the "
                               "expanded pool.", source="ops/demand-model-q3"),
        EvidenceItem(kind="operational", metric="queue_saturation_pct", value=91,
                     statement="Render queue has run at 91% average saturation for the "
                               "trailing quarter.", source="ops/telemetry-quarterly"),
        EvidenceItem(kind="operational", metric="overflow_incidents_90d", value=9,
                     statement="Nine queue-overflow incidents in the last 90 days forced "
                               "overnight re-prioritization.", source="ops/incident-log"),
        EvidenceItem(kind="strategic", metric="slate_vfx_titles", value=5,
                     statement="Five FY27 titles are VFX-heavy and depend on in-house "
                               "render capacity.", source="production/slate-fy27"),
        EvidenceItem(kind="risk", metric="vendor_delivery_slip_days", value=12,
                     statement="HelioCompute's last two deliveries slipped 12 days on "
                               "average.", source="procurement/vendor-history"),
        EvidenceItem(kind="risk", metric="integration_lead_weeks", value=9,
                     statement="Farm integration and burn-in historically takes 9 weeks.",
                     source="ops/integration-history"),
    ],
)


def main() -> int:
    payload = {"proposal": json.loads(FLAGSHIP.model_dump_json())}
    if os.getenv("SEED_PRINT"):
        print(json.dumps(payload, indent=2))
        return 0
    import httpx

    api = os.getenv("GENESIS_API", "http://localhost:8030")
    response = httpx.post(f"{api}/api/decisions", json=payload, timeout=30)
    print(response.status_code, response.text)
    return 0 if response.status_code == 202 else 1


if __name__ == "__main__":
    raise SystemExit(main())
