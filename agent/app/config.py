"""Agent configuration.

Values come from (lowest to highest precedence): defaults, `agent.ini` in the
data directory, environment variables, command-line flags. Intervals are
further overridden by the server policy returned on sign-in and heartbeat.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "WorkPulse" / "Agent"


@dataclass(frozen=True)
class AgentConfig:
    api_url: str = "http://localhost:8080/api"
    data_dir: Path = field(default_factory=default_data_dir)
    heartbeat_interval: float = 60.0
    sync_interval: float = 30.0
    idle_threshold: float = 300.0
    max_batch_size: int = 200
    request_timeout: float = 10.0
    #: Hard cap on locally queued events (oldest are dropped beyond this).
    max_queued_events: int = 50_000
    log_level: str = "INFO"

    @property
    def queue_path(self) -> Path:
        return self.data_dir / "queue.db"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"

    def with_policy(self, policy: dict[str, Any] | None) -> AgentConfig:
        """Apply the server-provided policy (intervals, thresholds)."""
        if not policy:
            return self
        return replace(
            self,
            heartbeat_interval=float(policy.get("heartbeat_interval_seconds", self.heartbeat_interval)),
            sync_interval=float(policy.get("sync_interval_seconds", self.sync_interval)),
            idle_threshold=float(policy.get("idle_threshold_seconds", self.idle_threshold)),
            max_batch_size=int(policy.get("max_batch_size", self.max_batch_size)),
        )


def load_config(api_url: str | None = None, data_dir: Path | None = None) -> AgentConfig:
    config = AgentConfig()
    directory = data_dir or Path(os.environ.get("WORKPULSE_DATA_DIR") or config.data_dir)
    config = replace(config, data_dir=directory)

    ini = directory / "agent.ini"
    if ini.exists():
        parser = configparser.ConfigParser()
        parser.read(ini, encoding="utf-8")
        section = parser["agent"] if parser.has_section("agent") else {}
        if "api_url" in section:
            config = replace(config, api_url=section["api_url"])
        if "log_level" in section:
            config = replace(config, log_level=section["log_level"])

    if env_url := os.environ.get("WORKPULSE_API_URL"):
        config = replace(config, api_url=env_url)
    if env_level := os.environ.get("WORKPULSE_LOG_LEVEL"):
        config = replace(config, log_level=env_level)
    if api_url:
        config = replace(config, api_url=api_url)
    return replace(config, api_url=config.api_url.rstrip("/"))
