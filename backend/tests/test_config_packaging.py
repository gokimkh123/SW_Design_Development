# 기능: DB URL 해석, 설정 우선순위, 재시작 저장 유지와 Docker 복사 구성의 설문 로딩을 검사한다.
# 시스템 범위: 환경변수와 작업 디렉터리를 격리하고 임시 DB 및 복사한 앱을 별도 프로세스로 실행한다.
# 결과: 지정 경로에만 저장되고 잘못된 설정이 거부되며 복사된 앱의 초안·공식 파일 규칙이 유지되면 통과한다.
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, database_path, sqlite_path
from app.main import create_app


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_PATH', raising=False)
    monkeypatch.chdir(tmp_path)


def test_absolute_and_relative_urls(tmp_path):
    assert sqlite_path('sqlite:////srv/var/roommate.db') == Path('/srv/var/roommate.db')
    assert sqlite_path('sqlite:///./roommate.db') == tmp_path / 'roommate.db'
    assert sqlite_path('sqlite:///nested/users.db') == tmp_path / 'nested/users.db'
    assert sqlite_path(f'sqlite:///{tmp_path}/users.db') == tmp_path / 'users.db'
    assert not (tmp_path / 'roommate.db').exists()


@pytest.mark.parametrize('url', ['', 'postgresql://host/db', 'sqlite://host/db', 'sqlite://',
    'sqlite:///', 'sqlite:///:memory:', 'sqlite:///file:users.db', 'sqlite+aiosqlite:///users.db',
    'sqlite:///users.db?mode=ro', 'sqlite:///users.db#fragment', 'sqlite:///my%20db',
    'sqlite://///host/db', 'sqlite:///   ', 'sqlite:///folder/'])
def test_invalid_url_does_not_fall_back(monkeypatch, tmp_path, url):
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'fallback.db'))
    with pytest.raises(ValueError, match='DATABASE_URL'):
        create_app()
    assert not (tmp_path / 'fallback.db').exists()


def test_priority(monkeypatch, tmp_path):
    assert database_path() == BACKEND_DIR / 'data/users.sqlite3'
    monkeypatch.setenv('DATABASE_PATH', 'legacy.db')
    assert database_path() == tmp_path / 'legacy.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///url.db')
    assert database_path() == tmp_path / 'url.db'
    assert database_path(Path('explicit.db')) == tmp_path / 'explicit.db'
    monkeypatch.setenv('DATABASE_URL', 'unsupported')
    assert database_path(Path('explicit.db')) == tmp_path / 'explicit.db'


@pytest.mark.parametrize('setting', ['DATABASE_URL', 'DATABASE_PATH'])
def test_env_database_persists_across_processes(monkeypatch, tmp_path, setting):
    db_path = tmp_path / 'persistent.db'
    monkeypatch.setenv(setting, f'sqlite:///{db_path}' if setting == 'DATABASE_URL' else str(db_path))
    with TestClient(create_app()) as client:
        response = client.post('/api/users', json={'nickname': '유지'})
        assert response.status_code == 201
        first = response.json()
    script = """
import json, sqlite3
from fastapi.testclient import TestClient
from app.main import app
from app.config import database_path
with TestClient(app) as client:
    assert client.post('/api/users', json={'nickname': '재시작'}).status_code == 201
with sqlite3.connect(database_path()) as db:
    print(json.dumps(db.execute('SELECT * FROM users ORDER BY rowid').fetchall()))
"""
    result = subprocess.run([sys.executable, '-c', script], cwd=BACKEND_DIR,
                            check=True, capture_output=True, text=True)
    rows = json.loads(result.stdout)
    assert len(rows) == 2 and rows[0] == list(first.values())


def test_relative_path_fixed_at_app_creation(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///./roommate.db')
    application = create_app()
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.chdir(other)
    with TestClient(application) as client:
        assert client.post('/api/users', json={'nickname': '경로'}).status_code == 201
    assert not (other / 'roommate.db').exists()
    with closing(sqlite3.connect(tmp_path / 'roommate.db')) as db:
        assert db.execute('SELECT nickname FROM users').fetchone() == ('경로',)


def test_dotenv_is_not_loaded(tmp_path):
    (tmp_path / '.env').write_text('DATABASE_URL=sqlite:///unexpected.db\n')
    assert database_path() == BACKEND_DIR / 'data/users.sqlite3'
    assert not (tmp_path / 'unexpected.db').exists()


def test_url_writes_only_to_priority_database(monkeypatch, tmp_path):
    legacy = tmp_path / 'legacy.db'
    monkeypatch.setenv('DATABASE_PATH', str(legacy))
    with TestClient(create_app()) as client:
        assert client.post('/api/users', json={'nickname': '기존'}).status_code == 201
    before = legacy.read_bytes()
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///selected.db')
    with TestClient(create_app()) as client:
        assert client.post('/api/users', json={'nickname': '신규'}).status_code == 201
    assert legacy.read_bytes() == before
    with closing(sqlite3.connect(tmp_path / 'selected.db')) as db:
        assert db.execute('SELECT nickname FROM users').fetchall() == [('신규',)]


def test_docker_copy_layout_survey(tmp_path):
    dockerfile = (BACKEND_DIR / 'Dockerfile').read_text()
    assert 'COPY backend/app ./app' in dockerfile
    assert 'COPY data /srv/data' in dockerfile
    root = tmp_path / 'srv'
    backend = root / 'backend'
    shutil.copytree(BACKEND_DIR / 'app', backend / 'app', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(BACKEND_DIR.parent / 'data', root / 'data')
    shutil.copytree(BACKEND_DIR.parent / 'engine', root / 'engine')
    draft = backend / 'app/data/survey.draft.json'
    assert draft.read_bytes() == (BACKEND_DIR / 'app/data/survey.draft.json').read_bytes()
    assert not (backend / 'data/survey.draft.json').exists()
    official = root / 'data/seed/survey.json'
    if official.exists():
        official.unlink()  # 임시 복사본만 제거하여 공식 파일 부재 조건을 검사한다.
    script = """
import json
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app, raise_server_exceptions=False) as client:
    assert client.get('/api/health').json() == {'status': 'ok'}
    response = client.get('/api/survey')
    print(json.dumps({'status': response.status_code, 'body': response.json()}))
"""
    env = {**os.environ, 'PYTHONPATH': str(root), 'DATABASE_URL': f'sqlite:///{root}/var/roommate.db'}

    def request():
        result = subprocess.run([sys.executable, '-c', script], cwd=backend, env=env,
                                check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    expected = json.loads(draft.read_text())
    assert request() == {'status': 200, 'body': expected}
    expected['version'] = 'official-test'
    official.write_text(json.dumps(expected))
    assert request() == {'status': 200, 'body': expected}
    official.write_text('{broken')
    result = request()
    assert result['status'] == 500
    assert result['body']['error']['code'] == 'INTERNAL_ERROR'
    assert not (root / 'var/roommate.db').exists()
