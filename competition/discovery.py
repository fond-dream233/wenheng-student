"""Minimal ADP discovery helper for resolving Partner RPC endpoints.

This mirrors the official ``demo-leader`` discovery client. When no discovery
server is configured the Leader keeps using its explicit local or injected URL.
"""
from __future__ import annotations

from typing import Any

import httpx
from acps_sdk.adp import (
    ADPError,
    DiscoveryRequest,
    DiscoveryResponse,
    validate_discovery_request,
)

from competition.aip_settings import SETTINGS


class DiscoveryError(RuntimeError):
    """Raised when a discovery request cannot return a usable Partner."""


def _extract_endpoint(acs_data: dict[str, Any]) -> str | None:
    endpoints = acs_data.get("endPoints") or []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        url = str(endpoint.get("url") or "").strip()
        if url.startswith("https://"):
            return url
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        url = str(endpoint.get("url") or "").strip()
        transport = str(endpoint.get("transport") or "").upper()
        if url and transport in {"HTTP", "JSONRPC"}:
            return url
    return None


async def discover_partners(
    query: str,
    *,
    limit: int | None = None,
    base_url: str | None = None,
    timeout_s: float | None = None,
) -> list[dict[str, Any]]:
    """Query the discovery server and return endpoint candidates."""
    server_url = (base_url or SETTINGS.discovery_base_url).rstrip("/")
    if not server_url:
        raise DiscoveryError("未配置 AIP_DISCOVERY_BASE_URL")

    request = DiscoveryRequest(
        type="explicit",
        query=query,
        limit=limit or SETTINGS.discovery_limit,
    )
    try:
        validate_discovery_request(request)
    except ADPError as exc:
        raise DiscoveryError(f"发现请求参数校验失败: {exc.message}") from exc

    url = f"{server_url}/discover"
    try:
        async with httpx.AsyncClient(timeout=timeout_s or SETTINGS.discovery_timeout_s) as client:
            response = await client.post(url, json=request.to_dict())
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPError as exc:
        raise DiscoveryError(f"发现服务请求失败: {exc}") from exc

    parsed = DiscoveryResponse.from_dict(payload)
    if parsed.is_error():
        adp_error = parsed.get_adp_error()
        message = adp_error.message if adp_error else str(parsed.error)
        raise DiscoveryError(f"发现服务返回错误: {message}")
    if parsed.result is None:
        raise DiscoveryError("发现服务未返回结果")

    candidates: list[dict[str, Any]] = []
    for aic, acs_data, _skill, _group in parsed.result.iter_agent_skills():
        endpoint = _extract_endpoint(acs_data or {})
        if not endpoint:
            continue
        candidates.append(
            {
                "aic": aic,
                "name": str(acs_data.get("name") or ""),
                "description": str(acs_data.get("description") or ""),
                "url": endpoint,
            }
        )
    return candidates


async def resolve_partner_url(query: str, fallback_url: str) -> str:
    """Resolve one Partner URL, falling back to an explicit URL without discovery."""
    if not SETTINGS.discovery_base_url:
        return fallback_url
    candidates = await discover_partners(query)
    if not candidates:
        raise DiscoveryError(f"发现服务未找到 Partner: {query}")
    return candidates[0]["url"]
