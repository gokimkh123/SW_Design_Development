# 기능: 페르소나 생성·조회·수정 API의 명세와 엔진·DB 연결을 검사한다.
# 시스템 범위: 임시 SQLite·설문 파일과 가짜 엔진으로 HTTP 요청을 실행한다.
# 결과: 응답·저장·소유권·입력 검사·실패 복구가 올바르면 통과한다.
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
import re
import shutil
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import engine_adapter, fake_engine, personas
from app.main import BACKEND_DIR, create_app
from conftest import HANEUL_ANSWERS


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_IMPL', 'fake')
    engine_adapter.get_engine.cache_clear()
    draft = tmp_path / 'draft.json'
    shutil.copyfile(BACKEND_DIR / 'app/data/survey.draft.json', draft)
    db = tmp_path / 'users.sqlite3'
    paths = dict(db_path=db, survey_path=tmp_path / 'official.json', draft_path=draft)
    app = create_app(**paths)
    with TestClient(app, raise_server_exceptions=False) as client:
        user = client.post('/api/users', json={'nickname': '하늘'}).json()
        headers = {'X-User-Id': user['user_id']}
        yield client, app, paths, user, headers
    engine_adapter.get_engine.cache_clear()


def counts(paths):
    with sqlite3.connect(paths['db_path']) as db:
        return db.execute('SELECT COUNT(*) FROM personas').fetchone()[0]


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = response.json()['error']
    assert error['code'] == code
    assert re.search('[가-힣]', error['message'])
    assert 'Traceback' not in response.text


def create(client, headers, answers=None):
    return client.post('/api/personas', headers=headers,
                       json={'answers': HANEUL_ANSWERS if answers is None else answers})


def test_create_get_and_restart(setup):
    client, _, paths, user, headers = setup
    response = create(client, headers)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert set(saved) == set(personas.PersonaData.model_fields) | {'persona_id', 'user_id', 'nickname', 'created_at'}
    assert re.fullmatch(r'per_[a-z0-9]{8}', saved['persona_id'])
    assert saved['user_id'] == user['user_id'] and saved['nickname'] == '하늘'
    assert saved['is_seed'] is False
    assert datetime.fromisoformat(saved['created_at']).utcoffset() == timedelta(hours=9)
    expected = asyncio.run(fake_engine.build_persona('하늘', HANEUL_ANSWERS))
    assert all(saved[key] == value for key, value in expected.items())
    assert personas.get_persona(paths['db_path'], saved['persona_id']) == saved
    assert client.get(f"/api/personas/{saved['persona_id']}", headers=headers).json() == saved
    with TestClient(create_app(**paths)) as restarted:
        assert restarted.get(f"/api/personas/{saved['persona_id']}", headers=headers).json() == saved
    second = create(client, headers).json()
    assert second['persona_id'] != saved['persona_id'] and counts(paths) == 2


@pytest.mark.parametrize('header', [None, '', 'usr_unknown'])
@pytest.mark.parametrize('method,path', [('post', '/api/personas'), ('get', '/api/personas/missing'),
                                      ('patch', '/api/personas/missing')])
def test_user_required(setup, header, method, path):
    client, app, paths, _, _ = setup
    async def forbidden(*args):
        pytest.fail('사용자 확인 전에 엔진을 호출하면 안 됩니다.')
    app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=forbidden)
    kwargs = {'headers': {} if header is None else {'X-User-Id': header}}
    if method != 'get':
        kwargs['json'] = {'answers': HANEUL_ANSWERS} if method == 'post' else {'must_keep': []}
    assert_error(getattr(client, method)(path, **kwargs), 401, 'USER_REQUIRED')
    assert counts(paths) == 0


def test_missing_answers_no_engine_or_save(setup):
    client, app, paths, _, headers = setup
    async def forbidden(*args):
        pytest.fail('잘못된 답변으로 엔진을 호출하면 안 됩니다.')
    app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=forbidden)
    answers = deepcopy(HANEUL_ANSWERS)
    del answers['q02']
    del answers['q12']
    response = create(client, headers, answers)
    assert_error(response, 400, 'SURVEY_INCOMPLETE')
    assert 'q02' in response.text and 'q12' in response.text
    assert_error(create(client, headers, {}), 400, 'SURVEY_INCOMPLETE')
    assert counts(paths) == 0


