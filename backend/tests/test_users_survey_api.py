# 기능: 사용자 생성과 설문 제공 API의 정상 응답, 경계값, 저장 및 오류를 검사한다.
# 시스템 범위: TestClient와 임시 SQLite·설문 파일만 사용하고 기존 엔진 선택값과 비교한다.
# 결과: ID·KST·재시작 유지·12문항 계약·파일 우선순위·공통 오류가 맞으면 테스트를 통과한다.
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
import json
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import fake_engine, users
from app.main import BACKEND_DIR, app, create_app


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / 'users.sqlite3'
    official = tmp_path / 'survey.json'
    draft = tmp_path / 'survey.draft.json'
    shutil.copyfile(BACKEND_DIR / 'app' / 'data' / 'survey.draft.json', draft)
    paths = dict(db_path=db, survey_path=official, draft_path=draft)
    with TestClient(create_app(**paths), raise_server_exceptions=False) as client:
        yield client, paths


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {'error'}
    assert set(body['error']) == {'code', 'message'}
    assert body['error']['code'] == code
    assert re.search('[가-힣]', body['error']['message'])
    assert 'Traceback' not in response.text


@pytest.mark.parametrize('nickname', ['가', '가' * 10, '  하늘 \t\n', 'O"Brien', "x');--"])
def test_user_success(setup, nickname):
    client, paths = setup
    response = client.post('/api/users', json={'nickname': nickname})
    assert response.status_code == 201
    user = response.json()
    assert set(user) == {'user_id', 'nickname', 'created_at'}
    assert re.fullmatch(r'usr_[a-z0-9]{8}', user['user_id'])
    assert user['nickname'] == nickname.strip()
    created = datetime.fromisoformat(user['created_at'])
    assert created.utcoffset() == timedelta(hours=9)
    assert abs((datetime.now(created.tzinfo) - created).total_seconds()) < 10
    with closing(sqlite3.connect(paths['db_path'])) as db:
        assert db.execute('SELECT * FROM users').fetchall() == [tuple(user.values())]


@pytest.mark.parametrize('payload', [{}, {'nickname': ''}, {'nickname': ' \t\n'},
    {'nickname': '가' * 11}, {'nickname': None}, {'nickname': 1}, {'nickname': 1.2},
    {'nickname': True}, {'nickname': []}, {'nickname': {}}, [], '하늘', 12, None])
def test_invalid_input(setup, payload):
    client, paths = setup
    assert_error(client.post('/api/users', content=json.dumps(payload),
                             headers={'content-type': 'application/json'}), 422, 'VALIDATION_ERROR')
    assert not paths['db_path'].exists()


@pytest.mark.parametrize('content', ['', '{', '{"nickname":}', b'\xff'])
def test_invalid_json(setup, content):
    client, _ = setup
    response = client.post('/api/users', content=content, headers={'content-type': 'application/json'})
    assert_error(response, 422, 'VALIDATION_ERROR')


def test_duplicate_nickname_and_concurrent_ids(setup):
    client, paths = setup
    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: client.post('/api/users', json={'nickname': '하늘'}), range(32)))
    assert all(r.status_code == 201 for r in responses)
    assert len({r.json()['user_id'] for r in responses}) == 32
    with closing(sqlite3.connect(paths['db_path'])) as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 32


def test_id_collision_and_exhaustion(setup, monkeypatch):
    client, paths = setup
    monkeypatch.setattr(users, 'new_user_id', lambda: 'usr_aaaaaaaa')
    first = client.post('/api/users', json={'nickname': '첫번째'}).json()
    ids = iter(['usr_aaaaaaaa', 'usr_bbbbbbbb'])
    monkeypatch.setattr(users, 'new_user_id', lambda: next(ids))
    assert client.post('/api/users', json={'nickname': '두번째'}).json()['user_id'] == 'usr_bbbbbbbb'
    monkeypatch.setattr(users, 'new_user_id', lambda: 'usr_aaaaaaaa')
    assert_error(client.post('/api/users', json={'nickname': '실패'}), 500, 'INTERNAL_ERROR')
    with closing(sqlite3.connect(paths['db_path'])) as db:
        assert db.execute('SELECT * FROM users WHERE user_id=?', (first['user_id'],)).fetchone() == tuple(first.values())
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 2


def test_database_survives_new_app_and_process(setup):
    client, paths = setup
    first = client.post('/api/users', json={'nickname': '하늘'}).json()
    with TestClient(create_app(**paths)) as restarted:
        assert restarted.post('/api/users', json={'nickname': '하늘'}).status_code == 201
    script = """
import json, sqlite3, sys
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
with TestClient(create_app(db_path=Path(sys.argv[1]))) as client:
    assert client.post('/api/users', json={'nickname': '재시작'}).status_code == 201
with sqlite3.connect(sys.argv[1]) as db:
    assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 3
    print(json.dumps(db.execute('SELECT * FROM users WHERE user_id=?', (sys.argv[2],)).fetchone()))
"""
    result = subprocess.run([sys.executable, '-c', script, str(paths['db_path']), first['user_id']],
                            check=True, capture_output=True, text=True, cwd=BACKEND_DIR)
    assert json.loads(result.stdout) == list(first.values())


