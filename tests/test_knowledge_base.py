"""知识库检索层的行为测试。"""
from __future__ import annotations

import pytest

from tools.knowledge_base import KnowledgeBase, tokenize


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


def test_corpus_loads(kb: KnowledgeBase) -> None:
    assert len(kb.entries) >= 20
    stages = {entry["stage"] for entry in kb.entries}
    assert {"common", "proposal", "midterm", "final"} <= stages


def test_tokenize_is_deterministic() -> None:
    first = tokenize("开题报告应明确研究目标与技术路线")
    second = tokenize("开题报告应明确研究目标与技术路线")
    assert first == second
    assert "研究" in first and "目标" in first


def test_search_returns_relevant_top_hit(kb: KnowledgeBase) -> None:
    results = kb.search("开题报告 研究目标 技术路线", k=3)
    assert results
    assert results[0]["stage"] == "proposal"


def test_stage_filter(kb: KnowledgeBase) -> None:
    results = kb.search("研究现状 进度 成果", k=10, stage="midterm")
    assert results
    assert all(item["stage"] in {"midterm", "common"} for item in results)


def test_category_filter(kb: KnowledgeBase) -> None:
    results = kb.search("参考文献 引用 出处", k=10, category="integrity")
    assert results
    assert all(item["category"] == "integrity" for item in results)


def test_cite_omits_score(kb: KnowledgeBase) -> None:
    cited = kb.cite("摘要 关键词 结论", k=2)
    assert cited
    assert all("score" not in item for item in cited)
    assert all({"id", "title", "clause", "stage", "category"} <= set(item) for item in cited)


def test_empty_query_returns_empty(kb: KnowledgeBase) -> None:
    assert kb.search("", k=5) == []
