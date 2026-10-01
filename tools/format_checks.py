"""格式检查项实现：每条规则对应一个检查函数，返回 0.0~1.0 的通过率并收集问题。

约定：函数签名 `func(doc, expected, findings) -> float`。
findings 元素为 (级别, 位置, 问题描述, 修改建议)。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from tools.docx_parser import DocInfo, ParaInfo

Finding = Tuple[str, str, str, str]
MAX_FINDINGS_PER_RULE = 6

_FONT_ALIASES: Dict[str, List[str]] = {
    "宋体": ["宋体", "songti", "simsun", "nsimsun", "新宋体"],
    "黑体": ["黑体", "heiti", "simhei"],
    "楷体": ["楷体", "kaiti", "stkaiti", "kaiti_gb2312"],
    "仿宋": ["仿宋", "fangsong", "stfangsong"],
    "times new roman": ["times new roman", "timesnewroman", "times"],
    "arial": ["arial"],
}


def _mode(exp: str) -> str:
    """从选项值中提取英文键（去掉中文括号说明）。"""
    return (exp or "").split("（")[0].strip().lower()


def _to_float(value) -> Optional[float]:
    """安全转换为浮点数，失败返回 None。"""
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _font_match(actual: Optional[str], expected: str) -> bool:
    """判断字体名是否匹配（支持中英文别名）。"""
    if not actual or not expected:
        return False
    a, e = actual.strip().lower(), expected.strip().lower()
    if a == e:
        return True
    for canon, aliases in _FONT_ALIASES.items():
        if e == canon or e in aliases:
            return a == canon or a in aliases
    return a in e or e in a


def ratio_score(bad: int, total: int, tolerance: float = 0.05) -> float:
    """按违规比例计算通过率。

    Args:
        bad: 违规数量。
        total: 检查总数。
        tolerance: 可忽略的违规比例。

    Returns:
        0.0 ~ 1.0 的通过率。
    """
    if total <= 0:
        return 1.0
    ratio = bad / total
    if ratio <= tolerance:
        return 1.0
    return round(max(0.0, 1.0 - ratio), 3)


def _loc(para: ParaInfo) -> str:
    """生成段落位置描述。"""
    return f"第 {para.index + 1} 段"


def _cn_paragraphs(doc: DocInfo, min_len: int = 10) -> List[ParaInfo]:
    """取长度达标的正文段落。

    排除：封面/声明/摘要/目录等前置部分、标题、图表题注、参考文献之后的段落。
    """
    start = doc.body_start_index or 0
    end = doc.ref_heading_index if doc.ref_heading_index is not None else None
    caption_index = {int(c["index"]) for c in doc.captions}
    return [
        p for p in doc.body_paragraphs
        if p.index >= start and len(p.text.strip()) >= min_len
        and p.index not in caption_index
        and not (end is not None and p.index > int(end))
    ]


def _headings(doc: DocInfo, level: Optional[int] = None) -> List[ParaInfo]:
    """取标题段落，可指定层级。"""
    items = [p for p in doc.paragraphs if p.is_heading]
    return [p for p in items if p.level == level] if level else items


def chk_page_size(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查纸张大小。"""
    if not exp:
        return 1.0
    width, height = doc.page.get("width_cm"), doc.page.get("height_cm")
    expect = {"a4": (21.0, 29.7), "a3": (29.7, 42.0)}.get(_mode(exp))
    if not expect or not width or not height:
        return 1.0
    ok = abs(width - expect[0]) <= 0.6 and abs(height - expect[1]) <= 0.6
    if not ok:
        out.append(("error", "页面设置", f"纸张为 {width}cm × {height}cm，与要求 {exp} 不符",
                    f"在「布局 → 纸张大小」中设为 {exp}（{expect[0]}cm × {expect[1]}cm）"))
    return 1.0 if ok else 0.0


def _make_margin_check(field_name: str, label: str) -> Callable[[DocInfo, str, List[Finding]], float]:
    """生成页边距检查函数。"""

    def _inner(doc: DocInfo, exp: str, out: List[Finding]) -> float:
        target, actual = _to_float(exp), doc.page.get(field_name)
        if target is None or actual is None:
            return 1.0
        diff = abs(actual - target)
        if diff <= 0.2:
            return 1.0
        out.append(("error" if diff > 0.5 else "warning", "页面设置",
                    f"{label}为 {actual}cm，要求 {target}cm",
                    f"在「布局 → 页边距」中将{label}改为 {target}cm"))
        return round(max(0.0, 1.0 - diff / 2.0), 3)

    return _inner