@pytest.mark.parametrize('field,value', [('q02', 'wrong'), ('q02', 'warm'), ('q03', 1),
    ('q04', None), ('q05', []), ('q13', 'extra'), ('q01', '23:00'),
    ('q01', {'bedtime': '23:00'}), ('q01', {'bedtime': '23:00', 'wake': '07:00', 'extra': 'x'}),
    ('q01', {'bedtime': '24:00', 'wake': '07:00'}),
    ('q01', {'bedtime': '20:30', 'wake': '07:00'}),
    ('q01', {'bedtime': '03:30', 'wake': '07:00'}),
    ('q01', {'bedtime': '23:15', 'wake': '07:00'}),
    ('q01', {'bedtime': '23:00', 'wake': '11:30'}),
    ('q01', {'bedtime': 23, 'wake': '07:00'})])
def test_invalid_answers(setup, field, value):
    client, app, paths, _, headers = setup
    async def forbidden(*args):
        pytest.fail('잘못된 답변으로 엔진을 호출하면 안 됩니다.')
    app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=forbidden)
    answers = deepcopy(HANEUL_ANSWERS)
    answers[field] = value
    assert_error(create(client, headers, answers), 422, 'VALIDATION_ERROR')
    assert counts(paths) == 0


@pytest.mark.parametrize('body', [{}, {'answers': None}, {'answers': []},
    {'answers': HANEUL_ANSWERS, 'user_id': 'usr_other'}, {'answers': HANEUL_ANSWERS, 'is_seed': True}])
def test_invalid_body(setup, body):
    client, _, paths, _, headers = setup
    assert_error(client.post('/api/personas', headers=headers, json=body), 422, 'VALIDATION_ERROR')
    assert counts(paths) == 0


def test_invalid_json(setup):
    client, _, paths, _, headers = setup
    assert_error(client.post('/api/personas', headers={**headers, 'Content-Type': 'application/json'},
                             content='{'), 422, 'VALIDATION_ERROR')
    assert counts(paths) == 0


@pytest.mark.parametrize('bedtime,wake', [('21:00', '05:00'), ('00:00', '07:00'), ('03:00', '11:00')])
def test_overnight_time_boundaries(setup, bedtime, wake):
    client, _, _, _, headers = setup
    answers = deepcopy(HANEUL_ANSWERS)
    answers['q01'] = {'bedtime': bedtime, 'wake': wake}
    assert create(client, headers, answers).status_code == 201


def test_engine_receives_db_identity_and_validated_answers(setup):
    client, app, _, user, headers = setup
    calls = []
    async def build(nickname, answers):
        calls.append((nickname, answers))
        result = await fake_engine.build_persona(nickname, answers)
        return {**result, 'user_id': 'forged', 'persona_id': 'forged', 'is_seed': True,
                'nickname': '가짜이름', 'created_at': 'forged'}
    app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=build)
    saved = create(client, headers).json()
    assert calls == [('하늘', HANEUL_ANSWERS)]
    assert saved['user_id'] == user['user_id'] and saved['nickname'] == '하늘'
    assert saved['is_seed'] is False and saved['persona_id'] != 'forged'


def test_llm_failure_uses_adapter_fallback(setup):
    client, app, paths, _, headers = setup
    class APIConnectionError(Exception):
        pass
    async def fail(*args):
        raise APIConnectionError('테스트용 연결 실패')
    adapter = engine_adapter.EngineAdapter(SimpleNamespace(build_persona=fail))
    app.dependency_overrides[engine_adapter.get_engine] = lambda: adapter
    assert create(client, headers).status_code == 201
    assert counts(paths) == 1


def test_timeout_uses_rule_based_fallback(setup, monkeypatch):
    from app import persona_api
    client, app, paths, _, headers = setup
    async def slow(*args):
        await asyncio.sleep(60)
    monkeypatch.setattr(persona_api, 'PERSONA_ENGINE_TIMEOUT_SECONDS', 0.01)
    app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=slow)
    assert create(client, headers).status_code == 201
    assert counts(paths) == 1


