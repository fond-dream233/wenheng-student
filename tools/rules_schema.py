"""格式规则定义：规则元数据、分组与「西南科技大学 2026 届模板」默认规范。

说明：preset 取自学校《本科毕业论文（设计）模板（2026届）定稿》实测值，
数据库初始化时按 preset 默认启用；教师可在「格式规范配置」页逐项调整，
清空后留空的规则在分析时自动跳过（不计入格式分）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RuleDef:
    """一条可配置的格式规则定义。

    Attributes:
        key: 规则唯一键。
        category: 所属分组（page/body/heading/structure/toc/figure/ref/misc）。
        title: 规则中文名。
        input_type: 配置控件类型（text/number/select/checkbox）。
        unit: 数值单位，用于页面展示。
        options: select 控件候选值。
        default_weight: 默认权重（占总分的比重）。
        preset: 通用参考规范建议值（空字符串表示无建议值）。
        hint: 填写说明。
    """

    key: str
    category: str
    title: str
    input_type: str = "text"
    unit: str = ""
    options: List[str] = field(default_factory=list)
    default_weight: int = 3
    preset: str = ""
    hint: str = ""


CATEGORIES: Dict[str, str] = {
    "page": "页面设置",
    "body": "正文格式",
    "heading": "标题格式",
    "structure": "结构完整性与篇幅",
    "toc": "目录",
    "figure": "图与表",
    "ref": "参考文献",
    "misc": "排版细节",
}

RULES: List[RuleDef] = [
    # ---------- 页面设置（模板：A4，上下左右各 2.5cm） ----------
    RuleDef("page_size", "page", "纸张大小", "select", options=["A4", "A3"], preset="A4",
            default_weight=2, hint="本科论文通常为 A4"),
    RuleDef("margin_top", "page", "上页边距", "number", unit="cm", preset="2.5", default_weight=2),
    RuleDef("margin_bottom", "page", "下页边距", "number", unit="cm", preset="2.5", default_weight=2),
    RuleDef("margin_left", "page", "左页边距", "number", unit="cm", preset="2.5", default_weight=2),
    RuleDef("margin_right", "page", "右页边距", "number", unit="cm", preset="2.5", default_weight=2),
    RuleDef("page_number_required", "page", "要求插入页码", "checkbox", preset="1", default_weight=2,
            hint="模板要求：正文用阿拉伯数字，前置部分用罗马数字，页面底端居中"),

    # ---------- 正文格式（模板：宋体/Times New Roman 小四，固定值 22 磅，首行缩进 2 字符） ----------
    RuleDef("body_font_cn", "body", "正文中文字体", "text", preset="宋体", default_weight=4),
    RuleDef("body_font_en", "body", "正文西文字体", "text", preset="Times New Roman", default_weight=2),
    RuleDef("body_size_pt", "body", "正文字号", "number", unit="pt", preset="12", default_weight=4,
            hint="小四 = 12pt，四号 = 14pt，五号 = 10.5pt"),
    RuleDef("line_spacing", "body", "正文行距", "number", unit="磅/倍", preset="22", default_weight=4,
            hint="填 >6 视为固定值磅（如 22），填 ≤6 视为倍数（如 1.5）"),
    RuleDef("first_line_indent", "body", "正文首行缩进", "number", unit="字符", preset="2", default_weight=3),
    RuleDef("body_align", "body", "正文对齐方式", "select",
            options=["both（两端对齐）", "left（左对齐）", "center（居中）"],
            preset="both（两端对齐）", default_weight=2),

    # ---------- 标题格式（模板：黑体；章小二居中，节一级四号居左，节二级小四居左） ----------
    RuleDef("heading_font_cn", "heading", "标题中文字体", "text", preset="黑体", default_weight=3),
    RuleDef("heading_bold", "heading", "标题要求加粗", "checkbox", preset="0", default_weight=2,
            hint="学校模板未强制标题加粗，故默认不检查"),
    RuleDef("heading1_size_pt", "heading", "一级（章）标题字号", "number", unit="pt", preset="18",
            default_weight=3, hint="小二 = 18pt"),
    RuleDef("heading2_size_pt", "heading", "二级标题字号", "number", unit="pt", preset="14",
            default_weight=2, hint="四号 = 14pt"),
    RuleDef("heading3_size_pt", "heading", "三级标题字号", "number", unit="pt", preset="12",
            default_weight=2, hint="小四 = 12pt"),
    RuleDef("heading1_align", "heading", "一级（章）标题对齐", "select",
            options=["center（居中）", "left（左对齐）", "none（不检查）"],
            preset="center（居中）", default_weight=2),
    RuleDef("heading_align", "heading", "二、三级标题对齐", "select",
            options=["left（左对齐）", "center（居中）", "none（不检查）"],
            preset="left（左对齐）", default_weight=2),
    RuleDef("heading_number_style", "heading", "标题编号方式", "select",
            options=["arabic（第1章 / 1.1 / 1.1.1）", "chinese（一、/（一）/ 1.）", "none（不检查）"],
            preset="arabic（第1章 / 1.1 / 1.1.1）", default_weight=3,
            hint="章标题可用「第1章」，节标题用「1.1 / 1.1.1」"),
    RuleDef("heading_use_style", "heading", "标题须使用样式/大纲级别", "checkbox", preset="1",
            default_weight=3, hint="避免使用手动加粗的「伪标题」"),

    # ---------- 结构与篇幅（模板：摘要 300-800 字，关键词 3~5 个，须有英文摘要） ----------
    RuleDef("required_sections", "structure", "必需章节", "text",
            preset="摘要,目录,结论,参考文献,致谢", default_weight=6,
            hint="英文逗号分隔；英文摘要另有单独检查项"),
    RuleDef("min_total_words", "structure", "正文最少字数", "number", unit="字", preset="10000", default_weight=4),
    RuleDef("abstract_word_min", "structure", "摘要最少字数", "number", unit="字", preset="300", default_weight=2),
    RuleDef("abstract_word_max", "structure", "摘要最多字数", "number", unit="字", preset="800", default_weight=2),
    RuleDef("keyword_count", "structure", "关键词个数", "number", unit="个", preset="4", default_weight=2,
            hint="模板要求 3~5 个，此处填目标值，±1 个不扣分"),
    RuleDef("require_english_abstract", "structure", "要求英文摘要", "number", preset="1", default_weight=2,
            hint="1=要求，0=不要求"),

    # ---------- 目录（模板：只显示三级标题） ----------
    RuleDef("toc_required", "toc", "要求目录", "checkbox", preset="1", default_weight=3),
    RuleDef("toc_auto", "toc", "目录须自动生成（带页码域）", "checkbox", preset="1", default_weight=2),
    RuleDef("toc_max_level", "toc", "目录最多层级", "number", unit="级", preset="3", default_weight=2),

    # ---------- 图与表（模板：图题在图下方加粗五号，表题在表上方五号，按章编号） ----------
    RuleDef("figure_caption_position", "figure", "图题位置", "select",
            options=["below（图下方）", "above（图上方）", "none（不检查）"],
            preset="below（图下方）", default_weight=2),
    RuleDef("table_caption_position", "figure", "表题位置", "select",
            options=["above（表上方）", "below（表下方）", "none（不检查）"],
            preset="above（表上方）", default_weight=2),
    RuleDef("caption_numbering", "figure", "图表编号方式", "select",
            options=["chapter（图1-1 按章编号）", "continuous（图1 全文连续）", "none（不检查）"],
            preset="chapter（图1-1 按章编号）", default_weight=2),
    RuleDef("caption_size_pt", "figure", "图表题注字号", "number", unit="pt", preset="10.5",
            default_weight=2, hint="五号 = 10.5pt"),

    # ---------- 参考文献（模板：中文宋体五号，英文数字 Times New Roman 五号，GB/T 7714） ----------
    RuleDef("ref_min_count", "ref", "参考文献最少条数", "number", unit="条", preset="15", default_weight=5),
    RuleDef("ref_standard", "ref", "参考文献著录标准", "text", preset="GB/T 7714", default_weight=2,
            hint="填写标准号，系统做基础著录要素检查"),
    RuleDef("ref_citation_style", "ref", "正文引用标注", "select",
            options=["bracket（[1]）", "superscript（上标）", "none（不检查）"],
            preset="bracket（[1]）", default_weight=2),
    RuleDef("ref_recent_ratio", "ref", "近五年文献占比下限", "number", unit="%", preset="30", default_weight=3),
    RuleDef("ref_size_pt", "ref", "参考文献字号", "number", unit="pt", preset="10.5",
            default_weight=2, hint="五号 = 10.5pt"),

    # ---------- 排版细节 ----------
    RuleDef("header_text", "misc", "页眉文字", "text",
            preset="西南科技大学本科生毕业论文（设计）", default_weight=2,
            hint="模板要求页眉为五号华文行楷；留空则不检查"),
    RuleDef("cn_en_space", "misc", "中英文之间须留空格", "checkbox", preset="0", default_weight=2,
            hint="学校模板未作要求，默认关闭；如需检查可改为「要求」"),
    RuleDef("no_multi_space", "misc", "禁止连续多余空格", "checkbox", preset="1", default_weight=2),
    RuleDef("no_trailing_punct_title", "misc", "标题末尾不加标点", "checkbox", preset="1", default_weight=1),
]


def get_rule(key: str) -> Optional[RuleDef]:
    """按键查找规则定义。

    Args:
        key: 规则键。

    Returns:
        规则定义对象，不存在时返回 None。
    """
    for item in RULES:
        if item.key == key:
            return item
    return None


def grouped_rules() -> Dict[str, List[RuleDef]]:
    """按分组返回规则定义。

    Returns:
        {分组键: [规则定义, ...]}，顺序与 CATEGORIES 一致。
    """
    result: Dict[str, List[RuleDef]] = {key: [] for key in CATEGORIES}
    for item in RULES:
        result.setdefault(item.category, []).append(item)
    return result