def test_database_error(setup):
    client, paths = setup
    paths['db_path'].mkdir()
    assert_error(client.post('/api/users', json={'nickname': '하늘'}), 500, 'INTERNAL_ERROR')


def test_health_docs_and_openapi(setup):
    client, _ = setup
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    error = schema['paths']['/api/users']['post']['responses']['422']['content']['application/json']['schema']
    assert error['$ref'].endswith('/ErrorResponse')
    with TestClient(app) as default_client:
        assert default_client.get('/api/health').json() == {'status': 'ok'}


def test_survey_contract_and_engine_compatibility(setup, monkeypatch):
    client, paths = setup
    response = client.get('/api/survey')
    assert response.status_code == 200
    survey = response.json()
    assert survey == json.loads(paths['draft_path'].read_text())
    assert survey['version'].startswith('provisional-')
    questions = survey['questions']
    assert [q['question_id'] for q in questions] == [f'q{i:02d}' for i in range(1, 13)]
    assert [q['section'] for q in questions] == ['life'] * 8 + ['situation'] * 4
    assert questions[0]['fields'] == [
        {'key': 'bedtime', 'label': '취침', 'min': '21:00', 'max': '03:00', 'step_minutes': 30, 'default': '23:00'},
        {'key': 'wake', 'label': '기상', 'min': '05:00', 'max': '11:00', 'step_minutes': 30, 'default': '07:00'}]
    monkeypatch.setattr(fake_engine, 'SEED_DIR', paths['survey_path'].parent)
    for index in range(4):
        answers = {'q01': {'bedtime': '23:00', 'wake': '07:00'}}
        for q in questions[1:]:
            assert q['type'] == 'choice' and len(q['options']) == 4
            answers[q['question_id']] = q['options'][index]['value']
            if q['section'] == 'situation':
                assert q['options'][index]['style'] == fake_engine.DEFAULT_STYLES[q['question_id']][answers[q['question_id']]]
        assert asyncio.run(fake_engine.build_persona('하늘', answers))['nickname'] == '하늘'
    # 프론트엔드 fixture의 모든 선택값과 순서를 독립적으로 대조한다.
    source = (BACKEND_DIR.parent / 'frontend/src/mocks/survey.ts').read_text()
    assert re.findall(r"value: '([^']+)'", source) == [o['value'] for q in questions[1:] for o in q['options']]


def test_official_priority_and_reload(setup):
    client, paths = setup
    content = json.loads(paths['draft_path'].read_text())
    content['version'] = '2026-10-29'
    content['questions'][0]['title'] = '공식 문구'
    paths['survey_path'].write_text(json.dumps(content))
    paths['draft_path'].write_text('broken')
    assert client.get('/api/survey').json() == content
    content['version'] = '2026-10-30'
    paths['survey_path'].write_text(json.dumps(content))
    assert client.get('/api/survey').json() == content


@pytest.mark.parametrize('damage', ['json', 'encoding', 'directory', 'version', 'count', 'order', 'section',
    'type', 'options', 'value', 'style', 'title', 'time', 'default', 'step'])
def test_broken_official_never_falls_back(setup, damage):
    client, paths = setup
    official = paths['survey_path']
    content = json.loads(paths['draft_path'].read_text())
    if damage == 'json':
        official.write_text('{')
    elif damage == 'encoding':
        official.write_bytes(b'\xff')
    elif damage == 'directory':
        official.mkdir()
    else:
        q = content['questions']
        if damage == 'version': content['version'] = 42
        elif damage == 'count': q.pop()
        elif damage == 'order': q.reverse()
        elif damage == 'section': q[8]['section'] = 'life'
        elif damage == 'type': q[1]['type'] = 'time_range'
        elif damage == 'options': q[1]['options'].pop()
        elif damage == 'value': q[1]['options'][0]['value'] = 'unknown'
        elif damage == 'style': q[8]['options'][0]['style'] = 'avoid'
        elif damage == 'title': q[1]['title'] = None
        elif damage == 'time': q[0]['fields'][0]['min'] = '25:00'
        elif damage == 'default': q[0]['fields'][0]['default'] = '12:00'
        elif damage == 'step': q[0]['fields'][0]['step_minutes'] = 15
        official.write_text(json.dumps(content))
    assert_error(client.get('/api/survey'), 500, 'INTERNAL_ERROR')
    assert client.get('/api/health').json() == {'status': 'ok'}


@pytest.mark.parametrize('damage', ['missing', 'broken', 'unmarked'])
def test_unavailable_draft(setup, damage):
    client, paths = setup
    draft = paths['draft_path']
    if damage == 'missing': draft.unlink()
    elif damage == 'broken': draft.write_text('{}')
    else:
        content = json.loads(draft.read_text())
        content['version'] = 'approved'
        draft.write_text(json.dumps(content))
    assert_error(client.get('/api/survey'), 500, 'INTERNAL_ERROR')
