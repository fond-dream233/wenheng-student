"""Runtime wiring for the thesis-review AIP/ACPs services.

All values come from environment variables. The defaults keep the existing
one-command local demo working; production deployments override them with
platform-issued endpoints and enable identity binding.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AipSettings:
    """Environment-driven settings shared by Leader and deployment scripts."""

    leader_id: str = os.getenv("AIP_LEADER_ID", "local-thesis-review-leader")
    identity_binding_enabled: bool = _env_bool("AIP_IDENTITY_BINDING_ENABLED", False)

    discovery_base_url: str = os.getenv("AIP_DISCOVERY_BASE_URL", "").strip().rstrip("/")
    discovery_timeout_s: float = _env_float("AIP_DISCOVERY_TIMEOUT_S", 10.0)
    discovery_limit: int = _env_int("AIP_DISCOVERY_LIMIT", 5)

    format_url: str = os.getenv("AIP_FORMAT_URL", "http://127.0.0.1:9021/rpc").rstrip("/")
    logic_url: str = os.getenv("AIP_LOGIC_URL", "http://127.0.0.1:9022/rpc").rstrip("/")
    cross_stage_url: str = os.getenv(
        "AIP_CROSS_STAGE_URL", "http://127.0.0.1:9023/rpc"
    ).rstrip("/")

    format_query: str = os.getenv("AIP_FORMAT_QUERY", "论文格式检查智能体")
    logic_query: str = os.getenv("AIP_LOGIC_QUERY", "论文逻辑审查智能体")
    cross_stage_query: str = os.getenv("AIP_CROSS_STAGE_QUERY", "论文跨阶段对比智能体")

    task_timeout_s: float = _env_float("AIP_TASK_TIMEOUT_S", 120.0)
    poll_interval_s: float = _env_float("AIP_POLL_INTERVAL_S", 0.1)


SETTINGS = AipSettings()
