from __future__ import annotations

from collections import Counter
from pathlib import Path

from evaluation.dataset import generate_dataset, load_cases
from evaluation.run_benchmark import _quality_metrics, _run_level


def test_manifest_is_balanced_and_unique():
    cases = load_cases()
    assert len(cases) == 30
    assert len({case["caseId"] for case in cases}) == 30
    assert Counter(case["expectedRisk"] for case in cases) == {
        "low": 10,
        "medium": 10,
        "high": 10,
    }
    assert all(case["sourceTopic"] and case["targetTopic"] for case in cases)


def test_generated_case_runs_and_metrics_are_bounded(tmp_path: Path):
    generated = generate_dataset(tmp_path / "dataset")[:3]
    records, performance = _run_level(generated, concurrency=1)
    quality = _quality_metrics(records)
    assert len(records) == 3
    assert performance["successRate"] == 1.0
    assert performance["latencyP95Ms"] >= performance["latencyP50Ms"] > 0
    assert 0 <= quality["accuracy"] <= 1
    assert 0 <= quality["macroF1"] <= 1
