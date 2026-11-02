# 기능: 가상 동거 이용권(API.md 4.18) 조회 · 구매와 이용 횟수 한도, 후보 6명 별칭, 궁합 진단 API를 검증한다.
# 시스템 범위: 임시 SQLite와 시드 후보만 사용하며 결제 · 외부 서비스 · 엔진 실행은 호출하지 않는다.
# 결과: 무료 횟수 소진 시 새 실행이 기록 없이 거절되고, 구매분만큼 다시 허용되며, 재사용 · 실패 실행은 차감되지 않음을 확인한다.
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import httpx
import pytest

from app import simulations as store
from app.database import connect_database
from app.main import create_app
from app.personas import PersonaData, create_persona
from app.users import create_user
from test_simulations import context  # noqa: F401 (pytest fixture)

SEED_PATH = Path(__file__).resolve().parents[2] / 'data/seed/personas.json'
SEEDS = json.loads(SEED_PATH.read_text(encoding='utf-8'))['personas']
POOL = [s for s in SEEDS if s['candidate_pool']]


def call(db, method, path, user, body=None):
    application = create_app(db_path=db)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            return await client.request(method, path, json=body, headers={'X-User-Id': user} if user else {})
    return asyncio.run(run())


def test_pass_summary_purchase_and_limit(tmp_path):
    db = tmp_path / 'passes.sqlite3'
    me = create_user(db, '하늘')['user_id']
    other = create_user(db, '다른 사람')['user_id']
    initial = call(db, 'GET', '/api/passes/me', me)
    assert initial.status_code == 200
    assert initial.json() == {'free_quota': 3, 'purchased': 0, 'used': 0, 'remaining': 3, 'purchases': []}

    bought = call(db, 'POST', '/api/passes', me, {'product': 'pass_5'})
    assert bought.status_code == 201
    body = bought.json()
    assert (body['purchased'], body['remaining']) == (5, 8)
    assert body['purchases'][0]['product'] == 'pass_5' and body['purchases'][0]['price'] == 2900
    assert call(db, 'GET', '/api/passes/me', other).json()['purchased'] == 0  # 사용자별 격리

    for _ in range(3):
        assert call(db, 'POST', '/api/passes', me, {'product': 'pass_15'}).status_code == 201
    assert call(db, 'GET', '/api/passes/me', me).json()['purchased'] == 50
    assert call(db, 'POST', '/api/passes', me, {'product': 'pass_15'}).json()['error']['code'] == 'PASS_LIMIT'
    assert call(db, 'POST', '/api/passes', me, {'product': 'pass_5'}).status_code == 201
    assert call(db, 'GET', '/api/passes/me', me).json()['purchased'] == 55


def test_pass_errors(tmp_path):
    db = tmp_path / 'passes.sqlite3'
    me = create_user(db, '하늘')['user_id']
    for method, path, body in (('GET', '/api/passes/me', None), ('POST', '/api/passes', {'product': 'pass_5'})):
        response = call(db, method, path, None, body)
        assert response.status_code == 401 and response.json()['error']['code'] == 'USER_REQUIRED'
    for body in ({'product': 'unlimited'}, {'product': 'pass_5', 'card_number': '1234'}, {}, {'product': 5}):
        response = call(db, 'POST', '/api/passes', me, body)
        assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    with connect_database(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM pass_purchases').fetchone()[0] == 0


def test_quota_blocks_before_insert_and_purchase_reopens(context):
    path, args, user, _ = context
    first, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])), free_quota=1)
    assert created
    with pytest.raises(store.SimulationLimitError) as info:
        store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[1]), alias='후보 F'), free_quota=1)
    assert info.value.scope == 'quota'
    # 같은 후보 재요청은 재사용이므로 차감 · 거절 없음
    again, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])), free_quota=1)
    assert not created and again['simulation_id'] == first['simulation_id']
    with connect_database(path) as db:
        assert db.execute('SELECT COUNT(*) FROM simulations').fetchone()[0] == 1
        db.execute("INSERT INTO pass_purchases VALUES ('pas_t', ?, 'pass_5', 5, 2900, '2026-11-02T00:00:00+09:00')",
                   (user['user_id'],))
    sim, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[1]), alias='후보 F'),
                                                    free_quota=1)
    assert created and sim['status'] == 'running'


