"""Confluent Cloud decision-ledger stream (locked §2.4 — included by Studio Head
decision 2026-08-13; the IBM track's "optional but strongly encouraged" Confluent).

Ledger-grade events (authorization.decided, decision.closed, action.delivered)
are produced to the `genesis.enterprise.ledger` topic as the enterprise
system-of-record feed. NATS keeps the internal-fabric role; this stream ADDS the
enterprise integration and degrades to NATS+JSONL with a surfaced warning when
unconfigured or unreachable — never silent, never fatal.
"""
from __future__ import annotations

import json

from app.config import Settings


class DecisionLedger:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._producer = None
        self._warned = False
        if settings.confluent_live:
            try:
                from confluent_kafka import Producer

                self._producer = Producer({
                    "bootstrap.servers": settings.confluent_bootstrap,
                    "security.protocol": "SASL_SSL",
                    "sasl.mechanisms": "PLAIN",
                    "sasl.username": settings.confluent_api_key,
                    "sasl.password": settings.confluent_api_secret,
                    "client.id": "genesis-enterprise-ledger",
                })
                print(f"[ledger] Confluent producer ready → {settings.confluent_ledger_topic}")
            except Exception as err:
                print(f"[ledger] Confluent unavailable ({err}) — DEGRADED: NATS+audit only")
                self._producer = None

    @property
    def available(self) -> bool:
        return self._producer is not None

    def append(self, record: dict) -> None:
        if self._producer is None:
            if not self._warned and not self.settings.force_mock:
                print("[ledger] Confluent not configured — ledger events stay on NATS+audit")
                self._warned = True
            return
        try:
            self._producer.produce(
                self.settings.confluent_ledger_topic,
                key=str(record.get("decision_id", "")).encode(),
                value=json.dumps(record, ensure_ascii=False, default=str).encode(),
            )
            self._producer.poll(0)
            self._producer.flush(2)
        except Exception as err:
            if not self._warned:
                print(f"[ledger] Confluent produce failed ({err}) — DEGRADED: NATS+audit only")
                self._warned = True
