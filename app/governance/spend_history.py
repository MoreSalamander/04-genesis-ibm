"""Trailing-12-month vendor spend baseline — Bob-built subsystem (session 2).

Deterministic, in-repo fixture: no network, no randomness, no database.
Shares are engineered so the flagship proposal (HelioCompute $2.8M) lands
a real VIOLATION against the 25% concentration cap.

Acceptance invariants (also tested in tests/test_governance_engine.py):
  (8_900_000 + 2_800_000) / (38_000_000 + 2_800_000) ≈ 0.287  > 0.25  → VIOLATION
  (1_300_000 + 2_800_000) / (38_000_000 + 2_800_000) ≈ 0.100  < 0.25  → COMPLIANT
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Fixed spend baseline (trailing 12 months, USD)
# ---------------------------------------------------------------------------
# Total engineered to ≈ $38 000 000.
_BASELINE: dict[str, float] = {
    "HelioCompute":      8_900_000,   # render compute — primary (engineered: will breach cap)
    "NimbusRender":      1_300_000,   # render compute — secondary (will stay COMPLIANT)
    "AzureStudio":       7_200_000,   # cloud infrastructure
    "OracleLicensing":   5_500_000,   # enterprise software licensing
    "PinnacleFacilities":3_800_000,   # studio facilities & power
    "FrameForge":        3_100_000,   # post-production services
    "SkylineMedia":      2_700_000,   # distribution & delivery
    "BroadcastBridge":   2_200_000,   # broadcast & streaming infra
    "CreativeForce":     1_800_000,   # marketing & campaign production
    "TalentStream":      1_500_000,   # staffing & contractor payroll
}

_TOTAL_BASELINE: float = sum(_BASELINE.values())   # 38_000_000


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def get_vendor_share(vendor: str, additional_spend_usd: float = 0.0) -> float | None:
    """Return the vendor's share of trailing-12-month studio spend *including*
    the proposed additional amount.

    Share-after formula:
        share = (existing_spend + additional_spend_usd) / (total_baseline + additional_spend_usd)

    Rules:
    - An unknown vendor is treated as having $0 existing spend (new entrant);
      its share is purely its own proposal against the enlarged total.
    - Returns ``None`` only if the baseline itself could not be loaded (never
      happens with the in-repo fixture, but callers must handle it).
    - An empty or blank vendor string: callers should handle as EXEMPT before
      calling this function, but for safety returns ``None``.
    """
    vendor = (vendor or "").strip()
    if not vendor:
        return None

    existing: float = _BASELINE.get(vendor, 0.0)
    total: float = _TOTAL_BASELINE + additional_spend_usd
    if total <= 0:
        return 0.0
    return (existing + additional_spend_usd) / total


def total_baseline_usd() -> float:
    """Return the total trailing-12-month baseline spend (for tests / observability)."""
    return _TOTAL_BASELINE


def vendor_exists(vendor: str) -> bool:
    """True if the vendor has a recorded spend history entry."""
    return vendor in _BASELINE
