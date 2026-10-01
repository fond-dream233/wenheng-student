"""分析结果数据模型：格式问题、规则结果、格式/逻辑报告。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Issue:
    """单个问题（格式或逻辑）。"""

    level: str          # error / warning / info
    rule_key: str
    rule_title: str
    location: str
    message: str
    suggestion: str


@dataclass
class RuleResult:
    """单条格式规则的检查结果。"""

    key: str
    title: str
    category: str
    weight: float
    enabled: bool
    configured: bool
    pass_ratio: float
    expected: str = ""
    issues: List[Issue] = field(default_factory=list)

    @property
    def earned(self) -> float:
        """本规则获得的加权分。"""
        return round(self.weight * self.pass_ratio, 2)

    @property
    def status(self) -> str:
        """规则状态：skipped / passed / partial / failed。"""
        if not (self.enabled and self.configured):
            return "skipped"
        if self.pass_ratio >= 0.999:
            return "passed"
        if self.pass_ratio <= 0.001:
            return "failed"
        return "partial"


@dataclass
class FormatReport:
    """格式检查报告。"""

    items: List[RuleResult] = field(default_factory=list)
    issues: List[Issue] = field(default_factory=list)
    score: Optional[float] = None      # None 表示尚未配置规范
    total_weight: float = 0.0
    earned_weight: float = 0.0
    configured_count: int = 0

    @property
    def error_count(self) -> int:
        """严重问题数量。"""
        return len([i for i in self.issues if i.level == "error"])

    @property
    def warning_count(self) -> int:
        """一般问题数量。"""
        return len([i for i in self.issues if i.level == "warning"])

    @property
    def info_count(self) -> int:
        """提示性问题数量。"""
        return len([i for i in self.issues if i.level == "info"])


@dataclass
class LogicFinding:
    """逻辑 / AI 痕迹检测发现项。"""

    key: str
    category: str
    title: str
    level: str                 # error / warning / info
    penalty: float             # 在 100 分尺度上的直接扣分
    detail: str
    suggestion: str
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class LogicReport:
    """逻辑检查报告。"""

    findings: List[LogicFinding] = field(default_factory=list)
    score: float = 0.0
    ai_likelihood: float = 0.0     # 0-100，越高越疑似 AI 生成
    metrics: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """严重问题数量。"""
        return len([f for f in self.findings if f.level == "error"])

    @property
    def warning_count(self) -> int:
        """一般问题数量。"""
        return len([f for f in self.findings if f.level == "warning"])


@dataclass
class AnalysisResult:
    """一次论文分析的完整结果。"""

    paper_id: int = 0
    student_name: str = ""
    paper_title: str = ""
    format_report: Optional[FormatReport] = None
    logic_report: Optional[LogicReport] = None
    format_score: Optional[float] = None
    logic_score: float = 0.0
    total_score: Optional[float] = None
    grade: str = ""
    summary: str = ""
    stats: Dict[str, object] = field(default_factory=dict)
