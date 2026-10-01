"""通用校验函数：账号、口令、文本长度等。"""
from __future__ import annotations

import re
from typing import Optional, Tuple

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")


def check_username(value: str) -> Tuple[bool, str]:
    """校验用户名合法性。

    Args:
        value: 待校验用户名。

    Returns:
        (是否合法, 提示信息)。
    """
    value = (value or "").strip()
    if not value:
        return False, "账号不能为空"
    if not _USERNAME_RE.match(value):
        return False, "账号需为 3-32 位字母、数字、下划线、点或连字符"
    return True, ""


def check_password(value: str, min_len: int = 6) -> Tuple[bool, str]:
    """校验口令强度（仅做最小长度约束）。

    Args:
        value: 明文口令。
        min_len: 最小长度。

    Returns:
        (是否合法, 提示信息)。
    """
    value = value or ""
    if len(value) < min_len:
        return False, f"口令至少 {min_len} 位"
    return True, ""


def to_int(value, default: Optional[int] = None) -> Optional[int]:
    """将输入安全转换为整数。

    Args:
        value: 任意输入。
        default: 转换失败时的返回值。

    Returns:
        整数或 default。
    """
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def to_float(value, default: Optional[float] = None) -> Optional[float]:
    """将输入安全转换为浮点数。

    Args:
        value: 任意输入。
        default: 转换失败时的返回值。

    Returns:
        浮点数或 default。
    """
    try:
        if value is None or value == "":
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