def test_failed_runs_are_not_charged(context):
    path, args, *_ = context
    sim, _ = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])), free_quota=1)
    with connect_database(path) as db:
        db.execute("UPDATE simulations SET status='failed', failure='{}', failed_at='2026-11-02T00:00:00+09:00' "
                   'WHERE simulation_id=?', (sim['simulation_id'],))
    _, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[1])), free_quota=1)
    assert created


def test_unknown_alias_rejected(context):
    path, args, *_ = context
    with pytest.raises(ValueError):
        store.create_or_reuse_simulation(path, **dict(args, alias='후보 G'))


def test_start_api_returns_402_when_quota_used(tmp_path, monkeypatch):
    from app import simulation_api
    monkeypatch.setattr(simulation_api, 'FREE_SIMULATIONS', 0)
    db = tmp_path / 'start.sqlite3'
    user = create_user(db, '테스터')
    data = {k: SEEDS[0][k] for k in PersonaData.model_fields}
    data['is_seed'] = False
    persona = create_persona(db, user['user_id'], data)
    cards = call(db, 'GET', f"/api/personas/{persona['persona_id']}/candidates", user['user_id']).json()['candidates']
    response = call(db, 'POST', '/api/simulations', user['user_id'],
                    {'persona_id': persona['persona_id'], 'candidate_id': cards[0]['candidate_id']})
    assert response.status_code == 402 and response.json()['error']['code'] == 'PASS_REQUIRED'
    with connect_database(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM simulations').fetchone()[0] == 0


def test_six_candidates_and_diagnosis(tmp_path):
    db = tmp_path / 'diag.sqlite3'
    user = create_user(db, '테스터')
    data = {k: SEEDS[0][k] for k in PersonaData.model_fields}
    data['is_seed'] = False
    persona = create_persona(db, user['user_id'], data)
    cards = call(db, 'GET', f"/api/personas/{persona['persona_id']}/candidates", user['user_id']).json()['candidates']
    assert [c['alias'] for c in cards] == [f'후보 {letter}' for letter in 'ABCDEF']
    comparison = call(db, 'GET', f"/api/personas/{persona['persona_id']}/comparison", user['user_id']).json()
    assert len(comparison['candidates']) == 6

    response = call(db, 'GET', f"/api/personas/{persona['persona_id']}/diagnosis", user['user_id'])
    assert response.status_code == 200
    body = response.json()
    assert body['pool_size'] == len(POOL) and body['level'] in ('good', 'limited', 'hard')
    assert len(body['factors']) == 3 and all(f['label'] and f['summary'] for f in body['factors'])
    assert [f['score_loss'] for f in body['factors']] == sorted((f['score_loss'] for f in body['factors']), reverse=True)
    # 후보 개인 정보(이름 · 소개)는 응답에 포함하지 않는다
    for seed in POOL:
        assert seed['name'] not in response.text and seed['summary'] not in response.text
    assert call(db, 'GET', '/api/personas/per_unknown/diagnosis', user['user_id']).status_code == 404
    assert call(db, 'GET', f"/api/personas/{persona['persona_id']}/diagnosis", None).status_code == 401


def test_diagnosis_explains_hard_profile():
    from app.diagnosis import diagnose
    extreme = {'persona_id': 'per_x', 'user_id': 'usr_x', 'gender': 'female',
               'axes': {'sleep_rhythm': 0, 'noise_sensitivity': 100, 'cleanliness': 100,
                        'sociability': 0, 'sharing_tolerance': 0}}
    result = diagnose(extreme, SEED_PATH)
    assert result['level'] in ('limited', 'hard') and result['good_count'] <= 2
    top = result['factors'][0]
    assert top['tips'] and top['score_loss'] > 0
    adjustment = result['best_adjustment']
    assert adjustment and adjustment['good_after'] > adjustment['good_before']
