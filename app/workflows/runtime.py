"""Process-wide runtime container for Enterprise Decision Intelligence
(mirrors the proven 01/02/03 runtime pattern — copied, never imported)."""
from __future__ import annotations

from app.config import Settings, settings as default_settings
from app.events.bus import EventBus
from app.events.ledger import DecisionLedger
from app.governance.engine import get_engine
from app.knowledge.datahub.emitter import DataHubKnowledge
from app.knowledge.objects.store import DossierObjectStore
from app.memory.durable import get_store
from app.memory.ephemeral import get_ephemeral
from app.memory.stores import EpisodicMemory, WorkingMemory
from app.tools.google.gemini import get_cognition


class EnterpriseRuntime:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or default_settings
        self.store = get_store(self.settings)
        self.working = WorkingMemory(self.store)
        self.episodic = EpisodicMemory(self.settings.data_dir)
        self.ephemeral = get_ephemeral(self.settings)
        self.ledger = DecisionLedger(self.settings)
        self.bus = EventBus(self.settings.data_dir, nats_url=self.settings.nats_url,
                            subject=self.settings.nats_subject, ledger=self.ledger)
        self.cognition = get_cognition(self.settings)
        self.policy_engine = get_engine(self.settings)
        self.datahub = DataHubKnowledge(self.settings)
        self.objects = DossierObjectStore(self.settings)

        from app.agents.executive.decision_executive import DecisionExecutive

        self.executive = DecisionExecutive(self)


_runtime: EnterpriseRuntime | None = None


def get_runtime() -> EnterpriseRuntime:
    global _runtime
    if _runtime is None:
        _runtime = EnterpriseRuntime()
    return _runtime