@pytest.mark.parametrize('failure', ['engine', 'storage', 'invalid_output'])
def test_unexpected_failures_do_not_save(setup, monkeypatch, failure):
    from app import persona_api
    client, app, paths, _, headers = setup
    if failure == 'storage':
        def fail(*args):
            raise sqlite3.OperationalError('테스트용 DB 오류')
        monkeypatch.setattr(persona_api, 'create_persona', fail)
    else:
        async def build(*args):
            if failure == 'engine':
                raise RuntimeError('테스트용 내부 오류')
            return {'summary': '불완전한 결과'}
        app.dependency_overrides[engine_adapter.get_engine] = lambda: SimpleNamespace(build_persona=build)
    assert_error(create(client, headers), 500, 'INTERNAL_ERROR')
    assert counts(paths) == 0


def test_ownership_and_partial_patch(setup):
    client, _, paths, _, headers = setup
    saved = create(client, headers).json()
    path = f"/api/personas/{saved['persona_id']}"
    other = client.post('/api/users', json={'nickname': '다른사람'}).json()
    other_headers = {'X-User-Id': other['user_id']}
    assert_error(client.get(path, headers=other_headers), 404, 'PERSONA_NOT_FOUND')
    assert_error(client.patch(path, headers=other_headers, json={'must_keep': []}), 404, 'PERSONA_NOT_FOUND')
    assert_error(client.get('/api/personas/missing', headers=headers), 404, 'PERSONA_NOT_FOUND')
    assert_error(client.patch('/api/personas/missing', headers=headers, json={}), 404, 'PERSONA_NOT_FOUND')
    changed = client.patch(path, headers=headers, json={'must_keep': ['밤에는 조용히']})
    assert changed.status_code == 200
    expected = {**saved, 'must_keep': ['밤에는 조용히']}
    assert changed.json() == expected
    assert personas.get_persona(paths['db_path'], saved['persona_id']) == expected
    cleared = client.patch(path, headers=headers, json={'okay_with': []}).json()
    assert cleared == {**expected, 'okay_with': []}
    assert client.patch(path, headers=headers, json={}).json() == cleared
    assert create(client, other_headers).json()['user_id'] == other['user_id']


@pytest.mark.parametrize('body', [{'must_keep': ['x'] * 4}, {'okay_with': ['가' * 31]},
    {'must_keep': None}, {'okay_with': '문자열'}, {'must_keep': [1]}, {'axes': {}}, {'nickname': '변경'}])
def test_patch_validation_keeps_original(setup, body):
    client, _, paths, _, headers = setup
    saved = create(client, headers).json()
    response = client.patch(f"/api/personas/{saved['persona_id']}", headers=headers, json=body)
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert personas.get_persona(paths['db_path'], saved['persona_id']) == saved


def test_openapi_header_and_response(setup):
    client, _, _, _, _ = setup
    schema = client.get('/openapi.json').json()
    for method, path in [('post', '/api/personas'), ('get', '/api/personas/{persona_id}'),
                         ('patch', '/api/personas/{persona_id}')]:
        operation = schema['paths'][path][method]
        assert any(p['name'] == 'X-User-Id' and p['in'] == 'header' for p in operation['parameters'])
        assert ('201' if method == 'post' else '200') in operation['responses']
        for status in ('401', '422', '500'):
            response = operation['responses'][status]['content']['application/json']['schema']
            assert response['$ref'].endswith('/ErrorResponse')


def test_patch_limits_and_no_other_persona_changes(setup):
    client, _, paths, _, headers = setup
    first = create(client, headers).json()
    second = create(client, headers).json()
    values = ['가' * 30] * 3
    response = client.patch(f"/api/personas/{first['persona_id']}", headers=headers,
                            json={'must_keep': values, 'okay_with': values})
    assert response.status_code == 200
    assert response.json() == {**first, 'must_keep': values, 'okay_with': values}
    assert personas.get_persona(paths['db_path'], second['persona_id']) == second


def test_broken_official_survey_prevents_generation(setup):
    client, _, paths, _, headers = setup
    paths['survey_path'].write_text('{broken')
    assert_error(create(client, headers), 500, 'INTERNAL_ERROR')
    assert counts(paths) == 0
