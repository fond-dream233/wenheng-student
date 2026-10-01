"""逻辑分析基础资源（二）：文本切分与统计特征计算。"""
from __future__ import annotations

import re
from typing import List, Sequence

_SENT_SPLIT = re.compile(r'(?<=[。！？；!?;])')
_PARA_SPLIT = re.compile(r'[\r\n]+')
_CN_CHAR = re.compile(r'[一-龥]')


def split_sentences(text: str) -> List[str]:
    """按句末标点切分句子。

    Args:
        text: 输入文本。

    Returns:
        非空句子列表。
    """
    parts = _SENT_SPLIT.split(text or '')
    return [s.strip() for s in parts if s and s.strip()]


def split_paragraphs(text: str, min_len: int = 20) -> List[str]:
    """按换行切分段落并过滤过短段落。

    Args:
        text: 输入文本。
        min_len: 段落最小长度。

    Returns:
        段落文本列表。
    """
    parts = _PARA_SPLIT.split(text or '')
    return [p.strip() for p in parts if p and len(p.strip()) >= min_len]


def cn_len(text: str) -> int:
    """统计中文字符数。"""
    return len(_CN_CHAR.findall(text or ''))


def coefficient_of_variation(values: Sequence[float]) -> float:
    """计算变异系数（标准差 / 均值）。

    Args:
        values: 数值序列。

    Returns:
        变异系数；样本不足或均值为 0 时返回 0.0。
    """
    data = [v for v in values if v > 0]
    if len(data) < 2:
        return 0.0
    mean = sum(data) / len(data)
    if mean <= 0:
        return 0.0
    var = sum((v - mean) ** 2 for v in data) / len(data)
    return round((var ** 0.5) / mean, 4)


def ngram_diversity(text: str, n: int = 2) -> float:
    """计算字符 n-gram 多样性（去重数 / 总数）。

    Args:
        text: 输入文本。
        n: n-gram 长度。

    Returns:
        0.0 ~ 1.0 的多样性比值，文本过短返回 1.0。
    """
    clean = re.sub(r'\s+', '', text or '')
    if len(clean) < n + 20:
        return 1.0
    grams = [clean[i:i + n] for i in range(len(clean) - n + 1)]
    if not grams:
        return 1.0
    return round(len(set(grams)) / len(grams), 4)


def count_terms(text: str, terms: Sequence[str]) -> int:
    """统计词表在文本中的命中总次数。"""
    return sum(len(re.findall(re.escape(t), text or '')) for t in terms)


def count_patterns(text: str, patterns: Sequence[str]) -> int:
    """统计正则模式在文本中的命中总次数。"""
    total = 0
    for pattern in patterns:
        try:
            total += len(re.findall(pattern, text or ''))
        except re.error:
            continue
    return total


def prefix_repeat_rate(sentences: Sequence[str], n: int = 4) -> float:
    """统计句首 n 字重复率（模板化写作信号）。

    Args:
        sentences: 句子列表。
        n: 句首字符数。

    Returns:
        0.0 ~ 1.0 的重复率。
    """
    heads = [s[:n] for s in sentences if len(s) >= n]
    if len(heads) < 10:
        return 0.0
    return round(1.0 - len(set(heads)) / len(heads), 4)


def jaccard(a: str, b: str, n: int = 2) -> float:
    """计算两段文本的字符 n-gram 杰卡德相似度。

    Args:
        a: 文本一。
        b: 文本二。
        n: n-gram 长度。

    Returns:
        0.0 ~ 1.0 的相似度。
    """
    ga = {a[i:i + n] for i in range(len(a) - n + 1)} if len(a) >= n else set()
    gb = {b[i:i + n] for i in range(len(b) - n + 1)} if len(b) >= n else set()
    if not ga or not gb:
        return 0.0
    return round(len(ga & gb) / len(ga | gb), 4)


def find_duplicate_paragraphs(paragraphs: Sequence[str], threshold: float = 0.7) -> List[List[int]]:
    """查找高度相似的段落对。

    Args:
        paragraphs: 段落列表。
        threshold: 相似度阈值。

    Returns:
        相似段落下标对的列表。
    """
    pairs: List[List[int]] = []
    for i in range(len(paragraphs)):
        for j in range(i + 1, len(paragraphs)):
            if jaccard(paragraphs[i], paragraphs[j]) >= threshold:
                pairs.append([i, j])
                if len(pairs) >= 10:
                    return pairs
    return pairs
