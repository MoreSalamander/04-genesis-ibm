"""Runtime configuration for Genesis OS — Enterprise Decision Intelligence."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    google_api_key: str = field(
        default_factory=lambda: (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    )
    use_vertex: bool = field(default_factory=lambda: _truthy(os.getenv("GOOGLE_GENAI_USE_VERTEXAI")))
    google_project: str = field(default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT", "").strip())
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-flash-latest").strip())
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("GENESIS_DATA_DIR", "./data")))
    force_mock: bool = field(default_factory=lambda: _truthy(os.getenv("GENESIS_MOCK")))
    site: str = field(default_factory=lambda: os.getenv("GENESIS_SITE", "local").strip())
    datahub_gms_url: str = field(
        default_factory=lambda: os.getenv("DATAHUB_GMS_URL", "http://localhost:8080").strip()
    )
    postgres_dsn: str = field(
        default_factory=lambda: os.getenv(
            "POSTGRES_DSN", "postgresql://genesis:genesis@localhost:5436/genesis_enterprise"
        ).strip()
    )
    nats_url: str = field(default_factory=lambda: os.getenv("NATS_URL", "nats://localhost:4226").strip())
    nats_subject: str = field(
        default_factory=lambda: os.getenv("NATS_SUBJECT", "genesis.enterprise.events").strip()
    )
    temporal_address: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_ADDRESS", "localhost:7236").strip()
    )
    temporal_task_queue: str = field(
        default_factory=lambda: os.getenv("TEMPORAL_TASK_QUEUE", "genesis-enterprise-decisions").strip()
    )
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6383/0").strip())
    minio_endpoint: str = field(default_factory=lambda: os.getenv("MINIO_ENDPOINT", "localhost:9020").strip())
    minio_access_key: str = field(default_factory=lambda: os.getenv("MINIO_ACCESS_KEY", "minioadmin").strip())
    minio_secret_key: str = field(default_factory=lambda: os.getenv("MINIO_SECRET_KEY", "minioadmin").strip())
    # Confluent Cloud decision-ledger stream (locked §2.4; degrades to NATS+JSONL, surfaced)
    confluent_bootstrap: str = field(
        default_factory=lambda: os.getenv("CONFLUENT_BOOTSTRAP", "").strip()
    )
    confluent_api_key: str = field(default_factory=lambda: os.getenv("CONFLUENT_API_KEY", "").strip())
    confluent_api_secret: str = field(
        default_factory=lambda: os.getenv("CONFLUENT_API_SECRET", "").strip()
    )
    confluent_ledger_topic: str = field(
        default_factory=lambda: os.getenv("CONFLUENT_LEDGER_TOPIC", "genesis.enterprise.ledger").strip()
    )
    # Policy engine (Bob-built subsystem): pack directory + active version
    policy_dir: Path = field(default_factory=lambda: Path(os.getenv("POLICY_DIR", "./policy")))
    policy_version: str = field(default_factory=lambda: os.getenv("POLICY_VERSION", "latest").strip())

    @property
    def gemini_live(self) -> bool:
        if self.force_mock:
            return False
        return bool(self.google_api_key) or (self.use_vertex and bool(self.google_project))

    @property
    def confluent_live(self) -> bool:
        return bool(self.confluent_bootstrap and self.confluent_api_key) and not self.force_mock

    def banner(self) -> str:
        return (
            "Genesis OS — Enterprise Decision Intelligence | "
            f"Gemini({self.gemini_model}): {'LIVE' if self.gemini_live else 'MOCK'} | "
            f"Confluent ledger: {'LIVE' if self.confluent_live else 'STUBBED (NATS+audit only)'}"
        )


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
