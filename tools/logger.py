"""日志模块：统一日志出口，按日期分割输出到 logs/ 目录。"""
from __future__ import annotations

import logging
from datetime import date
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Dict

from config.settings import Config

_LOGGERS: Dict[str, logging.Logger] = {}
_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"


def get_logger(name: str = "app") -> logging.Logger:
    """获取（或创建）指定名称的日志器。

    日志按天切分写入 logs/app-YYYY-MM-DD.log，同时输出到控制台。

    Args:
        name: 日志器名称，通常使用模块名。

    Returns:
        配置完成的 logging.Logger 对象。
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    Config.ensure_dirs()
    log_dir: Path = Config.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = TimedRotatingFileHandler(
        log_dir / f"{name}-{date.today().isoformat()}.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d.log"
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG if Config.DEBUG else logging.INFO)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    _LOGGERS[name] = logger
    return logger
