"""分析编排模块：解析论文 → 格式专家 → 逻辑专家 → 报告落盘 → 入库。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from config.settings import Config
from tools.database import Database, now_str
from tools.docx_parser import parse_docx
from tools.format_expert import FormatExpert
from tools.logger import get_logger
from tools.logic_expert import LogicExpert
from tools.models import AnalysisResult
from tools.report_builder import ReportBuilder, default_builder
from tools.scorer import combine, grade, summarize

logger = get_logger('analyzer')


class Analyzer:
    """论文分析编排器：串联解析、双专家分析与结果持久化。"""

    def __init__(self, db: Database, builder: Optional[ReportBuilder] = None) -> None:
        """初始化分析器。

        Args:
            db: 数据库客户端。
            builder: 报告构建器，缺省时使用默认配置。
        """
        self.db = db
        self.builder = builder or default_builder()

    def run(self, paper_id: int) -> AnalysisResult:
        """执行论文分析。

        Args:
            paper_id: 论文记录 id。

        Returns:
            AnalysisResult 分析结果。

        Raises:
            ValueError: 论文记录不存在。
            RuntimeError: 解析或分析失败。
        """
        row = self.db.get(
            "SELECT p.*, u.name AS student_name, u.student_no, u.class_name"
            " FROM papers p JOIN users u ON u.id = p.student_id"
            " WHERE p.id = ?",
            (paper_id,),
        )
        if not row:
            raise ValueError(f"论文记录不存在：{paper_id}")

        try:
            doc = parse_docx(row['stored_path'])
        except Exception as exc:
            self._mark_failed(paper_id, str(exc))
            raise RuntimeError(f"论文解析失败：{exc}") from exc

        title = self._guess_title(doc)
        self.db.execute(
            "UPDATE papers SET title = ?, status = 'analyzed', error_msg = '' WHERE id = ?",
            (title, paper_id),
        )

        rules = self.db.get_rules()
        if Config.COMPETITION_MODE and 'header_text' in rules:
            rules['header_text'] = {**rules['header_text'], 'enabled': False, 'expected': ''}
        format_report = FormatExpert(rules).check(doc)
        logic_report = LogicExpert().analyze(doc)

        format_score = format_report.score
        logic_score = logic_report.score
        total_score = combine(format_score, logic_score,
                              Config.FORMAT_WEIGHT, Config.LOGIC_WEIGHT)

        result = AnalysisResult(
            paper_id=paper_id,
            student_name=row['student_name'] or row['student_no'] or '',
            paper_title=title,
            format_report=format_report,
            logic_report=logic_report,
            format_score=format_score,
            logic_score=logic_score,
            total_score=total_score,
            grade=grade(total_score),
            summary=summarize(format_score, logic_score,
                              logic_report.ai_likelihood, total_score),
            stats=dict(doc.stats),
        )

        html_path, json_path = self.builder.build(result, Config.DISPLAY_ORGANIZATION_NAME)
        issue_count = len(format_report.issues) + len(logic_report.findings)
        self.db.execute(
            "INSERT INTO reports (paper_id, student_id, version, format_score, logic_score,"
            " total_score, ai_likelihood, issue_count, result_json, report_path, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (paper_id, row['student_id'], row['version'], format_score, logic_score,
             total_score, logic_report.ai_likelihood, issue_count, json_path,
             html_path, now_str()),
        )
        logger.info('论文 %s 分析完成：格式 %.1f，逻辑 %.1f，总分 %s',
                    paper_id, format_score or 0.0, logic_score, total_score)
        return result

    @staticmethod
    def _guess_title(doc) -> str:
        """推测论文标题：首个一级标题，或首个非空段落。"""
        for para in doc.paragraphs:
            if para.is_heading and (para.level or 9) <= 2 and para.text.strip():
                return para.text.strip()[:120]
        for para in doc.paragraphs[:30]:
            text = para.text.strip()
            if 6 <= len(text) <= 80:
                return text[:120]
        return '未命名论文'

    def _mark_failed(self, paper_id: int, message: str) -> None:
        """标记论文分析失败并记录原因。"""
        self.db.execute(
            "UPDATE papers SET status = 'failed', error_msg = ? WHERE id = ?",
            (message[:500], paper_id),
        )
        logger.error('论文 %s 分析失败：%s', paper_id, message)
