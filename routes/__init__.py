"""Web 路由包：认证、教师端、学生端蓝图。"""
from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    """注册全部蓝图。

    Args:
        app: Flask 应用实例。
    """
    from .auth import bp as auth_bp
    from .student import bp as student_bp
    from .teacher import bp as teacher_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(teacher_bp, url_prefix='/teacher')
    app.register_blueprint(student_bp, url_prefix='/student')
