# 기능: 후보 조회의 점수·익명 응답·접근 제어와 데이터 오류를 검증한다.
# 시스템 범위: 임시 SQLite와 독립 시드 파일을 사용하며 실제 사용자 DB를 변경하지 않는다.
# 결과: 후보 추림 계약과 기존 생성 API 연결이 올바르면 통과한다.
from decimal import Decimal, ROUND_HALF_UP
import json

import pytest
from fastapi.testclient import TestClient

from app.candidates import WEIGHTS, pre_score
from app.database import connect_database
from app.main import BACKEND_DIR, create_app
from app.personas import create_persona
from app.users import create_user
from conftest import HANEUL_ANSWERS


def axes(value=0):
    return dict.fromkeys(WEIGHTS, value)


def seed(identifier, value=0):
    return dict(persona_id=f'per_{identifier}', user_id=f'usr_{identifier}',
                candidate_pool=True, is_seed=True, axes=axes(value),
                department='테스트학과', year=1, type_name='테스트 유형',
                name='비공개실명', nickname='비공개닉네임', photo='private.png',
                answers={'private': '비공개 응답'}, summary='비공개 소개')


@pytest.fixture
def setup(tmp_path):
    db = tmp_path / 'test.sqlite3'
    path = tmp_path / 'seeds.json'
    path.write_text(json.dumps({'personas': [seed('d', 20), seed('c', 10),
                                             seed('b', 10), seed('a', 0)]}))
    user = create_user(db, '테스트')
    me = create_persona(db, user['user_id'], dict(
        type_name='테스트', summary='테스트', axes=axes(),
        axis_labels=dict.fromkeys(WEIGHTS, '테스트'),
        sleep={'bedtime': '23:00', 'wake': '07:00', 'exam_pattern': 'same'},
        conflict_style='direct', preferences={'temperature': 'moderate'},
        must_keep=[], okay_with=[]))
    app = create_app(db_path=db, seed_path=path)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db, path, me, {'X-User-Id': user['user_id']}


def request(setup, **kwargs):
    client, _, _, me, headers = setup
    return client.get(f"/api/personas/{me['persona_id']}/candidates",
                      headers=kwargs.pop('headers', headers), **kwargs)


def write_seeds(setup, seeds):
    setup[2].write_text(json.dumps({'personas': seeds}))


def test_ranking_contract_privacy_and_stability(setup):
    response = request(setup)
    assert response.status_code == 200
    cards = response.json()['candidates']
    assert [c['candidate_id'] for c in cards] == ['per_a', 'per_b', 'per_c']
    assert [c['pre_score'] for c in cards] == [100, 90, 90]
    assert [c['alias'] for c in cards] == ['후보 A', '후보 B', '후보 C']
    for card in cards:
        assert set(card) == {'candidate_id', 'alias', 'department', 'year', 'type_name',
                             'pre_score', 'highlight', 'simulation'}
        assert card['simulation'] is None
        assert card['department'] == '테스트학과' and card['year'] == 1
    assert '비공개' not in response.text and 'private.png' not in response.text
    data = json.loads(setup[2].read_text())['personas']
    write_seeds(setup, list(reversed(data)))
    assert request(setup).json() == response.json()