def chk_page_number(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查是否插入页码。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    if doc.has_page_number:
        return 1.0
    out.append(("error", "页面设置", "未检测到页脚页码", "在「插入 → 页码」中为正添加页码"))
    return 0.0


def chk_body_font_cn(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文中文字体。"""
    if not exp:
        return 1.0
    paras = [p for p in _cn_paragraphs(doc) if re.search(r"[一-龥]", p.text)]
    bad = [p for p in paras if not _font_match(p.font_cn, exp)]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"正文字体为「{p.font_cn or '未设置'}」，要求「{exp}」",
                    f"将正文段落字体统一为 {exp}"))
    return ratio_score(len(bad), len(paras))


def chk_body_font_en(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文西文字体。"""
    if not exp:
        return 1.0
    paras = [p for p in _cn_paragraphs(doc) if re.search(r"[A-Za-z]{3,}", p.text)]
    bad = [p for p in paras if not _font_match(p.font_en, exp)]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"西文字体为「{p.font_en or '未设置'}」，要求「{exp}」",
                    f"将西文字符字体统一为 {exp}"))
    return ratio_score(len(bad), len(paras))


def chk_body_size(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文字号。"""
    target = _to_float(exp)
    if target is None:
        return 1.0
    paras = [p for p in _cn_paragraphs(doc) if p.size_pt]
    bad = [p for p in paras if abs((p.size_pt or 0) - target) > 0.6]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"正文字号为 {p.size_pt}pt，要求 {target}pt",
                    f"将正文统一为 {target}pt（小四=12pt，四号=14pt）"))
    return ratio_score(len(bad), len(paras))


def chk_line_spacing(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文行距。

    期望值 > 6 时视为「固定值 N 磅」（学校模板为固定值 22 磅），
    否则视为「N 倍行距」。
    """
    target = _to_float(exp)
    if target is None:
        return 1.0
    is_pt = target > 6
    unit = "磅" if is_pt else "倍"
    tolerance = 1.5 if is_pt else 0.15
    paras = [p for p in _cn_paragraphs(doc, 20) if p.line_spacing]
    bad = [p for p in paras if abs((p.line_spacing or 0) - target) > tolerance]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"行距为 {p.line_spacing}，要求固定值 {target}{unit}"
                    if is_pt else f"行距为 {p.line_spacing} 倍，要求 {target} 倍",
                    f"在「段落 → 行距」中设为固定值 {target} 磅"
                    if is_pt else f"设置段落行距为 {target} 倍"))
    return ratio_score(len(bad), len(paras))


def chk_first_indent(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文首行缩进（字符数）。"""
    target = _to_float(exp)
    if target is None:
        return 1.0
    paras = [p for p in _cn_paragraphs(doc, 30) if p.first_indent_chars is not None]
    bad = [p for p in paras if abs((p.first_indent_chars or 0) - target) > 0.6]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"首行缩进约 {p.first_indent_chars} 字符，要求 {target} 字符",
                    f"在「段落 → 特殊格式 → 首行缩进」中设为 {target} 字符"))
    return ratio_score(len(bad), len(paras))


def chk_body_align(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文对齐方式。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    paras = [p for p in _cn_paragraphs(doc, 30) if p.align]
    bad = [p for p in paras if p.align != mode]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("info", _loc(p), f"对齐方式为 {p.align}，要求 {mode}", "统一正文对齐方式"))
    return ratio_score(len(bad), len(paras))


def chk_heading_font_cn(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题中文字体。"""
    if not exp:
        return 1.0
    items = _headings(doc)
    bad = [p for p in items if not _font_match(p.font_cn, exp)]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", f"标题「{p.text.strip()[:20]}」",
                    f"字体为「{p.font_cn or '未设置'}」，要求「{exp}」", f"将标题字体统一为 {exp}"))
    return ratio_score(len(bad), len(items))


