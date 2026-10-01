"""逻辑检查项（二）：AI 生成痕迹启发式检测。"""
from __future__ import annotations

import re
from typing import Optional

from tools.logic_checks import LogicContext, _finding
from tools.logic_dict import AI_CLICHE, AI_PATTERNS, CONNECTORS
from tools.logic_utils import coefficient_of_variation
from tools.logic_utils import count_patterns, count_terms
from tools.logic_utils import find_duplicate_paragraphs, jaccard
from tools.logic_utils import ngram_diversity, prefix_repeat_rate
from tools.models import LogicFinding


def check_ai_cliche(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查 AI 高频套话密度。"""
    if ctx.total_chars < 300:
        return None
    hits = count_terms(ctx.body_text, AI_CLICHE)
    hits += count_patterns(ctx.body_text, AI_PATTERNS)
    density = hits * ctx.per_k
    ctx.metrics['cliche_density'] = round(density, 3)
    if density <= 2.5:
        return None
    return _finding(
        'ai_cliche', 'ai', 'AI 高频套话密集',
        'error' if density > 5 else 'warning',
        min(10.0, (density - 2.0) * 1.8),
        f"检测到模板化套话约 {hits} 处（{density:.1f} 处/千字）",
        '删除空洞套话与过渡句，改为陈述具体的研究问题、方法与结论',
        {'hits': float(hits), 'density': round(density, 3)},
    )


def check_sentence_uniformity(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查句长是否过于均匀（AI 生成文本的典型特征）。"""
    lengths = [float(len(s)) for s in ctx.sentences]
    if len(lengths) < 30:
        return None
    cv = coefficient_of_variation(lengths)
    ctx.metrics['sentence_cv'] = cv
    if cv >= 0.42:
        return None
    return _finding(
        'sentence_uniformity', 'ai', '句长过于均匀', 'warning',
        min(6.0, (0.42 - cv) * 22.0),
        f"句长变异系数仅 {cv:.2f}（正常写作通常 > 0.45），长短句节奏高度一致",
        '适当使用短句强调重点、长句展开论述，形成自然的节奏变化',
        {'cv': cv},
    )


def check_prefix_repeat(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查句首重复率（模板化句式信号）。"""
    if len(ctx.sentences) < 30:
        return None
    rate = prefix_repeat_rate(ctx.sentences, 4)
    ctx.metrics['prefix_repeat'] = rate
    if rate <= 0.32:
        return None
    return _finding(
        'prefix_repeat', 'ai', '句式开头高度雷同', 'warning',
        min(7.0, (rate - 0.30) * 20.0),
        f"{rate * 100:.0f}% 的句子使用相同的前 4 个字开头，疑似模板化生成",
        '改写句子开头，避免连续使用同一句式结构',
        {'rate': rate},
    )


def check_low_diversity(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查用词多样性是否偏低。"""
    if ctx.total_chars < 800:
        return None
    diversity = ngram_diversity(ctx.body_text, 2)
    ctx.metrics['diversity'] = diversity
    if diversity >= 0.5:
        return None
    return _finding(
        'low_diversity', 'ai', '用词重复度高', 'warning',
        min(6.0, (0.5 - diversity) * 24.0),
        f"二字组多样性仅 {diversity:.2f}，用词偏贫乏、表达重复",
        '丰富专业术语与表达方式，合并重复表述',
        {'diversity': diversity},
    )


def check_connector_overuse(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查逻辑连接词是否过度堆砌。"""
    if ctx.total_chars < 500:
        return None
    density = count_terms(ctx.body_text, CONNECTORS) * ctx.per_k
    ctx.metrics['connector_density'] = round(density, 3)
    if density <= 26.0:
        return None
    return _finding(
        'connector_overuse', 'ai', '逻辑连接词堆砌', 'warning',
        min(5.0, (density - 26.0) / 6.0),
        f"连接词密度约 {density:.1f} 处/千字，「首先/其次/然而/因此」等堆砌明显",
        '减少机械的过渡词，用内容本身的因果与递进关系组织段落',
        {'density': round(density, 3)},
    )


def check_paragraph_duplicate(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查是否存在高度重复的段落。"""
    if len(ctx.paragraphs) < 6:
        return None
    pairs = find_duplicate_paragraphs(ctx.paragraphs)
    ctx.metrics['duplicate_pairs'] = float(len(pairs))
    if not pairs:
        return None
    return _finding(
        'paragraph_duplicate', 'ai', '段落内容高度重复', 'warning',
        min(6.0, 2.0 * len(pairs)),
        f"发现 {len(pairs)} 组相似度超过 70% 的段落，疑似复制或生成复用",
        '删除或改写重复段落，确保每段论述都有独立信息量',
        {'pairs': float(len(pairs))},
    )


def check_abstract_conclusion_similarity(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查摘要与结论是否高度雷同。"""
    abstract = ctx.doc.abstract_cn
    conclusion = ctx.doc.conclusion_text
    if len(abstract) < 80 or len(conclusion) < 80:
        return None
    sim = jaccard(abstract, conclusion, 2)
    ctx.metrics['abstract_conclusion_sim'] = sim
    if sim <= 0.5:
        return None
    return _finding(
        'abstract_conclusion_similarity', 'ai', '摘要与结论高度雷同', 'warning',
        min(5.0, (sim - 0.45) * 12.0),
        f"摘要与结论的相似度达 {sim:.0%}，结论未给出研究层面的提炼",
        '结论应总结研究成果、创新点与不足，避免直接复制摘要文字',
        {'sim': sim},
    )


def check_no_data_support(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查全文是否缺少数据、图表等实证支撑。"""
    if ctx.total_chars < 1000:
        return None
    figure_table = ctx.doc.table_count + ctx.doc.image_count
    digit_ratio = len(re.findall(r'\d', ctx.body_text)) / max(1, ctx.total_chars)
    ctx.metrics['digit_ratio'] = round(digit_ratio, 4)
    if figure_table >= 1 and digit_ratio >= 0.01:
        return None
    return _finding(
        'no_data_support', 'ai', '全文缺少实证支撑', 'error', 6.0,
        f"全文图表 {figure_table} 个、数字字符占比 {digit_ratio:.2%}，论证偏空泛",
        '补充实验数据、统计图表或案例细节，用事实支撑论点',
        {'figures': float(figure_table), 'digit_ratio': round(digit_ratio, 4)},
    )


def calc_ai_likelihood(metrics: dict) -> float:
    """根据多项启发式指标计算 AI 生成可能性（0-100）。

    Args:
        metrics: 预计算的指标字典。

    Returns:
        0-100 的 AI 可能性评分，越高越疑似 AI 生成。
    """
    cliche = min(1.0, metrics.get('cliche_density', 0.0) / 6.0)
    uniform = max(0.0, (0.45 - metrics.get('sentence_cv', 1.0)) / 0.45)
    prefix = min(1.0, metrics.get('prefix_repeat', 0.0) / 0.5)
    div_low = max(0.0, (0.55 - metrics.get('diversity', 1.0)) / 0.55)
    connector = min(1.0, metrics.get('connector_density', 0.0) / 40.0)
    score = (cliche * 0.30 + prefix * 0.25 + uniform * 0.20
             + div_low * 0.15 + connector * 0.10) * 100
    return round(max(0.0, min(100.0, score)), 1)
