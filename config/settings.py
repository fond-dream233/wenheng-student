"""全局配置模块。

所有配置项均从环境变量读取，业务代码中禁止硬编码配置。
环境变量未设置时，非敏感项使用内置默认值，敏感项（密钥、初始密码）按策略生成。
"""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Set


def _env(key: str, default: str = "") -> str:
    """读取环境变量，值为空时返回默认值。

    Args:
        key: 环境变量名。
        default: 缺省值。

    Returns:
        环境变量值或缺省值。
    """
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    """读取整型环境变量。

    Args:
        key: 环境变量名。
        default: 解析失败或缺省时的返回值。

    Returns:
        整型配置值。
    """
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    """读取布尔型环境变量（true/1/yes/on 视为真）。

    Args:
        key: 环境变量名。
        default: 缺省值。

    Returns:
        布尔配置值。
    """
    raw = _env(key, "")
    if raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Config:
    """系统配置对象（所有字段均为类属性，运行期只读）。"""

    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # ---------- Flask ----------
    SECRET_KEY: str = _env("APP_SECRET_KEY", "")
    DEBUG: bool = _env_bool("APP_DEBUG", False)
    HOST: str = _env("APP_HOST", "127.0.0.1")
    PORT: int = _env_int("APP_PORT", 5000)
    SESSION_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", False)
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_env_int("SESSION_LIFETIME_HOURS", 8))
    MAX_FORM_MEMORY_SIZE: int = _env_int("MAX_FORM_MEMORY_SIZE", 1024 * 1024)
    MAX_FORM_PARTS: int = _env_int("MAX_FORM_PARTS", 200)
    _trusted_hosts_raw: str = _env("TRUSTED_HOSTS", "")
    TRUSTED_HOSTS = [x.strip() for x in _trusted_hosts_raw.split(",") if x.strip()] or None

    # ---------- 展示 ----------
    COMPETITION_MODE: bool = _env_bool("COMPETITION_MODE", False)
    SCHOOL_NAME: str = _env("SCHOOL_NAME", "西南科技大学")
    DISPLAY_ORGANIZATION_NAME: str = _env(
        "PUBLIC_ORGANIZATION_NAME", "参赛作品" if COMPETITION_MODE else SCHOOL_NAME
    )
    SYSTEM_NAME: str = _env(
        "SYSTEM_NAME", "文衡·多智能体论文质检平台" if COMPETITION_MODE else "本科毕业论文检查系统"
    )

    # ---------- 路径 ----------
    OUTPUT_DIR: Path = Path(_env("OUTPUT_DIR", str(BASE_DIR / "outputs")))
    DB_PATH: Path = Path(_env("DB_PATH", str(OUTPUT_DIR / "db" / "thesis.db")))
    UPLOAD_DIR: Path = Path(_env("UPLOAD_DIR", str(OUTPUT_DIR / "papers")))
    REPORT_DIR: Path = Path(_env("REPORT_DIR", str(OUTPUT_DIR / "reports")))
    RESULT_DIR: Path = Path(_env("RESULT_DIR", str(OUTPUT_DIR / "results")))
    LOG_DIR: Path = Path(_env("LOG_DIR", str(BASE_DIR / "logs")))

    # ---------- 上传 ----------
    MAX_UPLOAD_MB: int = _env_int("MAX_UPLOAD_MB", 30)
    ALLOWED_EXT: Set[str] = {".docx"}

    # ---------- 初始教师账号 ----------
    DEFAULT_TEACHER_USERNAME: str = _env("DEFAULT_TEACHER_USERNAME", "teacher")
    DEFAULT_TEACHER_PASSWORD_FROM_ENV: bool = bool(os.getenv("DEFAULT_TEACHER_PASSWORD"))
    DEFAULT_TEACHER_PASSWORD: str = _env(
        "DEFAULT_TEACHER_PASSWORD", secrets.token_urlsafe(18)
    )
    DEFAULT_TEACHER_NAME: str = _env("DEFAULT_TEACHER_NAME", "管理员")

    # ---------- 评分权重 ----------
    FORMAT_WEIGHT: float = float(_env("FORMAT_WEIGHT", "0.5"))
    LOGIC_WEIGHT: float = float(_env("LOGIC_WEIGHT", "0.5"))

    _initialized: bool = False

    @classmethod
    def validate_security(cls) -> None:
        """Fail closed for unsafe credentials in competition mode."""
        unsafe = {"swust@2026", "change-me-please", "replace-with-a-strong-password"}
        if cls.COMPETITION_MODE and (
            not cls.DEFAULT_TEACHER_PASSWORD_FROM_ENV
            or cls.DEFAULT_TEACHER_PASSWORD in unsafe
            or len(cls.DEFAULT_TEACHER_PASSWORD) < 12
        ):
            raise RuntimeError(
                "竞赛模式必须通过 DEFAULT_TEACHER_PASSWORD 设置至少 12 位的非默认管理员口令"
            )

    @classmethod
    def ensure_dirs(cls) -> None:
        """创建运行期所需目录，并初始化密钥。

        Raises:
            OSError: 目录创建失败。
        """
        if cls._initialized:
            return
        for path in (
            cls.OUTPUT_DIR,
            cls.DB_PATH.parent,
            cls.UPLOAD_DIR,
            cls.REPORT_DIR,
            cls.RESULT_DIR,
            cls.LOG_DIR,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not cls.SECRET_KEY:
            cls.SECRET_KEY = cls._load_or_create_secret()
        cls._initialized = True

    @staticmethod
    def _load_or_create_secret() -> str:
        """从 outputs/db/secret.key 读取或生成并持久化 Flask 密钥。

        Returns:
            可用的密钥字符串。
        """
        key_file = Config.DB_PATH.parent / "secret.key"
        try:
            if key_file.exists():
                content = key_file.read_text(encoding="utf-8").strip()
                if content:
                    return content
        except OSError:
            pass
        value = secrets.token_hex(32)
        try:
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_text(value, encoding="utf-8")
        except OSError:
            pass
        return value
