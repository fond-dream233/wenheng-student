"""Local ACPs/AIP Leader coordinating review and cross-stage Partners."""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from acps_sdk.aip import AipRpcClient, StructuredDataItem, TaskState

from competition.aip_settings import SETTINGS
from competition.discovery import resolve_partner_url


def _product_data(task) -> dict[str, Any]:
    for product in task.products or []:
        for item in product.dataItems or []:
            if isinstance(item, StructuredDataItem):
                return item.data
    return {}


async def _call_partner(
    name: str,
    url: str,
    payload: str,
    session_id: str,
    *,
    identity_binding_enabled: bool = SETTINGS.identity_binding_enabled,
    timeout_s: float = SETTINGS.task_timeout_s,
    poll_interval_s: float = SETTINGS.poll_interval_s,
) -> dict[str, Any]:
    client = AipRpcClient(
        partner_url=url,
        leader_id=SETTINGS.leader_id,
        identity_binding_enabled=identity_binding_enabled,
    )
    task_id = f"{name}-{uuid.uuid4()}"
    started = time.perf_counter()
    deadline = started + timeout_s
    try:
        task = await client.start_task(session_id=session_id, task_id=task_id, user_input=payload)
        while task.status.state in (TaskState.Accepted, TaskState.Working):
            if time.perf_counter() > deadline:
                raise TimeoutError(f"{name} Partner 等待完成超时")
            await asyncio.sleep(poll_interval_s)
            task = await client.get_task(task_id=task_id, session_id=session_id)
        if task.status.state != TaskState.AwaitingCompletion:
            details = [getattr(item, "text", "") for item in task.status.dataItems or []]
            raise RuntimeError(f"{name} Partner 状态为 {task.status.state}: {'; '.join(details)}")
        result = _product_data(task)
        completed = await client.complete_task(task_id=task_id, session_id=session_id)
        return {
            "partner": name,
            "taskId": task_id,
            "state": completed.status.state.value,
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "result": result,
        }
    finally:
        await client.close()


async def review_document(
    document: Path,
    format_url: str | None = None,
    logic_url: str | None = None,
) -> dict[str, Any]:
    """Send one document to both Partners concurrently and aggregate evidence."""
    path = document.resolve()
    if path.suffix.lower() != ".docx" or not path.is_file():
        raise ValueError("document 必须是存在的 .docx 文件")
    payload = json.dumps(
        {
            "filename": path.name,
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "fileBase64": base64.b64encode(path.read_bytes()).decode("ascii"),
        },
        ensure_ascii=False,
    )
    resolved_format_url = format_url or SETTINGS.format_url
    resolved_logic_url = logic_url or SETTINGS.logic_url
    if SETTINGS.discovery_base_url:
        resolved_format_url = await resolve_partner_url(
            SETTINGS.format_query, resolved_format_url
        )
        resolved_logic_url = await resolve_partner_url(
            SETTINGS.logic_query, resolved_logic_url
        )
    session_id = f"thesis-review-{uuid.uuid4()}"
    started_at = datetime.now(timezone.utc)
    results = await asyncio.gather(
        _call_partner("format", resolved_format_url, payload, session_id),
        _call_partner("logic", resolved_logic_url, payload, session_id),
    )
    finished_at = datetime.now(timezone.utc)
    return {
        "protocol": "ACPs/AIP 02.02",
        "sessionId": session_id,
        "documentName": path.name,
        "startedAt": started_at.isoformat(),
        "finishedAt": finished_at.isoformat(),
        "partners": results,
    }


def _encoded_document(stage: str, path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if resolved.suffix.lower() != ".docx" or not resolved.is_file():
        raise ValueError(f"{stage} 必须是存在的 .docx 文件")
    return {
        "stage": stage,
        "filename": resolved.name,
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "fileBase64": base64.b64encode(resolved.read_bytes()).decode("ascii"),
    }


async def compare_stages(
    documents: dict[str, Path],
    cross_stage_url: str | None = None,
) -> dict[str, Any]:
    """Send two or three thesis stages to the cross-stage Partner."""
    if not 2 <= len(documents) <= 3:
        raise ValueError("必须提供 2 到 3 个不同阶段文档")
    payload = json.dumps(
        {"documents": [_encoded_document(stage, path) for stage, path in documents.items()]},
        ensure_ascii=False,
    )
    resolved_cross_stage_url = cross_stage_url or SETTINGS.cross_stage_url
    if SETTINGS.discovery_base_url:
        resolved_cross_stage_url = await resolve_partner_url(
            SETTINGS.cross_stage_query, resolved_cross_stage_url
        )
    session_id = f"thesis-stage-review-{uuid.uuid4()}"
    started_at = datetime.now(timezone.utc)
    result = await _call_partner("cross_stage", resolved_cross_stage_url, payload, session_id)
    finished_at = datetime.now(timezone.utc)
    return {
        "protocol": "ACPs/AIP 02.02",
        "sessionId": session_id,
        "stages": list(documents),
        "startedAt": started_at.isoformat(),
        "finishedAt": finished_at.isoformat(),
        "partners": [result],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local multi-Partner thesis review")
    parser.add_argument("document", type=Path, nargs="?")
    parser.add_argument("--format-url", default=SETTINGS.format_url)
    parser.add_argument("--logic-url", default=SETTINGS.logic_url)
    parser.add_argument("--cross-stage-url", default=SETTINGS.cross_stage_url)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--midterm", type=Path)
    parser.add_argument("--final", dest="final_document", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    stage_documents = {
        stage: path
        for stage, path in (
            ("proposal", args.proposal),
            ("midterm", args.midterm),
            ("final", args.final_document),
        )
        if path is not None
    }
    if stage_documents:
        if args.document is not None:
            parser.error("单文档检查不能与阶段文档参数同时使用")
        if len(stage_documents) < 2:
            parser.error("跨阶段检查至少需要 --proposal/--midterm/--final 中的两个")
        result = asyncio.run(compare_stages(stage_documents, args.cross_stage_url))
    else:
        if args.document is None:
            parser.error("请提供单篇 document，或至少两个阶段文档参数")
        result = asyncio.run(review_document(args.document, args.format_url, args.logic_url))
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    else:
        print(rendered)


if __name__ == "__main__":
    main()