def chk_heading_bold(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题是否加粗。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    items = _headings(doc)
    bad = [p for p in items if p.bold is False]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", f"标题「{p.text.strip()[:20]}」", "标题未加粗", "对标题应用加粗格式"))
    return ratio_score(len(bad), len(items))


def _make_heading_size_check(level: int) -> Callable[[DocInfo, str, List[Finding]], float]:
    """生成指定层级标题的字号检查函数。"""

    def _inner(doc: DocInfo, exp: str, out: List[Finding]) -> float:
        target = _to_float(exp)
        if target is None:
            return 1.0
        items = [p for p in _headings(doc, level) if p.size_pt]
        bad = [p for p in items if abs((p.size_pt or 0) - target) > 1.0]
        for p in bad[:MAX_FINDINGS_PER_RULE]:
            out.append(("warning", f"{level} 级标题「{p.text.strip()[:20]}」",
                        f"字号为 {p.size_pt}pt，要求 {target}pt",
                        f"统一 {level} 级标题字号为 {target}pt"))
        return ratio_score(len(bad), len(items))

    return _inner


def chk_heading_number_style(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题编号体系（阿拉伯分级 / 中文分级）。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    # 章标题兼容「第1章 / 第一章 / 1」三种写法
    arabic = {1: r"^\s*(?:第\s*[0-9一二三四五六七八九十百]+\s*[章节篇][\s、.]*|\d+(?![.\d]))",
              2: r"^\s*\d+\.\d+(?!\.\d)",
              3: r"^\s*\d+\.\d+\.\d+(?!\.\d)", 4: r"^\s*\d+\.\d+\.\d+\.\d+"}
    chinese = {1: r"^\s*第[一二三四五六七八九十百]+[章节篇]", 2: r"^\s*[（(][一二三四五六七八九十]+[)）]",
               3: r"^\s*\d+[.．、]", 4: r"^\s*[（(]\d+[)）]"}
    table = arabic if mode == "arabic" else chinese if mode == "chinese" else None
    if table is None:
        return 1.0
    # 摘要、结论、致谢、参考文献、附录等特殊章按学校模板不编号，跳过检查
    no_number = re.compile(r"^\s*(摘\s*要|ABSTRACT|Abstract|目\s*录|结\s*论|致\s*谢|参考文献|附\s*录|引\s*言)")
    items = [p for p in _headings(doc)
             if p.level in table and not no_number.match(p.text.strip())]
    bad = [p for p in items if not re.match(table[p.level or 1], p.text.strip())]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", f"{p.level} 级标题「{p.text.strip()[:24]}」",
                    "标题编号不符合所选编号体系", f"按「{exp}」统一编号，可用多级列表自动生成"))
    return ratio_score(len(bad), len(items), 0.1)


def chk_heading1_align(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查一级（章）标题对齐方式（学校模板要求居中）。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    items = [p for p in _headings(doc, 1) if p.align]
    bad = [p for p in items if p.align != mode]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", f"章标题「{p.text.strip()[:20]}」",
                    f"对齐方式为 {p.align}，要求 {mode}", "将章标题设为居中对齐"))
    return ratio_score(len(bad), len(items), 0.15)


def chk_heading_align(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查二、三级标题对齐方式。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    items = [p for p in _headings(doc) if p.align]
    bad = [p for p in items if p.align != mode]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("info", f"标题「{p.text.strip()[:20]}」", f"对齐方式为 {p.align}，要求 {mode}",
                    "统一标题对齐方式"))
    return ratio_score(len(bad), len(items), 0.15)


def chk_heading_use_style(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题是否使用样式（避免手动加粗的伪标题）。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    real = [p for p in doc.paragraphs if p.is_heading]
    pseudo = [p for p in doc.paragraphs if p.looks_like_heading]
    if not real and not pseudo:
        out.append(("error", "全文", "未识别到任何标题，无法生成目录",
                    "使用 Word 内置「标题 1/2/3」样式标记章节"))
        return 0.0
    for p in pseudo[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"「{p.text.strip()[:24]}」疑似手动加粗的伪标题",
                    "改为应用「标题 N」样式，便于自动生成目录"))
    return ratio_score(len(pseudo), len(real) + len(pseudo), 0.05)


