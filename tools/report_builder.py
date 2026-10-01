"""报告生成模块：将分析结果渲染为独立 HTML 报告并保存 JSON 结果。"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from config.settings import Config
from tools.logger import get_logger
from tools.models import AnalysisResult

logger = get_logger('report')


def result_to_dict(result: AnalysisResult) -> Dict:
    """将分析结果转换为可序列化的字典。

    Args:
        result: 分析结果对象。

    Returns:
        可 JSON 序列化的字典。
    """
    return asdict(result)


class ReportBuilder:
    """分析报告构建器：输出 HTML 报告与 JSON 数据。"""

    def __init__(self, template_dir: Path, report_dir: Path, result_dir: Path) -> None:
        """初始化报告构建器。

        Args:
            template_dir: Jinja2 模板目录。
            report_dir: HTML 报告输出目录。
            result_dir: JSON 结果输出目录。
        """
        self.template_dir = Path(template_dir)
        self.report_dir = Path(report_dir)
        self.result_dir = Path(result_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(['html', 'xml']),
        )

    def build(self, result: AnalysisResult, school_name: str) -> Tuple[str, str]:
        """生成报告文件。

        Args:
            result: 分析结果。
            school_name: 学校名称（报告页眉使用）。

        Returns:
            (HTML 报告路径, JSON 结果路径)。

        Raises:
            OSError: 文件写入失败。
        """
        json_path = self.result_dir / f"report_{result.paper_id}.json"
        html_path = self.report_dir / f"report_{result.paper_id}.html"

        payload = result_to_dict(result)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding='utf-8')

        template = self.env.get_template('report.html')
        html = template.render(result=result, school_name=school_name)
        html_path.write_text(html, encoding='utf-8')
        logger.info('报告已生成：%s', html_path)
        return str(html_path), str(json_path)


def default_builder() -> ReportBuilder:
    """使用默认配置创建报告构建器。

    Returns:
        ReportBuilder 实例。
    """
    return ReportBuilder(
        template_dir=Config.BASE_DIR / 'templates',
        report_dir=Config.REPORT_DIR,
        result_dir=Config.RESULT_DIR,
    )
