"""DataHub — durable knowledge/context/provenance substrate (locked §2.4).

Registers the policy packs as datasets and promotes closed decisions as
governed-knowledge entities with lineage back to the policy pack that judged
them. Outages degrade to log lines and never fail a decision.
"""
from __future__ import annotations

from app.config import Settings
from app import runtime_proof
from app.models.enterprise import Decision


class DataHubKnowledge:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._emitter = None
        if settings.datahub_gms_url and not settings.force_mock:
            try:
                from datahub.emitter.rest_emitter import DatahubRestEmitter

                self._emitter = DatahubRestEmitter(gms_server=settings.datahub_gms_url)
                # A constructed client proves configuration, not reachability —
                # so this stays IDLE until an emit actually lands.
                runtime_proof.declare(
                    "datahub", "IDLE",
                    f"configured at {settings.datahub_gms_url} — not contacted yet")
            except ImportError:
                print("[knowledge] acryl-datahub not importable — DataHub promotion disabled")
                runtime_proof.record(
                    "datahub", "DEGRADED",
                    "DATAHUB_GMS_URL is set but acryl-datahub is not installed")
        else:
            runtime_proof.declare(
                "datahub", "MOCK",
                "no DATAHUB_GMS_URL (or GENESIS_MOCK set) — local graph store only")

    @property
    def available(self) -> bool:
        return self._emitter is not None

    def _policy_urn(self, version: str) -> str:
        from datahub.emitter.mce_builder import make_dataset_urn

        return make_dataset_urn(platform="genesis-studio",
                                name=f"policy_pack.{version or 'pending'}", env="PROD")

    def register_policy_pack(self, version: str, policy_ids: list[str]) -> bool:
        if self._emitter is None:
            return False
        try:
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import DatasetPropertiesClass

            self._emitter.emit(MetadataChangeProposalWrapper(
                entityUrn=self._policy_urn(version),
                aspect=DatasetPropertiesClass(
                    name=f"Studio policy pack {version}",
                    description="Versioned governance policy pack (YAML in-repo; "
                                "engine built with IBM Bob).",
                    customProperties={"system": "genesis-enterprise-decision-intelligence",
                                      "policies": ", ".join(policy_ids)[:900]},
                ),
            ))
            return True
        except Exception as err:
            print(f"[knowledge] DataHub policy-pack registration failed: {err}")
            return False

    def promote(self, dec: Decision) -> list[str]:
        """Closed decisions become governed-knowledge entities with policy lineage."""
        if self._emitter is None:
            return []
        try:
            from datahub.emitter.mce_builder import make_dataset_urn
            from datahub.emitter.mcp import MetadataChangeProposalWrapper
            from datahub.metadata.schema_classes import (
                DatasetLineageTypeClass,
                DatasetPropertiesClass,
                UpstreamClass,
                UpstreamLineageClass,
            )

            urn = make_dataset_urn(platform="genesis-studio",
                                   name=f"enterprise_decision.{dec.id}", env="PROD")
            verdict = dec.verdict.outcome if dec.verdict else "NONE"
            self._emitter.emit(MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=DatasetPropertiesClass(
                    name=f"[{dec.status.value}] {dec.proposal.title[:110]}",
                    description=(f"Enterprise decision {dec.id}: {dec.proposal.description[:300]} "
                                 f"Verdict {verdict}; findings {dec.finding_counts()}."),
                    customProperties={
                        "status": dec.status.value,
                        "category": dec.proposal.category,
                        "amount_usd": str(dec.proposal.amount_usd),
                        "verdict": verdict,
                        "strength": str(dec.recommendation.strength if dec.recommendation else ""),
                        "authorizations": " | ".join(
                            f"{a.decision}({a.note[:60]})" for a in dec.authorizations)[:900],
                        "action_evidence": " | ".join(
                            dec.action_record.evidence_refs if dec.action_record else [])[:900],
                    },
                ),
            ))
            policy_version = dec.verdict.policy_version if dec.verdict else ""
            self._emitter.emit(MetadataChangeProposalWrapper(
                entityUrn=urn,
                aspect=UpstreamLineageClass(upstreams=[
                    UpstreamClass(dataset=self._policy_urn(policy_version),
                                  type=DatasetLineageTypeClass.TRANSFORMED)
                ]),
            ))
            runtime_proof.record("datahub", "LIVE",
                                 f"decision lineage emitted to {self.settings.datahub_gms_url}")
            return [urn]
        except Exception as err:
            print(f"[knowledge] DataHub promotion failed: {err}")
            runtime_proof.record("datahub", "DEGRADED", f"promotion failed ({err})")
            return []
