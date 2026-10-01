"""认证蓝图：登录、退出与首页跳转。"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from tools.logger import get_logger
from extensions import limiter
from utils.decorators import login_required
from utils.security import verify_password

logger = get_logger('auth')

bp = Blueprint('auth', __name__)


def get_db():
    """获取当前应用的数据库客户端。"""
    from flask import current_app
    return current_app.extensions['db']


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def login():
    """登录页：校验账号口令并写入会话。"""
    if session.get('user_id'):
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        row = get_db().get('SELECT * FROM users WHERE username = ?', (username,))
        if not row or not verify_password(row['password_hash'], password):
            flash('账号或密码错误', 'danger')
            logger.warning('登录失败：%s', username)
            return render_template('login.html', username=username)
        if not row['active']:
            flash('账号已被停用，请联系指导教师', 'danger')
            return render_template('login.html', username=username)

        session.clear()
        session['user_id'] = row['id']
        session['username'] = row['username']
        session['role'] = row['role']
        session['name'] = row['name'] or row['username']
        session.permanent = True
        logger.info('用户 %s（%s）登录成功', username, row['role'])
        return redirect(url_for('auth.index'))

    return render_template('login.html', username='')


@bp.route('/logout', methods=['POST'])
@login_required()
def logout():
    """退出登录并清理会话。"""
    session.clear()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))


@bp.route('/')
@login_required()
def index():
    """按角色跳转到对应首页。"""
    if session.get('role') == 'teacher':
        return redirect(url_for('teacher.dashboard'))
    return redirect(url_for('student.index'))
