"""SQLite 数据库客户端：连接管理、建表、初始数据。

通过依赖注入使用：`Database(path)` 实例由应用创建后传入各业务模块。
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from config.settings import Config
from tools.logger import get_logger
from tools.rules_schema import RULES

logger = get_logger("database")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    UNIQUE NOT NULL,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('teacher', 'student')),
    name          TEXT    NOT NULL DEFAULT '',
    student_no    TEXT    NOT NULL DEFAULT '',
    class_name    TEXT    NOT NULL DEFAULT '',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS thesis_projects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title         TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_thesis_projects_student ON thesis_projects(student_id);

CREATE TABLE IF NOT EXISTS papers (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_name TEXT    NOT NULL,
    stored_path   TEXT    NOT NULL,
    file_size     INTEGER NOT NULL DEFAULT 0,
    version       INTEGER NOT NULL DEFAULT 1,
    project_id    INTEGER REFERENCES thesis_projects(id) ON DELETE SET NULL,
    stage         TEXT    NOT NULL DEFAULT 'final',
    title         TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL DEFAULT 'uploaded',
    error_msg     TEXT    NOT NULL DEFAULT '',
    uploaded_at   TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_student ON papers(student_id);

CREATE TABLE IF NOT EXISTS reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id      INTEGER NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    student_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version       INTEGER NOT NULL DEFAULT 1,
    format_score  REAL,
    logic_score   REAL,
    total_score   REAL,
    ai_likelihood REAL    NOT NULL DEFAULT 0,
    issue_count   INTEGER NOT NULL DEFAULT 0,
    result_json   TEXT    NOT NULL DEFAULT '',
    report_path   TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_paper ON reports(paper_id);
CREATE INDEX IF NOT EXISTS idx_reports_student ON reports(student_id);

CREATE TABLE IF NOT EXISTS stage_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES thesis_projects(id) ON DELETE CASCADE,
    student_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    stages_json   TEXT    NOT NULL,
    result_json   TEXT    NOT NULL,
    risk_level    TEXT    NOT NULL,
    drift_score   REAL    NOT NULL,
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stage_reports_project ON stage_reports(project_id);
CREATE INDEX IF NOT EXISTS idx_stage_reports_student ON stage_reports(student_id);

CREATE TABLE IF NOT EXISTS format_rules (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_key   TEXT    UNIQUE NOT NULL,
    category   TEXT    NOT NULL,
    title      TEXT    NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 0,
    expected   TEXT    NOT NULL DEFAULT '',
    weight     REAL    NOT NULL DEFAULT 3,
    updated_at TEXT
);
"""


