"""评分模块：格式分与逻辑分的合成、等级评定与总评生成。"""
from __future__ import annotations

from typing import Optional


def combine(format_score: Optional[float], logic_score: float,
            format_weight: float = 0.5, logic_weight: float = 0.5) -> Optional[float]:
    """合成总分。

    Args:
        format_score: 格式分（None 表示未配置规范，此时仅返回逻辑分）。
        logic_score: 逻辑分。
        format_weight: 格式分权重。
        logic_weight: 逻辑分权重。

    Returns:
        0-100 的总分；format_score 为 None 时返回逻辑分。
    """
    if format_score is None:
        return round(max(0.0, min(100.0, logic_score)), 1)
    total_weight = format_weight + logic_weight
    if total_weight <= 0:
        return round(logic_score, 1)
    score = (format_score * format_weight + logic_score * logic_weight) / total_weight
    return round(max(0.0, min(100.0, score)), 1)


def grade(score: Optional[float]) -> str:
    """将分数转换为等级描述。

    Args:
        score: 0-100 的分值。

    Returns:
        等级文字：优秀 / 良好 / 中等 / 合格 / 待大幅修改 / 未评分。
    """
    if score is None:
        return '未评分'
    if score >= 90:
        return '优秀'
    if score >= 80:
        return '良好'
    if score >= 70:
        return '中等'
    if score >= 60:
        return '合格'
    return '待大幅修改'


def summarize(format_score: Optional[float], logic_score: float,
              ai_likelihood: float, total_score: Optional[float]) -> str:
    """生成一句话总评。

    Args:
        format_score: 格式分。
        logic_score: 逻辑分。
        ai_likelihood: AI 生成可能性。
        total_score: 总分。

    Returns:
        总评文本。
    """
    parts = []
    if total_score is not None:
        parts.append(f"综合得分 {total_score} 分（{grade(total_score)}）")
    if format_score is None:
        parts.append('格式规范尚未配置，暂未计入格式分')
    elif format_score >= 85:
        parts.append('格式规范执行情况良好')
    elif format_score >= 70:
        parts.append('格式存在若干偏差，需按清单逐项修订')
    else:
        parts.append('格式问题较多，建议按规范逐项整改')

    if logic_score >= 85:
        parts.append('论文结构清晰、论证较充分')
    elif logic_score >= 70:
        parts.append('逻辑基本通顺，但存在章节或论证上的短板')
    else:
        parts.append('逻辑问题突出，需重点调整章节结构与论证链条')

    if ai_likelihood >= 70:
        parts.append(f"AI 生成痕迹明显（{ai_likelihood} 分），建议人工重写关键章节")
    elif ai_likelihood >= 45:
        parts.append(f"存在一定 AI 写作痕迹（{ai_likelihood} 分），建议润色以降低模板化表达")
    else:
        parts.append(f"AI 生成痕迹不明显（{ai_likelihood} 分）")
    return '；'.join(parts) + '。'
