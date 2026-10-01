"""内容合理性检查：研究目标可衡量性、阶段成果与目标对应、结论呼应目标。

不依赖外部模型，全部为可解释的启发式判断（章节定位 + 二元词余弦相似度），
只输出风险提示，不认定学术不端。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Optional

from tools.knowledge_base import tokenize
from tools.logic_checks import LogicContext
from tools.models import LogicFinding

_OBJECTIVE_RE = re.compile(r"研究(目标|目的|内容)|主要内容|课题目标|预期目标")
_RESULT_RE = re.compile(r"阶段性成果|研究进展|目前进展|已完成的|阶段成果|取得的成果|工作进展|研究进度")
_CONCLUSION_RE = re.compile(r"结论|总结|展望")
_MEASURABLE_RE = re.compile(
    r"达到|实现|提升|提高|降低|不少于|不低于|准确率|精确率|召回率|误差|指标|验证|优化|%|百分|\d+"
)

CATEGORY = "reasonableness"


def _section_text(sections, pattern: re.Pattern[str]) -> str:
    return "\n".join(s.text for s in sections if pattern.search(s.title))


def _clean_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _cosine(left: Counter[str], right: Counter[str]) -> float | None:
    if not left or not right:
        return None
    shared = left.keys() & right.keys()
    numerator = sum(left[t] * right[t] for t in shared)
    denominator = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(
        sum(v * v for v in right.values())
    )
    return round(numerator / denominator, 4) if denominator else None


def _finding(key: str, title: str, level: str, penalty: float,
             detail: str, suggestion: str, metrics: dict) -> LogicFinding:
    return LogicFinding(key=key, category=CATEGORY, title=title, level=level,
                        penalty=penalty, detail=detail, suggestion=suggestion,
                        metrics=metrics)


def check_objective_specificity(ctx: LogicContext, stage: Optional[str]) -> Optional[LogicFinding]:
    """开题：研究目标应具体、可衡量、可验证。"""
    if stage != "proposal":
        return None
    objective = _section_text(ctx.sections, _OBJECTIVE_RE) or ctx.doc.abstract_cn
    if _clean_len(objective) < 30:
        return None  # 缺少目标章节由阶段要素检查另行提示
    markers = len(_MEASURABLE_RE.findall(objective))
    ctx.metrics["objective_measurable_markers"] = float(markers)
    if markers >= 2:
        return None
    return _finding(
        "objective_specificity", "研究目标可衡量性不足", "warning", 2.0,
        "研究目标多为方向性描述，缺少可衡量、可验证的指标（如目标值、验证方式或量化标准）。",
        "将研究目标改写为可检验的形式，明确预期达到的指标、实验验证方式或对比基准。",
        {"measurable_markers": float(markers)},
    )


def check_result_objective_alignment(ctx: LogicContext, stage: Optional[str]) -> Optional[LogicFinding]:
    """中期：阶段性成果应与开题研究目标对应。"""
    if stage != "midterm":
        return None
    result = _section_text(ctx.sections, _RESULT_RE)
    objective = _section_text(ctx.sections, _OBJECTIVE_RE) or ctx.doc.abstract_cn
    if _clean_len(result) < 30 or _clean_len(objective) < 30:
        return None  # 缺章节由阶段要素检查另行提示
    sim = _cosine(tokenize(objective), tokenize(result))
    ctx.metrics["result_objective_sim"] = sim if sim is not None else 0.0
    if sim is None or sim >= 0.35:
        return None
    level = "warning" if sim < 0.2 else "info"
    return _finding(
        "result_objective_alignment", "阶段性成果与研究目标对应较弱", level,
        3.0 if level == "warning" else 1.0,
        f"阶段性成果与研究目标的词汇相似度为 {sim:.2f}，对应关系不够清晰。",
        "建立开题目标到当前阶段成果的对应说明，逐项交代已完成与未达成的内容。",
        {"result_objective_sim": sim},
    )


def check_conclusion_echo(ctx: LogicContext, stage: Optional[str]) -> Optional[LogicFinding]:
    """终稿/通用：结论应呼应研究目标。"""
    if stage not in (None, "final"):
        return None
    conclusion = _section_text(ctx.sections, _CONCLUSION_RE) or ctx.doc.conclusion_text
    objective = _section_text(ctx.sections, _OBJECTIVE_RE) or ctx.doc.abstract_cn
    if _clean_len(conclusion) < 30 or _clean_len(objective) < 30:
        return None
    sim = _cosine(tokenize(objective), tokenize(conclusion))
    ctx.metrics["conclusion_objective_sim"] = sim if sim is not None else 0.0
    if sim is None or sim >= 0.35:
        return None
    level = "warning" if sim < 0.2 else "info"
    return _finding(
        "conclusion_echo", "结论与研究目标呼应不足", level,
        3.0 if level == "warning" else 1.0,
        f"结论与研究目标的词汇相似度为 {sim:.2f}，呼应不够紧密。",
        "在结论中逐项回应研究目标，说明各目标的达成情况与依据。",
        {"conclusion_objective_sim": sim},
    )


def run_reasonableness_checks(ctx: LogicContext, stage: Optional[str]) -> List[LogicFinding]:
    """运行与给定阶段匹配的内容合理性检查，返回发现项列表。"""
    findings: List[LogicFinding] = []
    for check in (check_objective_specificity,
                  check_result_objective_alignment,
                  check_conclusion_echo):
        result = check(ctx, stage)
        if result:
            findings.append(result)
    return findings
