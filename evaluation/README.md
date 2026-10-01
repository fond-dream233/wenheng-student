# 跨阶段对比评测基线

本目录提供可复现的匿名合成评测集，用于检查跨阶段 Partner 的质量指标和本机性能。

## 数据集

- `cases.json`：30 组案例清单，低、中、高漂移各 10 组。
- `dataset.py`：从固定课题词表生成开题与终稿 DOCX，不使用真实学生信息。
- `generated/`：运行时生成的 60 个 DOCX，已由 `.gitignore` 排除。

标签由明确的构造规则产生：`retained` 保持课题，`partial_shift` 保留部分目标并引入新课题，`replacement` 完全替换课题。它适合自动回归和阈值校准，但尚未经过独立教师双人盲审，不能冒充真实样本上的人工标注结论。

## 运行

```powershell
.\.venv\Scripts\python.exe -m evaluation.run_benchmark
```

输出到 `evaluation/results/`：

- `benchmark.json`：完整环境、质量、性能和逐案例结果；
- `cases.csv`：逐案例标签、预测、漂移分及相似度；
- `performance.csv`：并发 1 与并发 4 的成功率、P50/P95 和吞吐量；
- `report.md`：适合纳入技术报告的摘要。

性能测试包含 DOCX 解析和核心跨阶段算法，但不包含赛事平台网络、ADP、mTLS 或消息排队开销。提交最终材料前，应在目标部署环境重复运行，并补充至少两名教师对真实匿名样本的独立盲审结果。

## 真实样本盲审

`blind_review.py` 提供真实样本的本地匿名化、双教师独立标注、一致性计算和冲突裁决流程。完整操作规范见 [`blind_review/README.md`](blind_review/README.md)。

该流程不会把真实论文、身份映射或教师身份写入仓库，也不会在人工标签锁定前运行算法预测。自动匿名化采用纯文本 DOCX 重建，使用前仍必须由数据协调员逐份人工复核。
