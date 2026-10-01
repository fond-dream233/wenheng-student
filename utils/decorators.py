"""访问控制装饰器：登录校验与角色校验。"""
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from flask import abort, redirect, session, url_for


def login_required(role: Optional[str] = None) -> Callable:
    """要求登录（可指定角色）。

    Args:
        role: 允许的角色（teacher / student），None 表示任意已登录用户。

    Returns:
        视图函数装饰器。
    """

    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get('user_id'):
                return redirect(url_for('auth.login'))
            if role and session.get('role') != role:
                abort(403)
            return view(*args, **kwargs)

        return wrapper

    return decorator