def chk_required_sections(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查必需章节是否齐全。"""
    names = [x.strip() for x in re.split(r"[,，;；]", exp) if x.strip()]
    if not names:
        return 1.0
    # 标题常含间隔空格（如「目  录」「结  论」），比较前统一去掉空白
    heading_text = " ".join(p.text for p in doc.paragraphs if p.is_heading).replace(" ", "")
    missing = []
    for name in names:
        key = name.replace(" ", "")
        if key and key in heading_text:
            continue
        if any(p.text.strip().replace(" ", "").startswith(key) and len(p.text.strip()) <= 20
               for p in doc.paragraphs):
            continue
        missing.append(name)
    for name in missing[:MAX_FINDINGS_PER_RULE]:
        out.append(("error", "全文结构", f"缺少「{name}」", f"补充「{name}」并使用标题样式标记"))
    return round(max(0.0, 1.0 - len(missing) / len(names)), 3) if names else 1.0


def chk_min_total_words(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文总字数下限。"""
    target, actual = _to_float(exp), float(doc.stats.get("chars_cn", 0))
    if not target:
        return 1.0
    if actual >= target:
        return 1.0
    out.append(("error", "全文", f"正文中文字符约 {int(actual)} 字，低于要求 {int(target)} 字",
                "补充研究内容与论证篇幅"))
    return round(max(0.0, actual / target), 3)


def chk_abstract_word_min(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查摘要字数下限。"""
    target = _to_float(exp)
    if not target:
        return 1.0
    actual = len(re.findall(r"[一-龥]", doc.abstract_cn))
    if not doc.abstract_cn:
        out.append(("error", "摘要", "未识别到中文摘要", "添加「摘要」标题及摘要正文"))
        return 0.0
    if actual >= target:
        return 1.0
    out.append(("warning", "摘要", f"摘要约 {actual} 字，少于要求 {int(target)} 字",
                "补充研究目的、方法、结果与创新点"))
    return round(max(0.0, actual / target), 3)


def chk_abstract_word_max(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查摘要字数上限。"""
    target = _to_float(exp)
    actual = len(re.findall(r"[一-龥]", doc.abstract_cn))
    if not target or not actual:
        return 1.0
    if actual <= target:
        return 1.0
    out.append(("warning", "摘要", f"摘要约 {actual} 字，超出上限 {int(target)} 字", "精简摘要内容"))
    return round(max(0.0, target / actual), 3)


def chk_keyword_count(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查关键词个数。"""
    target, actual = _to_float(exp), len(doc.keywords)
    if not target:
        return 1.0
    if not actual:
        out.append(("error", "关键词", "未识别到关键词", "在摘要后添加「关键词：」并列出 3-5 个"))
        return 0.0
    if abs(actual - target) <= 1:
        return 1.0
    out.append(("warning", "关键词", f"关键词 {actual} 个，要求约 {int(target)} 个",
                f"调整关键词数量为 {int(target)} 个左右"))
    return round(max(0.0, 1.0 - abs(actual - target) / max(target, 1.0)), 3)


def chk_english_abstract(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查英文摘要。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    if len(re.findall(r"[A-Za-z]+", doc.abstract_en)) >= 30:
        return 1.0
    out.append(("error", "英文摘要", "未识别到英文摘要（Abstract）",
                "补充与中文摘要对应的英文摘要与英文关键词"))
    return 0.0


def chk_toc_required(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查是否存在目录。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    if doc.toc.get("has_entries") or doc.toc.get("has_field"):
        return 1.0
    out.append(("error", "目录", "未检测到目录", "在正文前插入自动生成的目录"))
    return 0.0


def chk_toc_auto(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查目录是否为自动生成。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    if doc.toc.get("has_field"):
        return 1.0
    if doc.toc.get("has_entries"):
        out.append(("warning", "目录", "目录项含页码但可能非自动生成",
                    "使用「引用 → 目录 → 自动目录」重新生成"))
        return 0.5
    return 1.0


def chk_toc_max_level(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题层级深度上限。"""
    target, max_level = _to_float(exp), float(doc.toc.get("max_level") or 0)
    if not target or not max_level:
        return 1.0
    if max_level <= target:
        return 1.0
    out.append(("warning", "目录", f"标题层级最深 {int(max_level)} 级，超过要求 {int(target)} 级",
                f"合并或降级第 {int(target) + 1} 级及以下的标题"))
    return round(max(0.0, 1.0 - (max_level - target) / 3.0), 3)


def _body_item_pos(doc: DocInfo, kind: str, index: int) -> Optional[int]:
    """查询段落/表格在正文元素序列中的位置。"""
    for pos, (item_kind, item_index) in enumerate(doc.body_items):
        if item_kind == kind and item_index == index:
            return pos
    return None


def _item_has_image(doc: DocInfo, pos: int) -> bool:
    """判断指定位置的正文元素是否含图片。"""
    if pos < 0 or pos >= len(doc.body_items):
        return False
    kind, index = doc.body_items[pos]
    return kind == "p" and 0 <= index < len(doc.paragraphs) and doc.paragraphs[index].has_image


def _item_is_table(doc: DocInfo, pos: int) -> bool:
    """判断指定位置的正文元素是否为表格。"""
    return 0 <= pos < len(doc.body_items) and doc.body_items[pos][0] == "tbl"


def chk_figure_caption_position(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查图题位置（常规要求位于图下方）。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    figures = [c for c in doc.captions if c["kind"] == "图"]
    bad = 0
    for cap in figures:
        pos = _body_item_pos(doc, "p", int(cap["index"]))
        if pos is None:
            continue
        before = _item_has_image(doc, pos) or _item_has_image(doc, pos - 1)
        after = _item_has_image(doc, pos + 1)
        if not before and not after:
            continue
        if not (before if mode == "below" else after):
            bad += 1
            if bad <= MAX_FINDINGS_PER_RULE:
                out.append(("warning", f"图题「{str(cap['text'])[:24]}」", "图题位置与要求不符",
                            f"将图题放在图的{'下方' if mode == 'below' else '上方'}"))
    return ratio_score(bad, len(figures), 0.0)


def chk_table_caption_position(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查表题位置（常规要求位于表上方）。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    tables = [c for c in doc.captions if c["kind"] == "表"]
    bad = 0
    for cap in tables:
        pos = _body_item_pos(doc, "p", int(cap["index"]))
        if pos is None:
            continue
        before = _item_is_table(doc, pos - 1)
        after = _item_is_table(doc, pos + 1) or _item_is_table(doc, pos + 2)
        if not before and not after:
            continue
        if not (after if mode == "above" else before):
            bad += 1
            if bad <= MAX_FINDINGS_PER_RULE:
                out.append(("warning", f"表题「{str(cap['text'])[:24]}」", "表题位置与要求不符",
                            f"将表题放在表的{'上方' if mode == 'above' else '下方'}"))
    return ratio_score(bad, len(tables), 0.0)


def chk_caption_numbering(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查图表编号方式与重复编号。"""
    mode = _mode(exp)
    if mode in ("", "none") or not doc.captions:
        return 1.0
    want_chapter = mode == "chapter"
    pattern = r"^[0-9]+[-—－.．][0-9]+$" if want_chapter else r"^[0-9]+$"
    bad = 0
    for cap in doc.captions:
        if not re.match(pattern, str(cap["number"])):
            bad += 1
            if bad <= MAX_FINDINGS_PER_RULE:
                out.append(("warning", f"题注「{str(cap['text'])[:24]}」",
                            f"编号不符合{'按章编号（图1-1）' if want_chapter else '全文连续（图1）'}",
                            "用「引用 → 插入题注」自动生成统一编号"))
    score = ratio_score(bad, len(doc.captions), 0.05)
    numbers = [str(c["number"]) for c in doc.captions]
    duplicates = {n for n in numbers if numbers.count(n) > 1}
    if duplicates:
        out.append(("error", "图表编号", f"存在重复编号：{'、'.join(sorted(duplicates)[:6])}",
                    "重新生成题注编号，确保唯一且连续"))
        score = round(min(score, 0.6), 3)
    return score


def chk_caption_size(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查图表题注字号（学校模板为五号 10.5pt）。"""
    target = _to_float(exp)
    if target is None or not doc.captions:
        return 1.0
    bad = 0
    for cap in doc.captions:
        idx = int(cap["index"])
        if not (0 <= idx < len(doc.paragraphs)):
            continue
        size = doc.paragraphs[idx].size_pt
        if size and abs(size - target) > 0.6:
            bad += 1
            if bad <= MAX_FINDINGS_PER_RULE:
                out.append(("warning", f"题注「{str(cap['text'])[:24]}」",
                            f"字号为 {size}pt，要求 {target}pt",
                            f"将图表题注统一为 {target}pt（五号）"))
    return ratio_score(bad, len(doc.captions), 0.1)


def chk_ref_min_count(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查参考文献数量下限。"""
    target, actual = _to_float(exp), float(len(doc.references))
    if not target or actual >= target:
        return 1.0
    out.append(("error", "参考文献", f"参考文献 {int(actual)} 条，少于要求 {int(target)} 条",
                "补充近三年相关文献，注意中英文比例"))
    return round(max(0.0, actual / target), 3)


def chk_ref_standard(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查参考文献著录要素完整性。"""
    if not exp:
        return 1.0
    items = doc.references
    if not items:
        out.append(("error", "参考文献", "未识别到参考文献列表", "在文末添加「参考文献」标题及条目"))
        return 0.0
    bad = 0
    for item in items:
        has_year = bool(re.search(r"(19|20)\d{2}", item))
        has_author = bool(re.match(r"^\s*(\[[0-9]+\]\s*)?[一-龥A-Za-z]", item))
        if not (has_year and has_author and len(item) >= 15):
            bad += 1
            if bad <= MAX_FINDINGS_PER_RULE:
                out.append(("warning", "参考文献", f"条目「{item[:36]}…」著录要素不完整",
                            f"按 {exp} 补全作者、题名、出版项与年份"))
    return ratio_score(bad, len(items), 0.1)


def chk_ref_citation_style(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查正文引用标注与文献表对应关系。"""
    mode = _mode(exp)
    if mode in ("", "none"):
        return 1.0
    if mode == "superscript":
        return 1.0 if doc.references else 0.0
    cites = [int(x) for x in re.findall(r"\[(\d{1,3})\]", doc.full_text)]
    if not cites:
        out.append(("error", "正文引用", "正文未发现 [n] 形式的引用标注",
                    "在引用处使用 [1] 标注，并与文献表顺序对应"))
        return 0.0
    score = 1.0
    if doc.references and max(cites) > len(doc.references):
        out.append(("error", "正文引用",
                    f"正文引用最大编号 [{max(cites)}] 超过文献条数 {len(doc.references)}",
                    "核对引用编号，确保与参考文献表一一对应"))
        score = 0.5
    missing = [i for i in range(1, len(doc.references) + 1) if i not in set(cites)]
    if doc.references and len(missing) > max(2, len(doc.references) // 3):
        out.append(("warning", "正文引用", f"有 {len(missing)} 条文献未在正文中被引用",
                    "删除未引用文献，或在正文中补充引用"))
        score = round(min(score, 0.7), 3)
    return score


def chk_ref_recent_ratio(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查近五年文献占比。"""
    target = _to_float(exp)
    if not target:
        return 1.0
    years = [int(m.group(0)) for m in re.finditer(r"(?:19|20)\d{2}", "\n".join(doc.references))]
    if not years:
        return 1.0
    recent = len([y for y in years if y >= datetime.now().year - 5])
    actual = recent / len(years) * 100
    if actual >= target:
        return 1.0
    out.append(("warning", "参考文献", f"近五年文献占比约 {actual:.0f}%，低于要求 {int(target)}%",
                "补充近五年（含当年）的期刊与会议文献"))
    return round(max(0.0, actual / target), 3)


def chk_ref_size(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查参考文献条目字号（学校模板为五号 10.5pt）。"""
    target = _to_float(exp)
    if target is None or doc.ref_heading_index is None:
        return 1.0
    items = [p for p in doc.paragraphs
             if p.index > int(doc.ref_heading_index) and p.text.strip() and p.size_pt][:80]
    if not items:
        return 1.0
    bad = [p for p in items if abs((p.size_pt or 0) - target) > 0.6]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("warning", _loc(p), f"参考文献字号为 {p.size_pt}pt，要求 {target}pt",
                    f"将参考文献条目统一为 {target}pt（五号）"))
    return ratio_score(len(bad), len(items), 0.1)


def chk_header_text(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查页眉文字是否符合学校要求。"""
    if not exp:
        return 1.0
    if not doc.headers:
        out.append(("error", "页眉", "未检测到页眉",
                    f"在「插入 → 页眉」中添加页眉：{exp}"))
        return 0.0
    joined = "".join(doc.headers).replace(" ", "").replace("\u3000", "")
    if exp.replace(" ", "") in joined:
        return 1.0
    out.append(("warning", "页眉", f"页眉文字为「{''.join(doc.headers)[:30]}」，要求「{exp}」",
                f"将页眉统一改为：{exp}"))
    return 0.5


def chk_cn_en_space(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查中英文之间是否留空格。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    pattern = re.compile(r"[一-龥][A-Za-z0-9]|[A-Za-z0-9][一-龥]")
    total = 0
    for para in _cn_paragraphs(doc, 20):
        hits = pattern.findall(para.text)
        total += len(hits)
        if hits and total <= MAX_FINDINGS_PER_RULE * 3:
            out.append(("info", _loc(para), f"存在 {len(hits)} 处中英文之间缺少空格",
                        "在中文与英文/数字之间添加一个半角空格"))
    per_thousand = total / max(1.0, doc.stats.get("total_chars", 1) / 1000.0)
    return 1.0 if per_thousand <= 1.0 else round(max(0.0, 1.0 - per_thousand / 15.0), 3)


def chk_no_multi_space(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查是否存在多余连续空格。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    bad = [p for p in doc.paragraphs if re.search(r"\S\s{2,}\S", p.text)]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("info", _loc(p), "存在连续多余空格", "删除多余空格或用首行缩进替代"))
    return ratio_score(len(bad), max(1, doc.stats.get("paragraphs", 1)), 0.02)


def chk_no_trailing_punct_title(doc: DocInfo, exp: str, out: List[Finding]) -> float:
    """检查标题末尾是否带标点。"""
    if _mode(exp) not in ("1", "true", "yes", "on"):
        return 1.0
    items = _headings(doc)
    bad = [p for p in items if p.text.strip() and p.text.strip()[-1] in "。；;，,：:、！!？?"]
    for p in bad[:MAX_FINDINGS_PER_RULE]:
        out.append(("info", f"标题「{p.text.strip()[:24]}」", "标题末尾带有标点符号",
                    "删除标题末尾标点"))
    return ratio_score(len(bad), len(items), 0.05)


CHECKS: Dict[str, Callable[[DocInfo, str, List[Finding]], float]] = {
    "page_size": chk_page_size,
    "margin_top": _make_margin_check("top_cm", "上页边距"),
    "margin_bottom": _make_margin_check("bottom_cm", "下页边距"),
    "margin_left": _make_margin_check("left_cm", "左页边距"),
    "margin_right": _make_margin_check("right_cm", "右页边距"),
    "page_number_required": chk_page_number,
    "body_font_cn": chk_body_font_cn,
    "body_font_en": chk_body_font_en,
    "body_size_pt": chk_body_size,
    "line_spacing": chk_line_spacing,
    "first_line_indent": chk_first_indent,
    "body_align": chk_body_align,
    "heading_font_cn": chk_heading_font_cn,
    "heading_bold": chk_heading_bold,
    "heading1_size_pt": _make_heading_size_check(1),
    "heading2_size_pt": _make_heading_size_check(2),
    "heading3_size_pt": _make_heading_size_check(3),
    "heading_number_style": chk_heading_number_style,
    "heading1_align": chk_heading1_align,
    "heading_align": chk_heading_align,
    "heading_use_style": chk_heading_use_style,
    "required_sections": chk_required_sections,
    "min_total_words": chk_min_total_words,
    "abstract_word_min": chk_abstract_word_min,
    "abstract_word_max": chk_abstract_word_max,
    "keyword_count": chk_keyword_count,
    "require_english_abstract": chk_english_abstract,
    "toc_required": chk_toc_required,
    "toc_auto": chk_toc_auto,
    "toc_max_level": chk_toc_max_level,
    "figure_caption_position": chk_figure_caption_position,
    "table_caption_position": chk_table_caption_position,
    "caption_numbering": chk_caption_numbering,
    "caption_size_pt": chk_caption_size,
    "ref_min_count": chk_ref_min_count,
    "ref_standard": chk_ref_standard,
    "ref_citation_style": chk_ref_citation_style,
    "ref_recent_ratio": chk_ref_recent_ratio,
    "ref_size_pt": chk_ref_size,
    "header_text": chk_header_text,
    "cn_en_space": chk_cn_en_space,
    "no_multi_space": chk_no_multi_space,
    "no_trailing_punct_title": chk_no_trailing_punct_title,
}
