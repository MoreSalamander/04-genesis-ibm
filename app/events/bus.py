"""Enterprise event contract (locked §2.11) — NATS internal fabric
(genesis.enterprise.events) + JSONL audit trail. Ledger-grade events are also
mirrored to the Confluent Cloud decision-ledger stream (app/events/ledger.py)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

EVENT_NAMES = {
    "decision.submitted",
    "decision.evaluated",
    "policy.finding",
    "governance.verdict",
    "recommendation.created",
    "authorization.decided",
    "action.objective_issued",
    "action.delivered",
    "decision.closed",
    "decision.incomplete",
    "knowledge.promoted",
}

# events that constitute the enterprise system-of-record (mirrored to Confluent)
LEDGER_EVENTS = {"authorization.decided", "decision.closed", "action.delivered"}


class EventBus:
    """NATS publish + local JSONL audit; ledger events additionally stream to
    Confluent. Failures degrade to audit-log-only and are surfaced once."""

    def __init__(self, data_dir: Path, nats_url: str = "",
                 subject: str = "genesis.enterprise.events", ledger=None):
        self.path = data_dir / "events.jsonl"
        self._nats_url = nats_url
        self._subject = subject
        self._nats_warned = False
        self._ledger = ledger

    def emit(self, name: str, **payload) -> None:
        if name not in EVENT_NAMES:
            raise ValueError(f"Unknown event '{name}' — extend the contract first")
        # payload first — the event name and timestamp can never be clobbered by kwargs
        record = {**payload, "event": name, "at": datetime.now(timezone.utc).isoformat()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._publish(record)
        if name in LEDGER_EVENTS and self._ledger is not None:
            self._ledger.append(record)

    def _publish(self, record: dict) -> None:
        if not self._nats_url:
            return
        try:
            import asyncio

            import nats

            async def _pub():
                nc = await nats.connect(self._nats_url, connect_timeout=2, max_reconnect_attempts=1)
                await nc.publish(self._subject, json.dumps(record, ensure_ascii=False, default=str).encode())
                await nc.flush(timeout=2)
                await nc.close()

            asyncio.run(_pub())
        except Exception as err:
            if not self._nats_warned:
                print(f"[events] NATS publish failed ({err}) — DEGRADED: audit log only")
                self._nats_warned = True

    def tail(self, limit: int = 100) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
