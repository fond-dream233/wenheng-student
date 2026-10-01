"""零依赖、可解释的知识库检索：为检查结论提供可引用的规范条文。

采用 BM25 对中文二元词与拉丁词打分，结果确定、可复现，不需要外部向量服务或
API 密钥。语料按阶段（proposal/midterm/final/common）与类别（structure/
format/logic/integrity）标注，下游检查据此附上「依据」，避免凭空给结论。
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

CORPUS_PATH = Path(__file__).with_name("knowledge_corpus.json")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[a-z][a-z0-9_-]{1,}")


def tokenize(text: str) -> Counter[str]:
    """返回可解释的中文二元词与拉丁词频次。"""
    compact = re.sub(r"\s+", "", text.lower())
    chinese = "".join(_CJK_RE.findall(compact))
    tokens = Counter(
        chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))
    )
    tokens.update(_LATIN_RE.findall(compact))
    return tokens


class KnowledgeBase:
    """轻量检索索引：BM25 打分 + 阶段/类别过滤。"""

    def __init__(self, entries: list[dict[str, Any]]) -> None:
        self.entries = entries
        self._index = [
            tokenize(" ".join(filter(None, [e.get("title", ""), e.get("clause", ""), " ".join(e.get("tags", []))])))
            for e in entries
        ]
        self._lengths = [sum(index.values()) or 1 for index in self._index]
        self._avg_len = sum(self._lengths) / len(self._lengths) if self._lengths else 1.0
        self._idf = self._build_idf()

    @classmethod
    def load(cls, path: Path | str = CORPUS_PATH) -> "KnowledgeBase":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = raw.get("entries", [])
        if not entries:
            raise ValueError(f"知识库语料为空：{path}")
        return cls(entries)

    def _build_idf(self) -> dict[str, float]:
        doc_count = len(self._index)
        containing: Counter[str] = Counter()
        for tokens in self._index:
            containing.update(tokens.keys())
        return {
            term: math.log((doc_count - count + 0.5) / (count + 0.5) + 1.0)
            for term, count in containing.items()
        }

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        stage: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """按相关度返回前 k 条，可用 stage 或 category 过滤。"""
        query_tokens = tokenize(query)
        scored: list[tuple[float, int]] = []
        for position, doc_tokens in enumerate(self._index):
            entry = self.entries[position]
            if stage is not None:
                entry_stage = entry.get("stage", "common")
                if stage == "common":
                    if entry_stage != "common":
                        continue
                elif entry_stage not in (stage, "common"):
                    continue
            if category is not None and entry.get("category") != category:
                continue
            scored.append((self._bm25(query_tokens, doc_tokens, self._lengths[position]), position))
        scored.sort(key=lambda item: (-item[0], item[1]))
        results: list[dict[str, Any]] = []
        for score, position in scored[:k]:
            if score <= 0:
                continue
            entry = self.entries[position]
            results.append({**entry, "score": round(score, 4)})
        return results

    def cite(self, query: str, *, k: int = 3, **filters: Any) -> list[dict[str, Any]]:
        """返回可作为结论依据的条文，去掉打分噪声，只留可读字段。"""
        return [
            {
                "id": item["id"],
                "title": item["title"],
                "clause": item["clause"],
                "stage": item["stage"],
                "category": item["category"],
            }
            for item in self.search(query, k=k, **filters)
        ]

    def _bm25(self, query_tokens: Counter[str], doc_tokens: Counter[str], doc_len: int) -> float:
        k1, b = 1.5, 0.75
        score = 0.0
        for term, query_freq in query_tokens.items():
            if term not in doc_tokens:
                continue
            tf = doc_tokens[term]
            denominator = tf + k1 * (1.0 - b + b * doc_len / self._avg_len)
            score += self._idf[term] * (tf * (k1 + 1.0) / denominator) * query_freq
        return score


def available_stages(entries: Iterable[dict[str, Any]]) -> set[str]:
    """返回语料中出现的全部阶段标签，供调用方构建过滤选项。"""
    return {entry.get("stage", "common") for entry in entries}


_default: KnowledgeBase | None = None


def default_kb() -> KnowledgeBase:
    """返回进程内缓存的默认知识库实例。"""
    global _default
    if _default is None:
        _default = KnowledgeBase.load()
    return _default


def cite_for(
    text: str,
    *,
    stage: str | None = None,
    category: str | None = None,
    k: int = 1,
) -> dict[str, Any] | None:
    """返回与 text 最相关的一条规范条文，找不到则为 None。"""
    items = default_kb().cite(text, k=k, stage=stage, category=category)
    return items[0] if items else None
