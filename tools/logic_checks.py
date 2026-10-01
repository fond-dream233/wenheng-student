"""逻辑检查项（一）：结构完整性与论证质量。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from tools.docx_parser import DocInfo, Section
from tools.logic_dict import DEICTIC_STARTS, EVIDENCE_PATTERNS, HEDGES
from tools.logic_utils import cn_len, count_patterns, count_terms, split_sentences
from tools.models import LogicFinding


@dataclass
class LogicContext:
    """逻辑分析上下文：预计算的文本与统计特征。"""

    doc: DocInfo
    body_text: str = ''
    sections: List[Section] = field(default_factory=list)
    sentences: List[str] = field(default_factory=list)
    paragraphs: List[str] = field(default_factory=list)
    total_chars: int = 0
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def per_k(self) -> float:
        """每千字换算系数（用于密度计算）。"""
        return 1000.0 / max(1, self.total_chars)


def _finding(key: str, category: str, title: str, level: str, penalty: float,
             detail: str, suggestion: str, metrics: Dict[str, float]) -> LogicFinding:
    """构造 LogicFinding 对象。"""
    return LogicFinding(key=key, category=category, title=title, level=level,
                        penalty=penalty, detail=detail, suggestion=suggestion,
                        metrics=metrics)


def check_structure_completeness(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查关键章节是否齐全。"""
    titles = [s.title for s in ctx.sections] or [p.text for p in ctx.doc.paragraphs if p.is_heading]
    # 标题常含间隔空格（如「结  论」），匹配前统一去掉空白
    joined = ' '.join(titles).replace(' ', '')
    groups = [
        ('研究背景与意义', ['绪论', '引言', '前言', '概述']),
        ('国内外研究现状', ['综述', '相关研究', '国内外', '研究现状']),
        ('研究方案或方法', ['设计', '方法', '模型', '算法', '方案', '原理']),
        ('实验或实现', ['实验', '实现', '测试', '结果', '仿真']),
        ('结论与展望', ['结论', '总结', '展望']),
    ]
    missing = [label for label, keys in groups if not any(k in joined for k in keys)]
    ctx.metrics['missing_sections'] = float(len(missing))
    if not missing:
        return None
    return _finding(
        'structure_completeness', 'structure', '章节结构不完整',
        'error' if len(missing) >= 2 else 'warning',
        min(10.0, 2.5 * len(missing)),
        f"缺少关键章节：{'、'.join(missing)}",
        '按「绪论 → 研究现状 → 方案设计 → 实验验证 → 结论」补齐章节骨架',
        {'missing': float(len(missing))},
    )