@pytest.mark.parametrize('axis,weight', WEIGHTS.items())
def test_each_weight_and_all_rounding_boundaries(axis, weight):
    for difference in range(101):
        other = axes()
        other[axis] = difference
        expected = int((Decimal(100) - Decimal(weight) * difference / 100)
                       .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        assert pre_score(axes(), other) == expected
        assert pre_score(other, axes()) == expected
    assert pre_score(axes(), axes(100)) == 0
    assert pre_score(axes(), axes()) == 100


def test_half_up_differs_from_builtin_round():
    other = axes()
    other['sleep_rhythm'] = 5
    assert round(98.5) == 98
    assert pre_score(axes(), other) == 99
    assert pre_score(axes(), dict(zip(WEIGHTS, [33, 67, 84, 33, 0]))) == 52


@pytest.mark.parametrize('count', [0, 1, 2])
def test_short_pool_and_exclude_self(setup, count):
    me = setup[3]
    same_id = seed('self')
    same_id['persona_id'] = me['persona_id']
    same_user = seed('same_user')
    same_user['user_id'] = me['user_id']
    not_candidate = seed('excluded')
    not_candidate.update(candidate_pool=False, department=None, year=None)
    write_seeds(setup, [same_id, same_user, not_candidate] + [seed(str(i)) for i in range(count)])
    cards = request(setup).json()['candidates']
    assert len(cards) == count
    assert [c['candidate_id'] for c in cards] == [f'per_{i}' for i in range(count)]


@pytest.mark.parametrize('headers', [{}, {'X-User-Id': ''}, {'X-User-Id': ' '},
                                    {'X-User-Id': 'usr_unknown'}])
def test_user_errors_before_loading_seed(setup, headers):
    setup[2].unlink()
    response = request(setup, headers=headers)
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'USER_REQUIRED'


def test_missing_and_other_owner(setup):
    client, db, path, me, headers = setup
    path.unlink()
    other = create_user(db, '다른사용자')
    responses = [request(setup, headers={'X-User-Id': other['user_id']}),
                 client.get('/api/personas/missing/candidates', headers=headers)]
    for response in responses:
        assert response.status_code == 404
        assert response.json()['error']['code'] == 'PERSONA_NOT_FOUND'


@pytest.mark.parametrize('field', ['axes', 'department', 'year', 'type_name',
                                   'persona_id', 'user_id', 'candidate_pool', 'is_seed'])
def test_missing_required_seed_data(setup, field):
    bad = seed('bad', 100)  # 상위 3명 밖의 손상도 숨기지 않는다.
    del bad[field]
    write_seeds(setup, [seed('a'), seed('b'), seed('c'), bad])
    assert_internal_error(request(setup))


@pytest.mark.parametrize('field,value', [('department', None), ('department', ' '),
    ('year', None), ('year', True), ('year', '1'), ('year', 0), ('year', 5),
    ('type_name', ''), ('candidate_pool', 'true'), ('is_seed', False)])
def test_invalid_seed_metadata(setup, field, value):
    bad = seed('bad')
    bad[field] = value
    write_seeds(setup, [bad])
    assert_internal_error(request(setup))


def assert_internal_error(response):
    assert response.status_code == 500
    assert response.json() == {'error': {'code': 'INTERNAL_ERROR',
        'message': '서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.'}}


@pytest.mark.parametrize('bad_axes', [{}, {'sleep_rhythm': 0}, axes(-1), axes(101),
                                     axes(True), axes(1.5), axes('10'), None])
def test_invalid_axes_in_seed_and_database(setup, bad_axes):
    bad = seed('bad')
    bad['axes'] = bad_axes
    write_seeds(setup, [bad])
    assert_internal_error(request(setup))
    write_seeds(setup, [seed('valid')])
    with connect_database(setup[1]) as db:
        db.execute('UPDATE personas SET axes=? WHERE persona_id=?',
                   (json.dumps(bad_axes), setup[3]['persona_id']))
    assert_internal_error(request(setup))


@pytest.mark.parametrize('content', ['{', '{}', '{"personas":{}}', '{"personas":[null]}'])
def test_broken_seed_file(setup, content):
    setup[2].write_text(content)
    assert_internal_error(request(setup))


def test_missing_file_and_duplicate_ids(setup):
    write_seeds(setup, [seed('a'), seed('a')])
    assert_internal_error(request(setup))
    setup[2].unlink()
    assert_internal_error(request(setup))


def test_openapi(setup):
    schema = setup[0].get('/openapi.json').json()
    operation = schema['paths']['/api/personas/{persona_id}/candidates']['get']
    assert any(p['name'] == 'X-User-Id' for p in operation['parameters'])
    assert {'200', '401', '404', '422', '500'} <= operation['responses'].keys()
    fields = schema['components']['schemas']['CandidateResponse']['properties']
    assert fields['simulation']['type'] == 'null'
    assert 'nickname' not in fields


def test_real_seed_with_api_created_persona(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_IMPL', 'fake')
    seed_path = tmp_path / 'personas.json'
    seed_path.write_bytes((BACKEND_DIR.parent / 'data/seed/personas.json').read_bytes())
    with TestClient(create_app(db_path=tmp_path / 'api.sqlite3', seed_path=seed_path)) as client:
        user = client.post('/api/users', json={'nickname': '하늘'}).json()
        headers = {'X-User-Id': user['user_id']}
        created = client.post('/api/personas', headers=headers, json={'answers': HANEUL_ANSWERS})
        assert created.status_code == 201
        response = client.get(f"/api/personas/{created.json()['persona_id']}/candidates", headers=headers)
        assert response.status_code == 200
        cards = response.json()['candidates']
        assert {c['candidate_id'] for c in cards} == {'per_subin', 'per_daeun', 'per_jiho'}
        assert [c['pre_score'] for c in cards] == sorted([c['pre_score'] for c in cards], reverse=True)