def now_str() -> str:
    """返回当前时间的标准字符串（用于入库）。

    Returns:
        `YYYY-MM-DD HH:MM:SS` 格式时间串。
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    """SQLite 轻量封装，提供连接上下文与常用查询方法。"""

    def __init__(self, db_path: Path) -> None:
        """初始化数据库客户端。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """获取数据库连接上下文，自动提交/回滚/关闭。

        Yields:
            已开启外键约束且 row_factory 为 Row 的连接。

        Raises:
            sqlite3.Error: 事务执行失败时抛出，连接自动回滚。
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        """建表并写入初始数据（默认教师账号、格式规则定义）。"""
        with self.connection() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate_schema(conn)
        self._seed_rules()
        self._seed_teacher()
        logger.info("数据库初始化完成：%s", self.db_path)

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection) -> None:
        """Add stage fields to databases created by earlier project versions."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(papers)").fetchall()}
        if "project_id" not in columns:
            conn.execute(
                "ALTER TABLE papers ADD COLUMN project_id INTEGER"
                " REFERENCES thesis_projects(id) ON DELETE SET NULL"
            )
        if "stage" not in columns:
            conn.execute("ALTER TABLE papers ADD COLUMN stage TEXT NOT NULL DEFAULT 'final'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_papers_project_stage"
            " ON papers(project_id, stage, id)"
        )

    def _seed_rules(self) -> None:
        """写入格式规则定义，默认按学校模板预设值启用。"""
        with self.connection() as conn:
            for rule in RULES:
                conn.execute(
                    "INSERT OR IGNORE INTO format_rules"
                    " (rule_key, category, title, enabled, expected, weight, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (rule.key, rule.category, rule.title, 1 if rule.preset else 0,
                     rule.preset, rule.default_weight, now_str()),
                )

    def _seed_teacher(self) -> None:
        """首次启动时创建默认教师账号。"""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE role = 'teacher' LIMIT 1"
            ).fetchone()
            if row:
                return
        from utils.security import hash_password  # 局部导入避免循环依赖

        with self.connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, name, created_at)"
                " VALUES (?, ?, 'teacher', ?, ?)",
                (
                    Config.DEFAULT_TEACHER_USERNAME,
                    hash_password(Config.DEFAULT_TEACHER_PASSWORD),
                    Config.DEFAULT_TEACHER_NAME,
                    now_str(),
                ),
            )
        if not Config.DEFAULT_TEACHER_PASSWORD_FROM_ENV:
            credential_file = Config.DB_PATH.parent / "initial_admin_password.txt"
            credential_file.write_text(Config.DEFAULT_TEACHER_PASSWORD, encoding="utf-8")
            logger.warning("管理员初始口令已写入本地文件：%s，请首次登录后删除", credential_file)
        logger.info("已创建默认教师账号：%s", Config.DEFAULT_TEACHER_USERNAME)

    # ---------------- 通用查询 ----------------
    def query(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        """执行查询并返回全部结果行。

        Args:
            sql: SQL 语句。
            params: 绑定参数。

        Returns:
            结果行列表（可能为 []）。
        """
        with self.connection() as conn:
            return conn.execute(sql, params).fetchall()

    def get(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        """执行查询并返回首行。

        Args:
            sql: SQL 语句。
            params: 绑定参数。

        Returns:
            首行 Row，无结果时返回 None。
        """
        with self.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """执行写操作并返回自增主键。

        Args:
            sql: SQL 语句。
            params: 绑定参数。

        Returns:
            最后插入行的主键 id。
        """
        with self.connection() as conn:
            cur = conn.execute(sql, params)
            return int(cur.lastrowid or 0)

    def execute_many(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        """批量执行写操作。

        Args:
            sql: SQL 语句。
            rows: 参数序列。
        """
        with self.connection() as conn:
            conn.executemany(sql, rows)

    # ---------------- 规则 ----------------
    def get_rules(self) -> Dict[str, Dict[str, Any]]:
        """读取全部格式规则，按 rule_key 索引。

        Returns:
            {规则键: {enabled, expected, weight, title, category}}。
        """
        rows = self.query("SELECT rule_key, category, title, enabled, expected, weight FROM format_rules")
        return {
            r["rule_key"]: {
                "category": r["category"],
                "title": r["title"],
                "enabled": bool(r["enabled"]),
                "expected": r["expected"],
                "weight": float(r["weight"] or 0),
            }
            for r in rows
        }

    def load_preset_rules(self) -> int:
        """载入「西南科技大学 2026 届模板」默认规范并启用全部规则。

        Returns:
            受影响的规则条数。
        """
        count = 0
        with self.connection() as conn:
            for rule in RULES:
                conn.execute(
                    "UPDATE format_rules SET enabled = ?, expected = ?, weight = ?, updated_at = ?"
                    " WHERE rule_key = ?",
                    (1 if rule.preset else 0, rule.preset, rule.default_weight,
                     now_str(), rule.key),
                )
                count += 1
        logger.info("已载入学校模板默认规范，共 %s 条规则", count)
        return count

    def clear_rules(self) -> int:
        """清空并停用全部格式规则（等待导入学校官方规范）。

        Returns:
            受影响的规则条数。
        """
        with self.connection() as conn:
            cur = conn.execute(
                "UPDATE format_rules SET enabled = 0, expected = '', updated_at = ?", (now_str(),)
            )
            return int(cur.rowcount or 0)
