"""安全相关工具：口令散列、随机账号口令生成、文件名清洗。

依赖 Werkzeug 提供的 PBKDF2 口令散列实现。
"""
from __future__ import annotations

import random
import re
import string
import zipfile
from pathlib import Path
from typing import Tuple

from werkzeug.security import check_password_hash, generate_password_hash

_UNSAFE_CHARS = re.compile(r"[^\w.\-一-龥]+")
# 口令生成时排除易混淆字符 0/O/1/l/I
_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)


def hash_password(raw: str) -> str:
    """生成口令散列值。

    Args:
        raw: 明文口令。

    Returns:
        口令散列字符串。

    Raises:
        ValueError: 明文口令为空。
    """
    if not raw:
        raise ValueError("口令不能为空")
    return generate_password_hash(raw)


def verify_password(password_hash: str, raw: str) -> bool:
    """校验明文口令是否匹配散列值。

    Args:
        password_hash: 数据库中保存的散列。
        raw: 用户输入的明文口令。

    Returns:
        匹配返回 True，否则 False。
    """
    if not password_hash or not raw:
        return False
    try:
        return check_password_hash(password_hash, raw)
    except Exception:  # noqa: BLE001 - 散列格式异常一律视为校验失败
        return False


def random_password(length: int = 10) -> str:
    """生成随机初始口令。

    Args:
        length: 口令长度，默认 10。

    Returns:
        随机口令字符串。
    """
    rng = random.SystemRandom()
    return "".join(rng.choice(_PASSWORD_ALPHABET) for _ in range(length))


def suggest_username(student_no: str, name: str) -> str:
    """根据学号与姓名生成建议账号。

    Args:
        student_no: 学号。
        name: 学生姓名。

    Returns:
        建议的用户名（优先学号，缺失时退回姓名拼音位/随机串）。
    """
    base = (student_no or "").strip()
    if not base:
        base = (name or "").strip()
    if not base:
        base = "stu" + "".join(random.choice(string.digits) for _ in range(6))
    return base


def safe_filename(filename: str) -> str:
    """清洗上传文件名，保留中英文、数字、下划线、点、连字符。

    Args:
        filename: 原始文件名。

    Returns:
        安全的文件名；清洗后为空时返回 upload.docx。
    """
    name = Path(filename or "").name
    cleaned = _UNSAFE_CHARS.sub("_", name).strip("._")
    return cleaned or "upload.docx"


def ensure_ext(filename: str, allowed: set) -> Tuple[bool, str]:
    """校验文件扩展名是否允许。

    Args:
        filename: 文件名。
        allowed: 允许的扩展名集合（含点，小写）。

    Returns:
        (是否允许, 小写扩展名)。
    """
    ext = Path(filename or "").suffix.lower()
    return ext in allowed, ext


def validate_docx_stream(stream) -> Tuple[bool, str]:
    """Validate that an upload is structurally a DOCX package, then rewind it."""
    try:
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            names = set(archive.namelist())
            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                return False, "文件不是有效的 DOCX 文档"
            if len(names) > 10000:
                return False, "DOCX 内部文件数量异常"
        return True, ""
    except (OSError, zipfile.BadZipFile):
        return False, "文件不是有效的 DOCX 文档"
    finally:
        try:
            stream.seek(0)
        except (AttributeError, OSError):
            pass
