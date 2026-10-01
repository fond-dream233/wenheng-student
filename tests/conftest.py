"""Keep tests isolated from the repository's persisted runtime data."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_runtime = Path(tempfile.gettempdir()) / "thesis-review-tests"
os.environ.setdefault("OUTPUT_DIR", str(_runtime / "outputs"))
os.environ.setdefault("DB_PATH", str(_runtime / "outputs" / "db" / "test.db"))
os.environ.setdefault("UPLOAD_DIR", str(_runtime / "outputs" / "papers"))
os.environ.setdefault("REPORT_DIR", str(_runtime / "outputs" / "reports"))
os.environ.setdefault("RESULT_DIR", str(_runtime / "outputs" / "results"))
os.environ.setdefault("LOG_DIR", str(_runtime / "logs"))
os.environ.setdefault("APP_SECRET_KEY", "tests-only-secret")
