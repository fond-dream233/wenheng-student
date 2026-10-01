"""Deterministic, explainable comparison across thesis development stages."""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from tools.docx_parser import DocInfo, Section, parse_docx
from tools.knowledge_base import cite_for

STAGE_ORDER = {"proposal": 0, "midterm": 1, "final": 2}
STAGE_LABELS = {"proposal": "开题", "midterm": "中期", "final": "终稿"}
_OBJECTIVE_RE = re.compile(r"研究(目标|目的|内容)|主要内容|课题目标|预期目标")
_METHOD_RE = re.compile(r"研究方法|技术路线|实施方案|实验方案|研究设计")
_NUMBERING_RE = re.compile(r"^\s*(第?[一二三四五六七八九十百0-9]+[章节篇]?|[0-9]+(?:\.[0-9]+)*)[、.．\s]*")


def _tokens(text: str, *, limit: int = 120_000) -> Counter[str]:
    """Return interpretable Chinese bigram and Latin-word frequencies."""
    compact = re.sub(r"\s+", "", text.lower())[:limit]
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", compact))
    result = Counter(chinese[index:index + 2] for index in range(max(0, len(chinese) - 1)))
    result.update(re.findall(r"[a-z][a-z0-9_-]{1,}", compact))
    return result


def _cosine(left: Counter[str], right: Counter[str]) -> float | None:
    if not left or not right:
        return None
    shared = left.keys() & right.keys()
    numerator = sum(left[key] * right[key] for key in shared)
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return round(numerator / denominator, 4) if denominator else None


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float | None:
    left_set = {item.strip().lower() for item in left if item.strip()}
    right_set = {item.strip().lower() for item in right if item.strip()}
    if not left_set or not right_set:
        return None
    return round(len(left_set & right_set) / len(left_set | right_set), 4)


def _section_text(sections: list[Section], pattern: re.Pattern[str]) -> str:
    return "\n".join(section.text for section in sections if pattern.search(section.title))


def _heading_text(doc: DocInfo) -> str:
    normalized = [_NUMBERING_RE.sub("", section.title).strip() for section in doc.sections]
    return "\n".join(title for title in normalized if title)


