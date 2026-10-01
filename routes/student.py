"""学生端蓝图：论文上传与分析、报告查看、密码修改。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, send_file, session, url_for)

from config.settings import Config
from competition.stage_comparison import STAGE_LABELS, compare_stage_documents
from tools.analyzer import Analyzer
from tools.database import Database, now_str
from tools.logger import get_logger
from utils.decorators import login_required
from utils.security import (ensure_ext, hash_password, safe_filename,
                            validate_docx_stream, verify_password)
from utils.validators import check_password

logger = get_logger('student')

bp = Blueprint('student', __name__)
VALID_STAGES = tuple(STAGE_LABELS)


def get_db() -> Database:
    """获取当前应用的数据库客户端。"""
    return current_app.extensions['db']


@bp.route('/')
@login_required('student')
def index():
    """学生主页：上传论文与查看历史报告。"""
    db = get_db()
    papers = db.query(
        'SELECT p.*, tp.title AS project_title, r.id AS report_id, r.total_score,'
        ' r.format_score, r.logic_score,'
        ' r.ai_likelihood, r.created_at AS analyzed_at'
        ' FROM papers p LEFT JOIN thesis_projects tp ON tp.id = p.project_id'
        ' LEFT JOIN reports r ON r.paper_id = p.id'
        ' WHERE p.student_id = ? ORDER BY p.id DESC',
        (session['user_id'],),
    )
    project_rows = db.query(
        'SELECT tp.*, (SELECT COUNT(DISTINCT p.stage) FROM papers p'
        ' WHERE p.project_id = tp.id) AS stage_count'
        ' FROM thesis_projects tp WHERE tp.student_id = ? ORDER BY tp.updated_at DESC, tp.id DESC',
        (session['user_id'],),
    )
    projects = []
    for project_row in project_rows:
        stage_rows = db.query(
            'SELECT p.id, p.stage, p.original_name, p.uploaded_at, p.status'
            ' FROM papers p WHERE p.project_id = ? AND p.id IN'
            ' (SELECT MAX(id) FROM papers WHERE project_id = ? GROUP BY stage)'
            ' ORDER BY CASE p.stage WHEN \'proposal\' THEN 1 WHEN \'midterm\' THEN 2 ELSE 3 END',
            (project_row['id'], project_row['id']),
        )
        latest_report = db.get(
            'SELECT id, risk_level, drift_score, created_at FROM stage_reports'
            ' WHERE project_id = ? ORDER BY id DESC LIMIT 1',
            (project_row['id'],),
        )
        projects.append({
            **dict(project_row),
            'stages': [dict(row) for row in stage_rows],
            'latest_report': dict(latest_report) if latest_report else None,
        })
    configured = db.get(
        "SELECT COUNT(*) AS c FROM format_rules WHERE enabled = 1 AND expected <> ''")['c']
    return render_template(
        'student_index.html', papers=papers, projects=projects,
        configured=configured, stage_labels=STAGE_LABELS,
    )


@bp.route('/upload', methods=['POST'])
@login_required('student')
def upload():
    """上传论文并立即执行分析。"""
    db = get_db()
    file = request.files.get('file')
    project_title = ' '.join((request.form.get('project_title') or '').split())
    stage = (request.form.get('stage') or '').strip()
    if not project_title or len(project_title) > 120:
        flash('请输入 1–120 字的课题名称', 'danger')
        return redirect(url_for('student.index'))
    if stage not in VALID_STAGES:
        flash('请选择开题、中期或终稿阶段', 'danger')
        return redirect(url_for('student.index'))
    if not file or not file.filename:
        flash('请选择要上传的 .docx 论文文件', 'danger')
        return redirect(url_for('student.index'))

    allowed, _ = ensure_ext(file.filename, Config.ALLOWED_EXT)
    if not allowed:
        flash('仅支持 .docx 格式的论文文件', 'danger')
        return redirect(url_for('student.index'))
    valid, message = validate_docx_stream(file.stream)
    if not valid:
        flash(message, 'danger')
        return redirect(url_for('student.index'))

    student_id = session['user_id']
    project = db.get(
        'SELECT * FROM thesis_projects WHERE student_id = ? AND title = ? COLLATE NOCASE',
        (student_id, project_title),
    )
    if project:
        project_id = project['id']
        db.execute('UPDATE thesis_projects SET updated_at = ? WHERE id = ?',
                   (now_str(), project_id))
    else:
        project_id = db.execute(
            'INSERT INTO thesis_projects (student_id, title, created_at, updated_at)'
            ' VALUES (?, ?, ?, ?)',
            (student_id, project_title, now_str(), now_str()),
        )
    filename = safe_filename(file.filename)
    target_dir = Config.UPLOAD_DIR / f"student_{student_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
    stored_path = target_dir / stored_name
    file.save(str(stored_path))

    version = db.get('SELECT COUNT(*) AS c FROM papers WHERE student_id = ?',
                     (student_id,))['c'] + 1
    paper_id = db.execute(
        'INSERT INTO papers (student_id, original_name, stored_path, file_size, version,'
        ' project_id, stage, status, uploaded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (student_id, filename, str(stored_path), stored_path.stat().st_size,
         version, project_id, stage, 'uploaded', now_str()),
    )
    logger.info('学生 %s 上传论文 %s', student_id, filename)

    try:
        Analyzer(db).run(paper_id)
        flash(f'{STAGE_LABELS[stage]}文档上传并分析完成', 'success')
    except Exception as exc:  # noqa: BLE001 - 分析失败需提示学生
        logger.error('论文分析失败：%s', exc)
        flash(f'论文上传成功，但分析失败：{exc}', 'warning')
    return redirect(url_for('student.index'))


@bp.route('/projects/<int:project_id>/compare', methods=['POST'])
@login_required('student')
def compare_project(project_id: int):
    """Compare the latest document from every available stage in one project."""
    db = get_db()
    project = db.get(
        'SELECT * FROM thesis_projects WHERE id = ? AND student_id = ?',
        (project_id, session['user_id']),
    )
    if not project:
        abort(403)
    papers = db.query(
        'SELECT * FROM papers WHERE project_id = ? AND id IN'
        ' (SELECT MAX(id) FROM papers WHERE project_id = ? GROUP BY stage)'
        ' ORDER BY CASE stage WHEN \'proposal\' THEN 1 WHEN \'midterm\' THEN 2 ELSE 3 END',
        (project_id, project_id),
    )
    available = [row for row in papers if row['stage'] in VALID_STAGES]
    if len(available) < 2:
        flash('至少上传两个不同阶段后才能进行跨阶段对比', 'warning')
        return redirect(url_for('student.index'))
    missing = [row['original_name'] for row in available if not Path(row['stored_path']).is_file()]
    if missing:
        flash('阶段文档已丢失，请重新上传：' + '、'.join(missing), 'danger')
        return redirect(url_for('student.index'))
    try:
        result = compare_stage_documents([
            (row['stage'], Path(row['stored_path']), row['original_name']) for row in available
        ])
        report = result['report']
        report_id = db.execute(
            'INSERT INTO stage_reports (project_id, student_id, stages_json, result_json,'
            ' risk_level, drift_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (
                project_id,
                session['user_id'],
                json.dumps({row['stage']: row['id'] for row in available}, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
                report['riskLevel'],
                report['overallDriftScore'],
                now_str(),
            ),
        )
    except Exception as exc:  # web boundary: keep the previous reports available
        logger.error('课题 %s 跨阶段分析失败：%s', project_id, exc)
        flash(f'跨阶段分析失败：{exc}', 'danger')
        return redirect(url_for('student.index'))
    flash('跨阶段分析完成', 'success')
    return redirect(url_for('student.view_stage_report', report_id=report_id))


@bp.route('/stage-report/<int:report_id>')
@login_required('student')
def view_stage_report(report_id: int):
    """Render one cross-stage report owned by the current student."""
    row = get_db().get(
        'SELECT sr.*, tp.title AS project_title FROM stage_reports sr'
        ' JOIN thesis_projects tp ON tp.id = sr.project_id'
        ' WHERE sr.id = ? AND sr.student_id = ?',
        (report_id, session['user_id']),
    )
    if not row:
        abort(404)
    result = json.loads(row['result_json'])
    return render_template(
        'stage_report.html', record=row, report=result['report'],
        stage_labels=STAGE_LABELS, viewer_role='student',
    )


@bp.route('/analyze/<int:paper_id>', methods=['POST'])
@login_required('student')
def analyze(paper_id: int):
    """对已上传的论文重新分析。"""
    db = get_db()
    paper = db.get('SELECT * FROM papers WHERE id = ? AND student_id = ?',
                   (paper_id, session['user_id']))
    if not paper:
        abort(403)
    if not Path(paper['stored_path']).exists():
        flash('论文文件已丢失，请重新上传', 'danger')
        return redirect(url_for('student.index'))
    db.execute('DELETE FROM reports WHERE paper_id = ?', (paper_id,))
    try:
        Analyzer(db).run(paper_id)
        flash('重新分析完成', 'success')
    except Exception as exc:  # noqa: BLE001
        logger.error('重新分析失败：%s', exc)
        flash(f'分析失败：{exc}', 'danger')
    return redirect(url_for('student.index'))


@bp.route('/report/<int:report_id>')
@login_required('student')
def view_report(report_id: int):
    """查看自己的分析报告。"""
    row = get_db().get('SELECT * FROM reports WHERE id = ? AND student_id = ?',
                       (report_id, session['user_id']))
    if not row or not row['report_path']:
        abort(404)
    path = Path(row['report_path'])
    if not path.exists():
        abort(404)
    return path.read_text(encoding='utf-8')


@bp.route('/report/<int:report_id>/download')
@login_required('student')
def download_report(report_id: int):
    """下载分析报告。"""
    row = get_db().get('SELECT * FROM reports WHERE id = ? AND student_id = ?',
                       (report_id, session['user_id']))
    if not row or not row['report_path'] or not Path(row['report_path']).exists():
        abort(404)
    return send_file(row['report_path'], as_attachment=True,
                     download_name=f"论文检查报告_{report_id}.html")


@bp.route('/password', methods=['POST'])
@login_required('student')
def change_password():
    """修改登录密码。"""
    db = get_db()
    old = request.form.get('old_password') or ''
    new = request.form.get('new_password') or ''
    row = db.get('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    if not verify_password(row['password_hash'], old):
        flash('原密码不正确', 'danger')
        return redirect(url_for('student.index'))
    ok, msg = check_password(new)
    if not ok:
        flash(msg, 'danger')
        return redirect(url_for('student.index'))
    db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
               (hash_password(new), session['user_id']))
    flash('密码修改成功', 'success')
    return redirect(url_for('student.index'))
