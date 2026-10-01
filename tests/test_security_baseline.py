from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document

from app import app
from utils.security import validate_docx_stream


def _csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def test_csrf_headers_and_logout_method():
    client = app.test_client()
    page = client.get('/login')
    assert page.status_code == 200
    assert page.headers['X-Content-Type-Options'] == 'nosniff'
    assert page.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert "object-src 'none'" in page.headers['Content-Security-Policy']
    assert client.post('/login', data={'username': 'x', 'password': 'x'}).status_code == 400
    token = _csrf_token(page.get_data(as_text=True))
    response = client.post('/login', data={
        'csrf_token': token, 'username': 'nobody', 'password': 'incorrect'
    })
    assert response.status_code == 200
    assert client.get('/logout').status_code == 405


def test_docx_content_validation(tmp_path: Path):
    invalid = io.BytesIO(b'not a docx')
    assert validate_docx_stream(invalid)[0] is False

    path = tmp_path / 'valid.docx'
    document = Document()
    document.add_paragraph('valid')
    document.save(path)
    with path.open('rb') as stream:
        assert validate_docx_stream(stream) == (True, '')


def test_account_download_rejects_path_traversal(tmp_path: Path):
    outside = tmp_path / 'accounts_escape.txt'
    outside.write_text('secret', encoding='utf-8')
    client = app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 1
        session['role'] = 'teacher'
    response = client.get('/teacher/accounts/download', query_string={'file': str(outside)})
    assert response.status_code == 302
