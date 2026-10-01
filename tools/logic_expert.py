"""论文逻辑专家：结构、论证与 AI 痕迹的启发式分析，输出逻辑分（0-100）。"""
from __future__ import annotations

import re
from typing import Callable, List, Optional

from tools.docx_parser import DocInfo
from tools.knowledge_base import cite_for
from tools.logger import get_logger
from tools.logic_ai_checks import (calc_ai_likelihood, check_abstract_conclusion_similarity,
                                   check_ai_cliche, check_connector_overuse,
                                   check_low_diversity, check_no_data_support,
                                   check_paragraph_duplicate, check_prefix_repeat,
                                   check_sentence_uniformity)
from tools.logic_checks import LogicContext
from tools.logic_checks import check_deictic_start
from tools.logic_checks import check_heading_content_mismatch
from tools.logic_checks import check_heading_duplicate
from tools.logic_checks import check_heading_level_jump
from tools.logic_checks import check_hedge_overuse
from tools.logic_checks import check_long_paragraph
from tools.logic_checks import check_no_evidence
from tools.logic_checks import check_one_sentence_paragraph
from tools.logic_checks import check_section_balance
from tools.logic_checks import check_section_order
from tools.logic_checks import check_structure_completeness
from tools.logic_checks import check_stage_requirements
from tools.logic_utils import split_paragraphs, split_sentences
from tools.models import LogicFinding, LogicReport

logger = get_logger('logic')

# 不参与逻辑分析的章节（目录、文献、致谢等）
EXCLUDE_TITLE_RE = re.compile(r'(目录|参考文献|致谢|附录|声明|原创性|摘\s*要|Abstract)', re.I)


def _build_context(doc: DocInfo) -> LogicContext:
    """构建逻辑分析上下文。

    Args:
        doc: 论文结构化信息。

    Returns:
        LogicContext 对象。
    """
    sections = [s for s in doc.sections if not EXCLUDE_TITLE_RE.search(s.title)]
    # 标题中的间隔空格（如「结  论」）会干扰关键词匹配，统一去掉
    for section in sections:
        section.title = re.sub(r'\s+', '', section.title)
    body_text = '\n'.join(s.text for s in sections)
    if len(body_text) < 500:
        body_text = doc.full_text
    clean = re.sub(r'\s+', '', body_text)
    return LogicContext(
        doc=doc,
        body_text=body_text,
        sections=sections,
        sentences=split_sentences(body_text),
        paragraphs=split_paragraphs(body_text, 20),
        total_chars=len(clean),
    )


ALL_CHECKS: List[Callable[[LogicContext], Optional[LogicFinding]]] = [
    check_structure_completeness,
    check_section_order,
    check_section_balance,
    check_heading_level_jump,
    check_heading_duplicate,
    check_heading_content_mismatch,
    check_long_paragraph,
    check_one_sentence_paragraph,
    check_no_evidence,
    check_hedge_overuse,
    check_deictic_start,
    check_ai_cliche,
    check_sentence_uniformity,
    check_prefix_repeat,
    check_low_diversity,
    check_connector_overuse,
    check_paragraph_duplicate,
    check_abstract_conclusion_similarity,
    check_no_data_support,
]


class LogicExpert:
    """论文逻辑专家：检查结构、论证与 AI 生成痕迹。"""

    def analyze(self, doc: DocInfo, stage: Optional[str] = None) -> LogicReport:
        """执行逻辑分析。

        Args:
            doc: 论文结构化信息。
            stage: 论文阶段（proposal/midterm/final），用于阶段要素检查与依据检索。

        Returns:
            LogicReport，含逻辑分与 AI 可能性评分。
        """
        ctx = _build_context(doc)
        findings: List[LogicFinding] = []
        for check in ALL_CHECKS:
            try:
                result = check(ctx)
            except Exception as exc:  # noqa: BLE001 - 单项异常不影响整体
                logger.warning('逻辑检查项 %s 执行失败：%s', getattr(check, '__name__', ''), exc)
                continue
            if result:
                findings.append(result)
        if stage:
            try:
                stage_result = check_stage_requirements(ctx, stage)
            except Exception as exc:  # noqa: BLE001 - 阶段检查异常不影响整体
                logger.warning('阶段要素检查失败：%s', exc)
            else:
                if stage_result:
                    findings.append(stage_result)
        _attach_citations(findings, stage)

        penalty = sum(f.penalty for f in findings)
        score = round(max(0.0, min(100.0, 100.0 - penalty)), 1)
        ai_likelihood = calc_ai_likelihood(ctx.metrics)
        return LogicReport(
            findings=findings,
            score=score,
            ai_likelihood=ai_likelihood,
            metrics=ctx.metrics,
            strengths=_build_strengths(ctx, ai_likelihood),
        )


def _attach_citations(findings: List[LogicFinding], stage: Optional[str]) -> None:
    """为每条发现项附加知识库中的规范条文作为依据。"""
    for finding in findings:
        finding.citation = cite_for(f"{finding.title} {finding.detail}", stage=stage)


def _build_strengths(ctx: LogicContext, ai_likelihood: float) -> List[str]:
    """根据指标生成论文的优点清单。

    Args:
        ctx: 逻辑分析上下文。
        ai_likelihood: AI 生成可能性评分。

    Returns:
        优点描述列表。
    """
    items: List[str] = []
    if not ctx.metrics.get('missing_sections'):
        items.append('章节结构完整，覆盖研究背景、方案设计与结论')
    if ctx.metrics.get('level_jumps', 0) == 0 and ctx.metrics.get('duplicates', 0) == 0:
        items.append('标题层级规范，未出现跳级或重复标题')
    ratio = ctx.metrics.get('no_evidence_ratio', 1.0)
    if ratio <= 0.45:
        items.append('多数段落配有数据、图表或文献引用等论据支撑')
    if ctx.metrics.get('sentence_cv', 0.0) >= 0.5:
        items.append('句式长短结合，行文节奏自然')
    if ctx.metrics.get('diversity', 0.0) >= 0.6:
        items.append('用词丰富，表达重复度低')
    if ai_likelihood <= 30:
        items.append('AI 生成痕迹不明显，写作风格较为个人化')
    if not items:
        items.append('论文整体已成形，按下列建议修改后可明显提升质量')
    return items
