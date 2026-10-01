"""论文格式专家引擎：按教师配置的规范逐项检查并汇总格式分（0-100）。"""
from __future__ import annotations

from typing import Dict, List

from tools.docx_parser import DocInfo
from tools.format_checks import CHECKS, Finding, MAX_FINDINGS_PER_RULE
from tools.models import FormatReport, Issue, RuleResult


class FormatExpert:
    """论文格式专家：执行全部启用的格式检查项。"""

    def __init__(self, rules: Dict[str, Dict]) -> None:
        """初始化格式专家。

        Args:
            rules: 规则配置，键为规则 key，值含 enabled/expected/weight/title/category。
        """
        self.rules = rules or {}

    def check(self, doc: DocInfo) -> FormatReport:
        """执行格式检查。

        Args:
            doc: 论文结构化信息。

        Returns:
            FormatReport；未启用任何规则时 score 为 None。
        """
        report = FormatReport()
        for key, func in CHECKS.items():
            cfg = self.rules.get(key)
            if not cfg:
                continue
            expected = str(cfg.get("expected") or "").strip()
            item = RuleResult(
                key=key,
                title=str(cfg.get("title") or key),
                category=str(cfg.get("category") or "misc"),
                weight=float(cfg.get("weight") or 0),
                enabled=bool(cfg.get("enabled")),
                configured=expected != "",
                pass_ratio=1.0,
                expected=expected,
            )
            if not (item.enabled and expected):
                report.items.append(item)
                continue
            findings: List[Finding] = []
            item.pass_ratio = self._run(func, doc, expected, findings)
            item.issues = [
                Issue(level=lv, rule_key=key, rule_title=item.title,
                      location=loc, message=msg, suggestion=sug)
                for lv, loc, msg, sug in findings[:MAX_FINDINGS_PER_RULE]
            ]
            report.issues.extend(item.issues)
            report.items.append(item)
        self._summarize(report)
        return report

    @staticmethod
    def _run(func, doc: DocInfo, expected: str, findings: List[Finding]) -> float:
        """安全执行单个检查函数。"""
        try:
            return round(float(func(doc, expected, findings)), 3)
        except Exception as exc:  # noqa: BLE001 - 单条规则异常不影响整体
            findings.append(("info", "检查项", f"该检查项执行异常：{exc}",
                             "请联系管理员检查该规则的配置值"))
            return 1.0

    @staticmethod
    def _summarize(report: FormatReport) -> None:
        """汇总加权得分。"""
        active = [i for i in report.items if i.enabled and i.configured]
        report.configured_count = len(active)
        report.total_weight = round(sum(i.weight for i in active), 2)
        report.earned_weight = round(sum(i.earned for i in active), 2)
        if report.total_weight > 0:
            report.score = round(
                max(0.0, min(100.0, report.earned_weight / report.total_weight * 100)), 1
            )
