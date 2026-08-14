"""Working memory (active decisions) and episodic memory (closed ones).

Write-through cache over the durable PostgreSQL document store with
newest-copy-wins merging — a Temporal worker may have advanced the durable
dossier past this process's cached object, and vice versa.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.enterprise import Decision


def _newest(a: Decision | None, b: Decision | None) -> Decision | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if a.updated_at >= b.updated_at else b


class WorkingMemory:
    """Write-through cache over the durable document store (PostgreSQL)."""

    def __init__(self, store):
        self._store = store
        self._items: dict[str, Decision] = {}
        self._lock = threading.Lock()

    def put(self, dec: Decision) -> None:
        with self._lock:
            self._items[dec.id] = dec
        try:
            self._store.upsert("decision", dec.id, dec.status.value, dec.escalated,
                               dec.model_dump(mode="json"))
        except Exception as err:
            print(f"[state] durable persist failed for {dec.id}: {err}")

    def get(self, dec_id: str) -> Decision | None:
        with self._lock:
            cached = self._items.get(dec_id)
        doc = self._store.fetch("decision", dec_id)
        stored = None
        if doc is not None:
            try:
                stored = Decision.model_validate(doc)
            except Exception:
                stored = None
        winner = _newest(cached, stored)
        if winner is stored and stored is not None:
            with self._lock:
                self._items[dec_id] = stored
        return winner

    def all(self) -> list[Decision]:
        merged: dict[str, Decision] = {}
        for doc in self._store.list("decision", limit=100):
            try:
                dec = Decision.model_validate(doc)
                merged[dec.id] = dec
            except Exception:
                continue
        with self._lock:
            for dec_id, cached in self._items.items():
                merged[dec_id] = _newest(cached, merged.get(dec_id)) or cached
        return sorted(merged.values(), key=lambda d: d.created_at, reverse=True)


class EpisodicMemory:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "episodic_decisions.jsonl"

    def record(self, dec: Decision) -> None:
        summary = {
            "decision_id": dec.id,
            "title": dec.proposal.title,
            "category": dec.proposal.category,
            "amount_usd": dec.proposal.amount_usd,
            "status": dec.status.value,
            "rounds": dec.round,
            "verdict": dec.verdict.outcome if dec.verdict else None,
            "findings": dec.finding_counts(),
            "strength": dec.recommendation.strength if dec.recommendation else None,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(summary, ensure_ascii=False) + "\n")

    def list(self, limit: int = 50) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
