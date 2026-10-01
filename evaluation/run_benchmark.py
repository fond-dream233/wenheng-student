"""Run reproducible quality and performance benchmarks for cross-stage comparison."""
from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Keep benchmark runtime logs, generated secrets and database paths out of the project.
_RUNTIME = Path(tempfile.gettempdir()) / "aic-cross-stage-benchmark"
os.environ.setdefault("OUTPUT_DIR", str(_RUNTIME / "outputs"))
os.environ.setdefault("DB_PATH", str(_RUNTIME / "outputs" / "db" / "benchmark.db"))
os.environ.setdefault("UPLOAD_DIR", str(_RUNTIME / "outputs" / "papers"))
os.environ.setdefault("REPORT_DIR", str(_RUNTIME / "outputs" / "reports"))
os.environ.setdefault("RESULT_DIR", str(_RUNTIME / "outputs" / "results"))
os.environ.setdefault("LOG_DIR", str(_RUNTIME / "logs"))

from competition.stage_comparison import compare_stage_documents
from evaluation.dataset import ROOT, generate_dataset

LABELS = ("low", "medium", "high")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 2)


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = compare_stage_documents([
            ("proposal", case["proposal"], "proposal.docx"),
            ("final", case["final"], "final.docx"),
        ])
        report = result["report"]
        comparison = report["comparisons"][0]
        return {
            "caseId": case["caseId"],
            "expectedRisk": case["expectedRisk"],
            "predictedRisk": report["riskLevel"],
            "driftScore": report["overallDriftScore"],
            "topicSimilarity": comparison["metrics"]["topicSimilarity"],
            "objectiveSimilarity": comparison["metrics"]["objectiveSimilarity"],
            "outlineSimilarity": comparison["metrics"]["outlineSimilarity"],
            "keywordRetention": comparison["metrics"]["keywordRetention"],
            "findingCount": len(report["findings"]),
            "success": True,
            "error": "",
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "groundTruthReason": case["groundTruthReason"],
        }
    except Exception as exc:  # benchmark records failures instead of hiding them
        return {
            "caseId": case["caseId"],
            "expectedRisk": case["expectedRisk"],
            "predictedRisk": "error",
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "groundTruthReason": case["groundTruthReason"],
        }


def _run_level(cases: list[dict[str, Any]], concurrency: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    if concurrency == 1:
        results = [_evaluate_case(case) for case in cases]
    else:
        results = []
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(_evaluate_case, case): case["caseId"] for case in cases}
            for future in as_completed(futures):
                results.append(future.result())
        results.sort(key=lambda item: item["caseId"])
    wall_seconds = time.perf_counter() - started
    durations = [float(item["durationMs"]) for item in results]
    successes = sum(bool(item["success"]) for item in results)
    return results, {
        "concurrency": concurrency,
        "runs": len(results),
        "successes": successes,
        "successRate": _safe_div(successes, len(results)),
        "latencyMeanMs": round(statistics.fmean(durations), 2),
        "latencyP50Ms": _percentile(durations, 0.50),
        "latencyP95Ms": _percentile(durations, 0.95),
        "wallTimeSeconds": round(wall_seconds, 3),
        "throughputCasesPerSecond": round(len(results) / wall_seconds, 2) if wall_seconds else 0.0,
    }


