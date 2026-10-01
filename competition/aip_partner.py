"""ACPs/AIP Partner adapters for the deterministic thesis review engines.

Run one role per process, for example::

    python -m competition.aip_partner --role format --port 9021
    python -m competition.aip_partner --role logic --port 9022
    python -m competition.aip_partner --role cross-stage --port 9023

Local development deliberately disables certificate identity binding. A deployed
competition instance must enable mTLS and use the AIC issued by the platform.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from acps_sdk.aip import (
    FileDataItem,
    Product,
    StructuredDataItem,
    TaskCommand,
    TaskResult,
    TaskState,
    TextDataItem,
)
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers,
    DefaultHandlers,
    TaskManager,
    add_aip_rpc_router,
)
from fastapi import FastAPI

from config.settings import Config
from competition.stage_comparison import STAGE_ORDER, compare_stage_documents
from tools.docx_parser import parse_docx
from tools.format_expert import FormatExpert
from tools.logic_expert import LogicExpert
from tools.rules_schema import RULES

PartnerRole = Literal["format", "logic", "cross_stage"]
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_rules() -> dict[str, dict[str, Any]]:
    """Return the configured baseline without depending on a mutable database."""
    rules = {
        rule.key: {
            "category": rule.category,
            "title": rule.title,
            "enabled": bool(rule.preset),
            "expected": rule.preset,
            "weight": float(rule.default_weight),
        }
        for rule in RULES
    }
    if Config.COMPETITION_MODE and "header_text" in rules:
        rules["header_text"].update(enabled=False, expected="")
    return rules


def _payload_from(command: TaskCommand) -> dict[str, Any]:
    """Read a JSON payload from AIP structured, text, or file data items."""
    payload: dict[str, Any] = {}
    for item in command.dataItems or []:
        if isinstance(item, StructuredDataItem):
            payload.update(item.data)
        elif isinstance(item, FileDataItem) and item.bytes:
            payload.setdefault("filename", item.name or "paper.docx")
            payload.setdefault("fileBase64", item.bytes)
        elif isinstance(item, TextDataItem) and item.text.strip():
            try:
                decoded = json.loads(item.text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                payload.update(decoded)
    return payload


def _decode_docx(payload: dict[str, Any]) -> tuple[Path | None, bool]:
    """Resolve a DOCX input and report whether the returned path is temporary."""
    encoded = payload.get("fileBase64")
    if isinstance(encoded, str) and encoded:
        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("fileBase64 不是合法 Base64") from exc
        max_bytes = Config.MAX_UPLOAD_MB * 1024 * 1024
        if not content or len(content) > max_bytes:
            raise ValueError(f"DOCX 大小必须在 1 字节到 {Config.MAX_UPLOAD_MB} MB 之间")
        if not content.startswith(b"PK"):
            raise ValueError("上传内容不是有效的 DOCX/ZIP 文件")
        with tempfile.NamedTemporaryFile(prefix="aip-paper-", suffix=".docx", delete=False) as stream:
            stream.write(content)
            return Path(stream.name), True

    local_path = payload.get("documentPath")
    if isinstance(local_path, str) and local_path:
        if not _env_bool("AIP_ALLOW_LOCAL_PATHS", False):
            raise ValueError("本地路径输入已禁用，请使用 fileBase64")
        candidate = Path(local_path).expanduser().resolve()
        allowed_root = Path(os.getenv("AIP_INPUT_DIR", str(Config.UPLOAD_DIR))).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError as exc:
            raise ValueError("documentPath 必须位于 AIP_INPUT_DIR 内") from exc
        if candidate.suffix.lower() != ".docx" or not candidate.is_file():
            raise ValueError("documentPath 必须指向存在的 .docx 文件")
        return candidate, False
    return None, False


def _decode_stage_documents(payload: dict[str, Any]) -> tuple[list[tuple[str, Path, str]], list[Path]]:
    """Decode two or three uniquely labelled stage documents."""
    supplied = payload.get("documents")
    if not isinstance(supplied, list) or not 2 <= len(supplied) <= 3:
        raise ValueError("documents 必须包含 2 到 3 个阶段文档")
    documents: list[tuple[str, Path, str]] = []
    temporary_paths: list[Path] = []
    seen: set[str] = set()
    try:
        for item in supplied:
            if not isinstance(item, dict):
                raise ValueError("每个阶段文档必须是 JSON 对象")
            stage = item.get("stage")
            if stage not in STAGE_ORDER:
                raise ValueError("stage 仅支持 proposal、midterm、final")
            if stage in seen:
                raise ValueError(f"阶段 {stage} 重复")
            path, temporary = _decode_docx(item)
            if path is None:
                raise ValueError(f"阶段 {stage} 缺少 fileBase64")
            seen.add(stage)
            documents.append((stage, path, str(item.get("filename") or f"{stage}.docx")))
            if temporary:
                temporary_paths.append(path)
    except Exception:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        raise
    return documents, temporary_paths


def _bind_sender(task: TaskResult, aic: str) -> TaskResult:
    task.senderId = aic
    return task


def _analyse(role: PartnerRole, path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    doc = parse_docx(path)
    if role == "format":
        supplied = payload.get("rules")
        rules = supplied if isinstance(supplied, dict) else _default_rules()
        report = FormatExpert(rules).check(doc)
        return {"agent": "format", "report": asdict(report), "stats": dict(doc.stats)}
    if role == "logic":
        report = LogicExpert().analyze(doc)
        return {"agent": "logic", "report": asdict(report), "stats": dict(doc.stats)}
    raise ValueError(f"角色 {role} 需要多阶段输入")


def build_handlers(role: PartnerRole, aic: str) -> CommandHandlers:
    """Build the AIP state-machine handlers for one review role."""

    async def on_start(command: TaskCommand, task: TaskResult | None) -> TaskResult:
        if task is not None:
            return _bind_sender(task, aic)
        payload = _payload_from(command)
        temporary_paths: list[Path] = []
        try:
            if role == "cross_stage":
                if "documents" not in payload:
                    path = None
                    stage_documents = []
                else:
                    stage_documents, temporary_paths = _decode_stage_documents(payload)
                    path = stage_documents[0][1]
            else:
                path, temporary = _decode_docx(payload)
                stage_documents = []
                if temporary and path is not None:
                    temporary_paths.append(path)
        except ValueError as exc:
            failed = TaskManager.create_task(
                command,
                initial_state=TaskState.Failed,
                data_items=[TextDataItem(text=f"输入校验失败：{exc}")],
            )
            return _bind_sender(failed, aic)
        if path is None:
            prompt = (
                "请提供 documents，其中包含 2 到 3 个 proposal/midterm/final 阶段 DOCX。"
                if role == "cross_stage" else "请提供 DOCX 的 fileBase64。"
            )
            created = TaskManager.create_task(
                command,
                initial_state=TaskState.AwaitingInput,
                data_items=[TextDataItem(text=prompt)],
            )
            return _bind_sender(created, aic)

        created = TaskManager.create_task(command, initial_state=TaskState.Working)
        _bind_sender(created, aic)
        try:
            result = (
                compare_stage_documents(stage_documents)
                if role == "cross_stage" else _analyse(role, path, payload)
            )
            TaskManager.set_products(
                created.taskId,
                [
                    Product(
                        id=f"{role}-report-{created.taskId}",
                        name=f"{role}-review-report",
                        description="结构化跨阶段对比结果" if role == "cross_stage" else "结构化论文检查结果",
                        dataItems=[StructuredDataItem(data=result)],
                    )
                ],
            )
            updated = TaskManager.update_task_status(created.taskId, TaskState.AwaitingCompletion)
            return _bind_sender(updated, aic)
        except Exception as exc:  # protocol boundary: return a failed task, not a 500 page
            failed = TaskManager.update_task_status(
                created.taskId,
                TaskState.Failed,
                [TextDataItem(text=f"论文检查失败：{type(exc).__name__}: {exc}")],
            )
            return _bind_sender(failed, aic)
        finally:
            for temporary_path in temporary_paths:
                temporary_path.unlink(missing_ok=True)

    async def on_continue(command: TaskCommand, task: TaskResult) -> TaskResult:
        if task.status.state != TaskState.AwaitingInput:
            return _bind_sender(await DefaultHandlers.continue_(command, task), aic)
        TaskManager._tasks.pop(task.taskId, None)
        return await on_start(command, None)

    async def on_get(command: TaskCommand, task: TaskResult) -> TaskResult:
        return _bind_sender(await DefaultHandlers.get(command, task), aic)

    async def on_cancel(command: TaskCommand, task: TaskResult) -> TaskResult:
        return _bind_sender(await DefaultHandlers.cancel(command, task), aic)

    async def on_complete(command: TaskCommand, task: TaskResult) -> TaskResult:
        return _bind_sender(await DefaultHandlers.complete(command, task), aic)

    return CommandHandlers(
        on_start=on_start,
        on_get=on_get,
        on_continue=on_continue,
        on_cancel=on_cancel,
        on_complete=on_complete,
    )


def create_partner_app(
    role: PartnerRole,
    *,
    aic: str | None = None,
    identity_binding_enabled: bool | None = None,
) -> FastAPI:
    """Create one Partner application; production enables identity binding."""
    local_aic = aic or os.getenv("AIP_PARTNER_AIC", f"local-{role}-partner")
    if identity_binding_enabled is None:
        identity_binding_enabled = _env_bool("AIP_IDENTITY_BINDING_ENABLED", False)
    app = FastAPI(title=f"Thesis Review {role.title()} AIP Partner", version="0.1.0")
    add_aip_rpc_router(
        app,
        "/rpc",
        build_handlers(role, local_aic),
        local_aic=local_aic,
        identity_binding_enabled=identity_binding_enabled,
    )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "role": role,
            "aic": local_aic,
            "identityBinding": identity_binding_enabled,
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a thesis-review AIP Partner")
    parser.add_argument("--role", choices=("format", "logic", "cross-stage"), required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    import uvicorn

    role = args.role.replace("-", "_")
    uvicorn.run(create_partner_app(role), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