def check_section_order(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查章节顺序是否合理。"""
    titles = [s.title for s in ctx.sections]
    if len(titles) < 3:
        return None
    conclusion = [i for i, t in enumerate(titles) if re.search(r'(结论|总结|展望)', t)]
    evidence = [i for i, t in enumerate(titles) if re.search(r'(实验|实现|测试|结果)', t)]
    design = [i for i, t in enumerate(titles) if re.search(r'(设计|方案|方法|模型)', t)]
    problems = []
    if conclusion and evidence and min(conclusion) < max(evidence):
        problems.append('结论章节出现在实验/结果章节之前')
    if evidence and design and max(evidence) < min(design):
        problems.append('实验/实现章节出现在方案设计之前')
    if not problems:
        return None
    return _finding(
        'section_order', 'structure', '章节顺序不合理', 'error', 5.0,
        '；'.join(problems),
        '按「背景 → 现状 → 设计 → 实现/实验 → 结论」调整章节顺序',
        {'problems': float(len(problems))},
    )


def check_section_balance(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查各章节篇幅是否失衡。"""
    if len(ctx.sections) < 3 or ctx.total_chars < 2000:
        return None
    counts = [(s.title, cn_len(s.text)) for s in ctx.sections]
    total = sum(c for _, c in counts) or 1
    ratios = [(t, c / total) for t, c in counts]
    huge = [(t, r) for t, r in ratios if r > 0.45]
    tiny = [(t, r) for t, r in ratios if 0 < r < 0.02]
    ctx.metrics['max_section_ratio'] = round(max(r for _, r in ratios), 4)
    if not huge and len(tiny) < 3:
        return None
    parts = [f"「{t[:16]}」占 {r * 100:.0f}%" for t, r in huge[:3]]
    if len(tiny) >= 3:
        parts.append(f"{len(tiny)} 个章节篇幅不足 2%")
    return _finding(
        'section_balance', 'structure', '章节篇幅失衡', 'warning',
        min(6.0, 2.0 * len(huge) + (2.0 if len(tiny) >= 3 else 0.0)),
        '；'.join(parts),
        '均衡各章节篇幅，过短章节合并或补充内容',
        {'huge': float(len(huge)), 'tiny': float(len(tiny))},
    )


def check_heading_level_jump(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查标题层级是否跳级。"""
    levels = [(p.text.strip(), p.level or 1) for p in ctx.doc.paragraphs if p.is_heading]
    jumps = []
    for i in range(1, len(levels)):
        prev, cur = levels[i - 1][1], levels[i][1]
        if cur - prev > 1:
            jumps.append(f"「{levels[i - 1][0][:14]}」({prev}级) 后直接出现「{levels[i][0][:14]}」({cur}级)")
    ctx.metrics['level_jumps'] = float(len(jumps))
    if not jumps:
        return None
    return _finding(
        'heading_level_jump', 'structure', '标题层级跳级', 'warning',
        min(5.0, 1.5 * len(jumps)),
        '；'.join(jumps[:4]),
        '补齐中间层级标题，保证层级逐级递进',
        {'jumps': float(len(jumps))},
    )


def check_heading_duplicate(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查是否存在重复标题。"""
    titles = [p.text.strip() for p in ctx.doc.paragraphs if p.is_heading and p.text.strip()]
    dup = {t for t in titles if titles.count(t) > 1}
    if not dup:
        return None
    return _finding(
        'heading_duplicate', 'structure', '存在重复标题', 'warning',
        min(4.0, 1.5 * len(dup)),
        f"重复标题 {len(dup)} 处：{'、'.join(list(dup)[:4])}",
        '合并重复章节或改写标题，使各章节标题唯一',
        {'duplicates': float(len(dup))},
    )


def check_heading_content_mismatch(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查标题关键词是否在所属章节正文中缺失（跑题）。"""
    if not ctx.sections:
        return None
    mismatched = []
    for section in ctx.sections:
        keywords = re.findall(r'[一-龥]{2,6}', re.sub(r'^[\d.\s、]+', '', section.title))
        keywords = [k for k in keywords if k not in ('研究', '分析', '设计', '本章', '小结')]
        body = section.text
        if not keywords or cn_len(body) < 100:
            continue
        hit = sum(1 for k in keywords if k in body)
        if hit == 0:
            mismatched.append(section.title[:18])
    if not mismatched:
        return None
    return _finding(
        'heading_content_mismatch', 'structure', '标题与内容不匹配', 'warning',
        min(5.0, 2.0 * len(mismatched)),
        f"{len(mismatched)} 个章节正文未出现标题关键词：{'、'.join(mismatched[:4])}",
        '改写标题使其准确概括内容，或补充与标题对应的论证内容',
        {'mismatched': float(len(mismatched))},
    )


def check_long_paragraph(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查是否存在过长的段落。"""
    longs = [p for p in ctx.paragraphs if cn_len(p) > 600]
    if not ctx.paragraphs:
        return None
    ratio = len(longs) / len(ctx.paragraphs)
    ctx.metrics['long_paragraph_ratio'] = round(ratio, 4)
    if ratio <= 0.05:
        return None
    return _finding(
        'long_paragraph', 'argument', '存在超长段落', 'warning',
        min(5.0, ratio * 12.0),
        f"{len(longs)} 个段落超过 600 字（占 {ratio * 100:.0f}%）",
        '按论点拆分长段落，一个段落围绕一个中心意思展开',
        {'ratio': round(ratio, 4)},
    )


def check_one_sentence_paragraph(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查单句成段比例是否过高（论证碎片化）。"""
    if len(ctx.paragraphs) < 10:
        return None
    single = [p for p in ctx.paragraphs if len(split_sentences(p)) <= 1 and cn_len(p) < 120]
    ratio = len(single) / len(ctx.paragraphs)
    ctx.metrics['single_sentence_ratio'] = round(ratio, 4)
    if ratio <= 0.25:
        return None
    return _finding(
        'one_sentence_paragraph', 'argument', '单句段落过多', 'warning',
        min(5.0, (ratio - 0.25) * 16.0),
        f"单句成段 {len(single)} 处（占 {ratio * 100:.0f}%），论证显碎片化",
        '将孤立短句并入相邻段落，围绕论点组织成完整的论证单元',
        {'ratio': round(ratio, 4)},
    )


def check_no_evidence(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查段落是否有数据/图表/引用等论据支撑。"""
    if len(ctx.paragraphs) < 8:
        return None
    weak = [p for p in ctx.paragraphs if count_patterns(p, EVIDENCE_PATTERNS) == 0]
    ratio = len(weak) / len(ctx.paragraphs)
    ctx.metrics['no_evidence_ratio'] = round(ratio, 4)
    if ratio <= 0.55:
        return None
    return _finding(
        'no_evidence', 'argument', '大量段落缺少论据支撑', 'error',
        min(8.0, (ratio - 0.5) * 18.0),
        f"约 {ratio * 100:.0f}% 的段落未出现数据、图表、引用或案例等论据",
        '为每个核心论点补充数据、实验对比、文献引用或具体案例',
        {'ratio': round(ratio, 4)},
    )


def check_hedge_overuse(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查模糊限定词是否过度使用。"""
    if ctx.total_chars < 500:
        return None
    density = count_terms(ctx.body_text, HEDGES) * ctx.per_k
    ctx.metrics['hedge_density'] = round(density, 3)
    if density <= 9.0:
        return None
    return _finding(
        'hedge_overuse', 'argument', '模糊表述过多', 'warning',
        min(5.0, (density - 9.0) / 4.0),
        f"模糊限定词（可能、一定程度上、较为…）密度约 {density:.1f} 处/千字",
        '把模糊表述替换为可验证的结论或具体数据，避免言之无物',
        {'density': round(density, 3)},
    )


def check_deictic_start(ctx: LogicContext) -> Optional[LogicFinding]:
    """检查段首指代是否明确。"""
    if len(ctx.paragraphs) < 8:
        return None
    starts = [p for p in ctx.paragraphs
              if p[:1] in DEICTIC_STARTS and not re.match(r'^(这种|这样)[^，。]{0,10}(?:情况|问题|方法|技术)', p)]
    ratio = len(starts) / len(ctx.paragraphs)
    ctx.metrics['deictic_ratio'] = round(ratio, 4)
    if ratio <= 0.2:
        return None
    return _finding(
        'deictic_start', 'argument', '段首指代不清', 'warning',
        min(4.0, (ratio - 0.2) * 12.0),
        f"{ratio * 100:.0f}% 的段落以「这/该/其」等代词开头，指代对象不明确",
        '把代词替换为明确的主语，避免读者回溯上下文猜测指代',
        {'ratio': round(ratio, 4)},
    )
