"""Flask 应用入口：创建应用、注入数据库依赖并注册蓝图。"""
from __future__ import annotations

from flask import Flask, jsonify

from config.settings import Config
from extensions import csrf, limiter
from tools.database import Database
from tools.logger import get_logger

logger = get_logger('app')


def create_app() -> Flask:
    """创建并配置 Flask 应用。

    Returns:
        配置完成的 Flask 应用实例。
    """
    Config.ensure_dirs()
    Config.validate_security()
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.update(
        SECRET_KEY=Config.SECRET_KEY,
        MAX_CONTENT_LENGTH=Config.MAX_UPLOAD_MB * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=Config.MAX_FORM_MEMORY_SIZE,
        MAX_FORM_PARTS=Config.MAX_FORM_PARTS,
        SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=Config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=Config.SESSION_COOKIE_SAMESITE,
        PERMANENT_SESSION_LIFETIME=Config.PERMANENT_SESSION_LIFETIME,
        TRUSTED_HOSTS=Config.TRUSTED_HOSTS,
    )
    csrf.init_app(app)
    limiter.init_app(app)

    db = Database(Config.DB_PATH)
    db.init()
    app.extensions['db'] = db

    @app.context_processor
    def inject_globals() -> dict:
        """向模板注入全局展示变量。"""
        return {
            'school_name': Config.DISPLAY_ORGANIZATION_NAME,
            'system_name': Config.SYSTEM_NAME,
            'competition_mode': Config.COMPETITION_MODE,
        }

    from routes import register_blueprints
    register_blueprints(app)

    @app.get('/health')
    @limiter.exempt
    def health():
        return jsonify(status='ok', service='thesis-review-web')

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; "
            "font-src 'self' https://cdn.jsdelivr.net; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'self'; form-action 'self'",
        )
        return response

    logger.info('%s %s 启动完成', Config.DISPLAY_ORGANIZATION_NAME, Config.SYSTEM_NAME)
    return app


app = create_app()


if __name__ == '__main__':
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