def _round_metric(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _weighted_drift(metrics: dict[str, float | None]) -> float:
    weights = {
        "topicSimilarity": 0.45,
        "objectiveSimilarity": 0.25,
        "outlineSimilarity": 0.20,
        "keywordRetention": 0.10,
    }
    available = [(metrics[key], weight) for key, weight in weights.items() if metrics[key] is not None]
    if not available:
        return 100.0
    similarity = sum(float(value) * weight for value, weight in available) / sum(
        weight for _, weight in available
    )
    return round((1.0 - max(0.0, min(1.0, similarity))) * 100, 2)


def _finding(
    key: str,
    level: str,
    title: str,
    detail: str,
    suggestion: str,
    pair: str,
) -> dict[str, str]:
    return {
        "key": key,
        "level": level,
        "title": title,
        "detail": detail,
        "suggestion": suggestion,
        "stagePair": pair,
    }


def _compare_pair(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    previous_doc: DocInfo = previous["doc"]
    current_doc: DocInfo = current["doc"]
    previous_objective = _section_text(previous_doc.sections, _OBJECTIVE_RE) or previous_doc.abstract_cn
    current_objective = _section_text(current_doc.sections, _OBJECTIVE_RE) or current_doc.abstract_cn
    metrics: dict[str, float | None] = {
        "topicSimilarity": _cosine(_tokens(previous_doc.full_text), _tokens(current_doc.full_text)),
        "objectiveSimilarity": _cosine(_tokens(previous_objective), _tokens(current_objective)),
        "outlineSimilarity": _cosine(_tokens(_heading_text(previous_doc)), _tokens(_heading_text(current_doc))),
        "keywordRetention": _jaccard(previous_doc.keywords, current_doc.keywords),
    }
    previous_length = int(previous_doc.stats.get("total_chars", 0))
    current_length = int(current_doc.stats.get("total_chars", 0))
    metrics["lengthRatio"] = round(current_length / previous_length, 4) if previous_length else None
    metrics = {key: _round_metric(value) for key, value in metrics.items()}
    drift_score = _weighted_drift(metrics)
    pair = f"{previous['stage']}->{current['stage']}"
    findings: list[dict[str, str]] = []

    topic = metrics["topicSimilarity"]
    if topic is not None and topic < 0.35:
        findings.append(_finding(
            "topic-drift", "error", "研究主题发生显著词汇漂移",
            f"相邻阶段正文词汇相似度为 {topic:.2f}。",
            "核对研究题目、对象和核心问题是否已获批准变更，并在阶段说明中记录原因。", pair,
        ))
    elif topic is not None and topic < 0.55:
        findings.append(_finding(
            "topic-drift", "warning", "研究主题存在词汇漂移",
            f"相邻阶段正文词汇相似度为 {topic:.2f}。",
            "逐项核对研究对象、核心问题与预期成果，补充变更说明。", pair,
        ))

    objective = metrics["objectiveSimilarity"]
    if objective is not None and objective < 0.45:
        findings.append(_finding(
            "objective-drift", "warning", "研究目标延续性较弱",
            f"目标相关章节或摘要的词汇相似度为 {objective:.2f}。",
            "建立开题目标到当前成果的对应表，说明删除、新增或调整的目标。", pair,
        ))

    outline = metrics["outlineSimilarity"]
    if outline is not None and outline < 0.40:
        findings.append(_finding(
            "outline-drift", "warning", "章节结构变化较大",
            f"标题结构词汇相似度为 {outline:.2f}。",
            "检查关键研究任务是否因章节调整而遗漏，并记录目录变更依据。", pair,
        ))

    length_ratio = metrics["lengthRatio"]
    if length_ratio is not None and length_ratio < 0.75:
        findings.append(_finding(
            "content-regression", "warning", "后续阶段正文规模明显缩减",
            f"当前阶段正文字符数约为上一阶段的 {length_ratio:.0%}。",
            "确认是否误传版本，或说明删减内容及其对研究目标的影响。", pair,
        ))

    return {
        "fromStage": previous["stage"],
        "toStage": current["stage"],
        "metrics": metrics,
        "driftScore": drift_score,
        "findings": findings,
    }


def compare_stage_documents(documents: list[tuple[str, Path, str]]) -> dict[str, Any]:
    """Compare two or three canonical thesis stages in chronological order."""
    if not 2 <= len(documents) <= 3:
        raise ValueError("跨阶段对比需要 2 到 3 个文档")
    stages = [stage for stage, _, _ in documents]
    if any(stage not in STAGE_ORDER for stage in stages) or len(set(stages)) != len(stages):
        raise ValueError("阶段必须是互不重复的 proposal、midterm 或 final")
    parsed: list[dict[str, Any]] = []
    for stage, path, filename in sorted(documents, key=lambda item: STAGE_ORDER[item[0]]):
        doc = parse_docx(path)
        parsed.append({"stage": stage, "filename": filename, "doc": doc})

    comparisons = [_compare_pair(parsed[index - 1], parsed[index]) for index in range(1, len(parsed))]
    scores = [comparison["driftScore"] for comparison in comparisons]
    overall_score = round(max(scores) * 0.6 + (sum(scores) / len(scores)) * 0.4, 2)
    risk_level = "high" if overall_score >= 65 else "medium" if overall_score >= 35 else "low"
    findings = [finding for comparison in comparisons for finding in comparison["findings"]]
    for finding in findings:
        finding["citation"] = cite_for(f"{finding['title']} {finding['detail']}")
    stage_summaries = []
    for item in parsed:
        doc: DocInfo = item["doc"]
        stage_summaries.append({
            "stage": item["stage"],
            "stageLabel": STAGE_LABELS[item["stage"]],
            "filename": item["filename"],
            "stats": dict(doc.stats),
            "keywords": list(doc.keywords),
            "headings": [section.title for section in doc.sections],
            "hasObjectiveSection": bool(_section_text(doc.sections, _OBJECTIVE_RE)),
            "hasMethodSection": bool(_section_text(doc.sections, _METHOD_RE)),
        })
    return {
        "agent": "cross_stage",
        "report": {
            "stageCount": len(parsed),
            "stages": stage_summaries,
            "comparisons": comparisons,
            "findings": findings,
            "overallDriftScore": overall_score,
            "riskLevel": risk_level,
            "method": "确定性的中文二元词频余弦相似度、关键词集合重合度、标题结构和篇幅变化",
            "disclaimer": "结果是可解释的词汇与结构漂移提示，不等同于语义事实判断或学术不端认定。",
        },
    }
