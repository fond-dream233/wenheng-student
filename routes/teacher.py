"""教师端蓝图：班级概览、学生账号管理、提交与报告查看、格式规范配置。"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, send_from_directory, url_for)

from config.settings import Config
from competition.stage_comparison import STAGE_LABELS
from tools.database import Database, now_str
from tools.logger import get_logger
from tools.rules_schema import CATEGORIES, RULES, grouped_rules
from utils.decorators import login_required
from utils.security import hash_password, random_password
from utils.validators import check_password, check_username

logger = get_logger('teacher')

bp = Blueprint('teacher', __name__)


def get_db() -> Database:
    """获取当前应用的数据库客户端。"""
    return current_app.extensions['db']


@bp.route('/')
@login_required('teacher')
def dashboard():
    """教师工作台：班级统计与最近提交。"""
    db = get_db()
    stats = {
        'student_count': db.get("SELECT COUNT(*) AS c FROM users WHERE role='student'")['c'],
        'paper_count': db.get('SELECT COUNT(*) AS c FROM papers')['c'],
        'analyzed_count': db.get("SELECT COUNT(*) AS c FROM papers WHERE status='analyzed'")['c'],
        'avg_total': db.get('SELECT AVG(total_score) AS v FROM reports')['v'],
        'avg_format': db.get('SELECT AVG(format_score) AS v FROM reports')['v'],
        'avg_logic': db.get('SELECT AVG(logic_score) AS v FROM reports')['v'],
        'ai_high': db.get('SELECT COUNT(*) AS c FROM reports WHERE ai_likelihood >= 70')['c'],
        'rule_count': db.get(
            "SELECT COUNT(*) AS c FROM format_rules WHERE enabled=1 AND expected<>''")['c'],
    }
    dist = [0, 0, 0, 0, 0]
    for row in db.query('SELECT total_score FROM reports WHERE total_score IS NOT NULL'):
        dist[min(4, int((row['total_score'] or 0) // 20))] += 1
    recent = db.query(
        'SELECT r.id, r.total_score, r.format_score, r.logic_score, r.ai_likelihood,'
        ' r.created_at, u.name, u.student_no, p.title, p.original_name'
        ' FROM reports r JOIN users u ON u.id = r.student_id'
        ' JOIN papers p ON p.id = r.paper_id ORDER BY r.id DESC LIMIT 12')
    return render_template('teacher_dashboard.html', stats=stats, dist=dist, recent=recent)


@bp.route('/students')
@login_required('teacher')
def students():
    """学生账号列表。"""
    rows = get_db().query(
        'SELECT u.*, (SELECT COUNT(*) FROM papers p WHERE p.student_id = u.id) AS paper_count,'
        ' (SELECT MAX(r.total_score) FROM reports r WHERE r.student_id = u.id) AS best_score'
        " FROM users u WHERE u.role = 'student'"
        ' ORDER BY u.class_name, u.student_no, u.id')
    return render_template('teacher_students.html', students=rows)


@bp.route('/students/create', methods=['POST'])
@login_required('teacher')
def create_student():
    """创建单个学生账号。"""
    db = get_db()
    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()
    name = (request.form.get('name') or '').strip()
    student_no = (request.form.get('student_no') or '').strip()
    class_name = (request.form.get('class_name') or '').strip()

    ok, msg = check_username(username)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('teacher.students'))
    if not password:
        password = random_password()
    ok, msg = check_password(password)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('teacher.students'))
    if db.get('SELECT id FROM users WHERE username = ?', (username,)):
        flash(f'账号 {username} 已存在', 'danger')
        return redirect(url_for('teacher.students'))

    db.execute(
        'INSERT INTO users (username, password_hash, role, name, student_no, class_name, created_at)'
        " VALUES (?, ?, 'student', ?, ?, ?, ?)",
        (username, hash_password(password), name, student_no, class_name, now_str()),
    )
    flash(f'已创建学生账号：{username} / {password}（请告知学生及时修改密码）', 'success')
    logger.info('创建学生账号 %s', username)
    return redirect(url_for('teacher.students'))


@bp.route('/students/batch', methods=['POST'])
@login_required('teacher')
def batch_create_students():
    """批量创建学生账号（每行：学号 姓名）。"""
    db = get_db()
    roster = request.form.get('roster') or ''
    class_name = (request.form.get('class_name') or '').strip()
    created, skipped = [], []
    for line in roster.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r'[\s,，\t]+', line, maxsplit=1)
        student_no = parts[0].strip()
        name = parts[1].strip() if len(parts) > 1 else ''
        username = student_no or f"stu{len(created) + 1:03d}"
        if not student_no or db.get('SELECT id FROM users WHERE username = ?', (username,)):
            skipped.append(username)
            continue
        password = random_password()
        db.execute(
            'INSERT INTO users (username, password_hash, role, name, student_no, class_name, created_at)'
            " VALUES (?, ?, 'student', ?, ?, ?, ?)",
            (username, hash_password(password), name, student_no, class_name, now_str()),
        )
        created.append({'student_no': student_no, 'name': name,
                        'username': username, 'password': password})

    export_path = ''
    if created:
        export_path = Config.RESULT_DIR / (
            'accounts_' + datetime.now().strftime('%Y%m%d%H%M%S') + '.txt')
        export_path.write_text(
            '\n'.join(f"{c['student_no']}\t{c['name']}\t{c['username']}\t{c['password']}"
                      for c in created),
            encoding='utf-8',
        )
        export_path = str(export_path)
    flash(f'批量创建完成：成功 {len(created)} 个，跳过 {len(skipped)} 个', 'success')
    logger.info('批量创建学生账号 %s 个', len(created))

    rows = db.query(
        'SELECT u.*, (SELECT COUNT(*) FROM papers p WHERE p.student_id = u.id) AS paper_count,'
        ' (SELECT MAX(r.total_score) FROM reports r WHERE r.student_id = u.id) AS best_score'
        " FROM users u WHERE u.role = 'student' ORDER BY u.class_name, u.student_no, u.id")
    return render_template('teacher_students.html', students=rows,
                           batch=created, batch_file=export_path)


@bp.route('/students/<int:user_id>/reset', methods=['POST'])
@login_required('teacher')
def reset_password(user_id: int):
    """重置学生密码并返回新密码。"""
    password = (request.form.get('password') or '').strip() or random_password()
    ok, msg = check_password(password)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('teacher.students'))
    get_db().execute('UPDATE users SET password_hash = ? WHERE id = ? AND role = ?',
                     (hash_password(password), user_id, 'student'))
    flash(f'密码已重置为：{password}', 'success')
    logger.info('重置学生 %s 的密码', user_id)
    return redirect(url_for('teacher.students'))


@bp.route('/students/<int:user_id>/toggle', methods=['POST'])
@login_required('teacher')
def toggle_student(user_id: int):
    """启用或停用学生账号。"""
    get_db().execute(
        'UPDATE users SET active = CASE active WHEN 1 THEN 0 ELSE 1 END'
        ' WHERE id = ? AND role = ?', (user_id, 'student'))
    return redirect(url_for('teacher.students'))


@bp.route('/students/<int:user_id>/delete', methods=['POST'])
@login_required('teacher')
def delete_student(user_id: int):
    """删除学生账号及其论文记录。"""
    get_db().execute("DELETE FROM users WHERE id = ? AND role = 'student'", (user_id,))
    flash('学生账号已删除', 'info')
    logger.info('删除学生 %s', user_id)
    return redirect(url_for('teacher.students'))


@bp.route('/accounts/download')
@login_required('teacher')
def download_accounts():
    """下载批量生成的账号文件。"""
    path = request.args.get('file') or ''
    root = Config.RESULT_DIR.resolve()
    try:
        resolved = Path(path).resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError):
        flash('文件不存在', 'danger')
        return redirect(url_for('teacher.students'))
    if not resolved.name.startswith('accounts_') or resolved.suffix.lower() != '.txt':
        abort(403)
    return send_from_directory(root, relative.as_posix(), as_attachment=True,
                               download_name='student_accounts.txt')


@bp.route('/rules')
@login_required('teacher')
def rules():
    """格式规范配置页。"""
    db = get_db()
    cfg = {r['rule_key']: dict(r) for r in db.query('SELECT * FROM format_rules')}
    if Config.COMPETITION_MODE and 'header_text' in cfg:
        cfg['header_text'].update(enabled=0, expected='')
    groups = []
    for key, defs in grouped_rules().items():
        groups.append((CATEGORIES.get(key, key), [(d, cfg.get(d.key)) for d in defs]))
    configured = sum(1 for r in cfg.values() if r['enabled'] and r['expected'])
    return render_template('teacher_rules.html', groups=groups, configured=configured,
                           total=len(cfg))


@bp.route('/rules/save', methods=['POST'])
@login_required('teacher')
def save_rules():
    """保存格式规范配置。"""
    db = get_db()
    for rule in RULES:
        enabled = 1 if request.form.get(f'enabled_{rule.key}') else 0
        expected = (request.form.get(f'expected_{rule.key}') or '').strip()
        weight = request.form.get(f'weight_{rule.key}') or rule.default_weight
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = float(rule.default_weight)
        db.execute(
            'UPDATE format_rules SET enabled = ?, expected = ?, weight = ?, updated_at = ?'
            ' WHERE rule_key = ?',
            (enabled, expected, weight, now_str(), rule.key),
        )
    flash('格式规范已保存，后续分析将按新规范执行', 'success')
    logger.info('格式规范配置已更新')
    return redirect(url_for('teacher.rules'))


@bp.route('/rules/preset', methods=['POST'])
@login_required('teacher')
def load_preset():
    """一键载入通用参考规范。"""
    count = get_db().load_preset_rules()
    template_name = '内置论文格式模板' if Config.COMPETITION_MODE else '西南科技大学 2026 届模板默认规范'
    flash(f'已载入{template_name}（{count} 项），请按实际要求核对', 'warning')
    return redirect(url_for('teacher.rules'))


@bp.route('/rules/clear', methods=['POST'])
@login_required('teacher')
def clear_rules():
    """清空规范配置，等待导入学校官方规范。"""
    get_db().clear_rules()
    flash('已清空全部规范配置', 'info')
    return redirect(url_for('teacher.rules'))


@bp.route('/submissions')
@login_required('teacher')
def submissions():
    """论文提交与报告列表。"""
    rows = get_db().query(
        'SELECT p.*, tp.title AS project_title, u.name, u.student_no, u.class_name,'
        ' r.id AS report_id,'
        ' r.format_score, r.logic_score, r.total_score, r.ai_likelihood'
        ' FROM papers p JOIN users u ON u.id = p.student_id'
        ' LEFT JOIN thesis_projects tp ON tp.id = p.project_id'
        ' LEFT JOIN reports r ON r.paper_id = p.id'
        ' ORDER BY p.id DESC LIMIT 300')
    stage_reports = get_db().query(
        'SELECT sr.id, sr.risk_level, sr.drift_score, sr.created_at,'
        ' tp.title AS project_title, u.name, u.student_no, u.class_name'
        ' FROM stage_reports sr JOIN thesis_projects tp ON tp.id = sr.project_id'
        ' JOIN users u ON u.id = sr.student_id ORDER BY sr.id DESC LIMIT 100'
    )
    return render_template(
        'teacher_submissions.html', submissions=rows, stage_reports=stage_reports,
        stage_labels=STAGE_LABELS,
    )


@bp.route('/report/<int:report_id>')
@login_required('teacher')
def view_report(report_id: int):
    """查看分析报告（返回已生成的 HTML）。"""
    row = get_db().get('SELECT * FROM reports WHERE id = ?', (report_id,))
    if not row or not row['report_path']:
        abort(404)
    path = Path(row['report_path'])
    if not path.exists():
        abort(404)
    return path.read_text(encoding='utf-8')


@bp.route('/report/<int:report_id>/download')
@login_required('teacher')
def download_report(report_id: int):
    """下载分析报告 HTML 文件。"""
    row = get_db().get('SELECT r.*, p.original_name FROM reports r'
                       ' JOIN papers p ON p.id = r.paper_id WHERE r.id = ?', (report_id,))
    if not row or not row['report_path'] or not Path(row['report_path']).exists():
        abort(404)
    return send_file(row['report_path'], as_attachment=True,
                     download_name=f"论文检查报告_{report_id}.html")


@bp.route('/stage-report/<int:report_id>')
@login_required('teacher')
def view_stage_report(report_id: int):
    """View any student's cross-stage report."""
    row = get_db().get(
        'SELECT sr.*, tp.title AS project_title, u.name, u.student_no, u.class_name'
        ' FROM stage_reports sr JOIN thesis_projects tp ON tp.id = sr.project_id'
        ' JOIN users u ON u.id = sr.student_id WHERE sr.id = ?',
        (report_id,),
    )
    if not row:
        abort(404)
    result = json.loads(row['result_json'])
    return render_template(
        'stage_report.html', record=row, report=result['report'],
        stage_labels=STAGE_LABELS, viewer_role='teacher',
    )