def _quality_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    matrix = {expected: {predicted: 0 for predicted in LABELS} for expected in LABELS}
    correct = 0
    for item in records:
        predicted = item["predictedRisk"]
        if predicted in LABELS:
            matrix[item["expectedRisk"]][predicted] += 1
        correct += int(item["expectedRisk"] == predicted)

    by_class: dict[str, Any] = {}
    for label in LABELS:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[other][label] for other in LABELS if other != label)
        false_negative = sum(matrix[label][other] for other in LABELS if other != label)
        precision = _safe_div(true_positive, true_positive + false_positive)
        recall = _safe_div(true_positive, true_positive + false_negative)
        by_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": _safe_div(2 * precision * recall, precision + recall),
            "support": sum(matrix[label].values()),
        }

    expected_positive = [item["expectedRisk"] != "low" for item in records]
    predicted_positive = [item["predictedRisk"] in {"medium", "high"} for item in records]
    tp = sum(expected and predicted for expected, predicted in zip(expected_positive, predicted_positive))
    fp = sum(not expected and predicted for expected, predicted in zip(expected_positive, predicted_positive))
    tn = sum(not expected and not predicted for expected, predicted in zip(expected_positive, predicted_positive))
    fn = sum(expected and not predicted for expected, predicted in zip(expected_positive, predicted_positive))
    return {
        "cases": len(records),
        "accuracy": _safe_div(correct, len(records)),
        "macroPrecision": round(statistics.fmean(value["precision"] for value in by_class.values()), 4),
        "macroRecall": round(statistics.fmean(value["recall"] for value in by_class.values()), 4),
        "macroF1": round(statistics.fmean(value["f1"] for value in by_class.values()), 4),
        "binaryDrift": {
            "precision": _safe_div(tp, tp + fp),
            "recall": _safe_div(tp, tp + fn),
            "falsePositiveRate": _safe_div(fp, fp + tn),
            "truePositive": tp,
            "falsePositive": fp,
            "trueNegative": tn,
            "falseNegative": fn,
        },
        "byClass": by_class,
        "confusionMatrix": matrix,
        "predictedDistribution": dict(Counter(item["predictedRisk"] for item in records)),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_report(path: Path, report: dict[str, Any]) -> None:
    quality = report["quality"]
    binary = quality["binaryDrift"]
    lines = [
        "# 跨阶段对比评测报告",
        "",
        f"- 样本：{quality['cases']} 组匿名合成开题—终稿案例，低/中/高各 10 组。",
        f"- 三分类准确率：{quality['accuracy']:.1%}",
        f"- Macro F1：{quality['macroF1']:.1%}",
        f"- 漂移检出召回率：{binary['recall']:.1%}",
        f"- 漂移误报率：{binary['falsePositiveRate']:.1%}",
        "",
        "## 性能",
        "",
        "| 并发 | 成功率 | P50 (ms) | P95 (ms) | 吞吐量 (组/秒) |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["performance"]:
        lines.append(
            f"| {item['concurrency']} | {item['successRate']:.1%} | "
            f"{item['latencyP50Ms']:.2f} | {item['latencyP95Ms']:.2f} | "
            f"{item['throughputCasesPerSecond']:.2f} |"
        )
    lines.extend([
        "",
        "## 限制",
        "",
        "该版本使用确定性生成的匿名合成案例，适合回归、阈值校准和性能复现。",
        "标签由预设变换规则给出，尚未经过独立教师双人盲审，因此不能作为真实场景泛化结论。",
        "性能为本机核心算法（含 DOCX 解析）结果，不包含赛事平台网络、ADP、mTLS 或排队开销。",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_benchmark(output_dir: Path, generated_dir: Path, concurrency_levels: list[int]) -> dict[str, Any]:
    cases = generate_dataset(generated_dir)
    # Warm up imports, XML parsing and caches; the warm-up is not included in reported timing.
    _evaluate_case(cases[0])
    performance = []
    baseline_records: list[dict[str, Any]] = []
    for concurrency in concurrency_levels:
        records, timing = _run_level(cases, concurrency)
        performance.append(timing)
        if not baseline_records:
            baseline_records = records
    report = {
        "schemaVersion": "1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "type": "deterministic-synthetic",
            "caseCount": len(cases),
            "labelDistribution": dict(Counter(case["expectedRisk"] for case in cases)),
            "containsPersonalData": False,
            "independentHumanReview": False,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "quality": _quality_metrics(baseline_records),
        "performance": performance,
        "cases": baseline_records,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_csv(output_dir / "cases.csv", baseline_records, [
        "caseId", "expectedRisk", "predictedRisk", "driftScore", "topicSimilarity",
        "objectiveSimilarity", "outlineSimilarity", "keywordRetention", "findingCount",
        "success", "durationMs", "groundTruthReason", "error",
    ])
    _write_csv(output_dir / "performance.csv", performance, [
        "concurrency", "runs", "successes", "successRate", "latencyMeanMs",
        "latencyP50Ms", "latencyP95Ms", "wallTimeSeconds", "throughputCasesPerSecond",
    ])
    _write_report(output_dir / "report.md", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark cross-stage drift detection")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--generated-dir", type=Path, default=ROOT / "generated")
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4])
    args = parser.parse_args()
    if any(level < 1 or level > 32 for level in args.concurrency):
        parser.error("并发数必须在 1 到 32 之间")
    report = run_benchmark(args.output_dir, args.generated_dir, args.concurrency)
    print(json.dumps({"quality": report["quality"], "performance": report["performance"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
