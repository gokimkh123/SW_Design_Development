# 기능: 완료 리포트의 명세·접근 제어·손상 감지·읽기 전용 동작을 검증한다.
# 시스템 범위: 임시 SQLite와 가짜 엔진만 사용하며 실제 사용자 DB와 유료 LLM은 접근하지 않는다.
# 결과: API 전체 흐름과 저장 결과의 점수·집계·순서·익명성을 확인한다.
import asyncio
import json

import httpx
import pytest

from app import simulations as store, fake_engine
from app.database import connect_database
from app.engine_adapter import get_engine, load_engine
from app.main import create_app
from app.users import create_user
from conftest import HANEUL_ANSWERS
from test_simulations import context, create, engine_events


def request(db, sid, user=None, app=None):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
                app=app or create_app(db_path=db), raise_app_exceptions=False), base_url='http://test') as client:
            return await client.get(f'/api/simulations/{sid}/report',
                                    headers={'X-User-Id': user} if user else {})
    return asyncio.run(run())


def completed(context):
    db, args, *_ = context
    sid = create(context)
    store.start_simulation(db, sid)
    for event in engine_events(db, sid):
        if event['type'] == 'scene_judged':
            index = event['data']['scene_index']
            event['data']['verdict'] = store.VERDICTS[(index - 1) % 4]
            event['data']['agreement'] = None if index == 3 else args['candidate']['nickname'] + ' 합의'
        store.save_event(db, sid, event)
    store.complete_simulation(db, sid, score=73, headline='저장된 판정', report={'private': 'internal-secret'})
    return sid


def test_report_contract_snapshot_privacy_and_read_only(context, monkeypatch):
    db, args, *_ = context
    sid = completed(context)
    def forbidden(*args, **kwargs):
        raise AssertionError('리포트 조회가 엔진이나 저장 함수를 호출했습니다.')
    for name in ('simulate', 'score', 'headline', 'load_scenes'):
        monkeypatch.setattr(fake_engine, name, forbidden)
    for name in ('complete_simulation', 'save_event', 'start_simulation', 'create_or_reuse_simulation'):
        monkeypatch.setattr(store, name, forbidden)
    app = create_app(db_path=db, seed_path=db.parent / 'missing-seeds.json')
    app.dependency_overrides[get_engine] = forbidden
    before = db.read_bytes()
    responses = [request(db, sid, args['user_id'], app) for _ in range(3)]
    assert all(r.status_code == 200 for r in responses)
    assert db.read_bytes() == before
    assert responses[0].json() == responses[1].json() == responses[2].json()
    data = responses[0].json()
    assert set(data) == {'simulation_id', 'candidate', 'score', 'headline', 'verdict_counts',
                         'scene_verdicts', 'highlights', 'expected_conflicts_per_month'}
    assert data['score'] == 73 and data['headline'] == '저장된 판정'
    assert data['candidate'] == {'candidate_id': args['candidate']['persona_id'],
                                'alias': '후보 A', 'type_name': args['candidate']['type_name']}
    assert data['verdict_counts'] == dict.fromkeys(store.VERDICTS, 5)
    assert data['scene_verdicts'] == list(store.VERDICTS) * 5
    assert [h['scene_index'] for h in data['highlights']] == [3, 7, 11, 15, 19, 2, 6, 10, 14, 18]
    assert data['highlights'][0]['agreement'] is None
    assert data['highlights'][1]['agreement'] == '후보 A 합의'
    assert data['expected_conflicts_per_month'] is None
    for highlight in data['highlights']:
        scene = args['scenes'][highlight['scene_index'] - 1]
        assert highlight['title'] == scene['title'] and highlight['day'] == scene['day']
    for secret in ('internal-secret', 'engine_inputs', 'user_id', 'nickname', 'reason', 'dialogue',
                   args['candidate']['name'], args['candidate']['nickname']):
        assert secret not in responses[0].text
    schema = app.openapi()['paths']['/api/simulations/{simulation_id}/report']['get']
    assert {'200', '401', '404', '409', '500'} <= schema['responses'].keys()


@pytest.mark.parametrize('state', ['queued', 'running', 'failed', 'completed'])
def test_access_and_states(context, state):
    db, args, *_ = context
    sid = completed(context) if state == 'completed' else create(context)
    if state == 'queued':
        with connect_database(db) as conn:
            conn.execute("UPDATE simulations SET status='queued' WHERE simulation_id=?", (sid,))
    elif state == 'failed':
        store.fail_simulation(db, sid, dict(code='INTERNAL_ERROR', message='internal-secret', retryable=False))
    other = create_user(db, '타인')['user_id']
    before = db.read_bytes()
    for user, target, status, code in [
        (None, sid, 401, 'USER_REQUIRED'), ('missing', sid, 401, 'USER_REQUIRED'),
        (other, sid, 404, 'SIMULATION_NOT_FOUND'),
        (args['user_id'], 'missing', 404, 'SIMULATION_NOT_FOUND'),
    ]:
        r = request(db, target, user)
        assert r.status_code == status and r.json()['error']['code'] == code
    r = request(db, sid, args['user_id'])
    assert r.status_code == (200 if state == 'completed' else 409)
    if state != 'completed':
        assert r.json()['error']['code'] == 'SIMULATION_NOT_COMPLETED'
    assert 'internal-secret' not in r.text
    assert db.read_bytes() == before


@pytest.mark.parametrize('damage', ['json', 'score_missing', 'score_bool', 'score_range', 'headline',
    'counts', 'count_bool', 'missing_scene', 'missing_judgement', 'verdict', 'agreement', 'index', 'scene_id', 'snapshot'])
def test_corrupt_completion_is_not_fabricated(context, damage):
    db, args, *_ = context
    sid = completed(context)
    with connect_database(db) as conn:
        result = store.get_completion(db, sid)
        if damage in ('json', 'score_missing', 'score_bool', 'score_range', 'headline', 'counts', 'count_bool'):
            if damage == 'score_missing':
                del result['score']
            elif damage == 'score_bool':
                result['score'] = True
            elif damage == 'score_range':
                result['score'] = 101
            elif damage == 'headline':
                result['headline'] = None
            elif damage == 'counts':
                result['verdict_counts']['pending'] = 0
            elif damage == 'count_bool':
                result['verdict_counts']['pending'] = True
            conn.execute('UPDATE simulations SET result=? WHERE simulation_id=?',
                         ('{' if damage == 'json' else json.dumps(result), sid))
        elif damage == 'missing_scene':
            conn.execute('DELETE FROM simulation_scenes WHERE simulation_id=? AND scene_index=5', (sid,))
        elif damage == 'snapshot':
            conn.execute("UPDATE simulations SET inputs='{}' WHERE simulation_id=?", (sid,))
        else:
            judgement = json.loads(conn.execute('SELECT judgement FROM simulation_scenes WHERE simulation_id=? AND scene_index=1', (sid,)).fetchone()[0])
            if damage == 'verdict':
                judgement['verdict'] = 'unknown'
            elif damage == 'agreement':
                del judgement['agreement']
            elif damage == 'index':
                judgement['scene_index'] = 2
            elif damage == 'scene_id':
                judgement['scene_id'] = 'different'
            conn.execute('UPDATE simulation_scenes SET judgement=? WHERE simulation_id=? AND scene_index=1',
                         (None if damage == 'missing_judgement' else json.dumps(judgement), sid))
    before = db.read_bytes()
    r = request(db, sid, args['user_id'])
    assert r.status_code == 500 and r.json()['error']['code'] == 'INTERNAL_ERROR'
    assert 'internal-secret' not in r.text
    assert db.read_bytes() == before


def test_full_fake_engine_api_flow(tmp_path):
    async def run():
        db = tmp_path / 'flow.db'
        app = create_app(db_path=db)
        app.dependency_overrides[get_engine] = lambda: load_engine('fake')
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                r = await client.post('/api/users', json={'nickname': '테스터'})
                assert r.status_code == 201
                headers = {'X-User-Id': r.json()['user_id']}
                r = await client.post('/api/personas', headers=headers, json={'answers': HANEUL_ANSWERS})
                assert r.status_code == 201
                pid = r.json()['persona_id']
                r = await client.get(f'/api/personas/{pid}/candidates', headers=headers)
                assert r.status_code == 200
                card = r.json()['candidates'][0]
                r = await client.post('/api/simulations', headers=headers,
                    json={'persona_id': pid, 'candidate_id': card['candidate_id']})
                assert r.status_code == 202
                sid = r.json()['simulation_id']
                await asyncio.gather(*list(app.state.simulation_runner.tasks))
                r = await client.get(f'/api/simulations/{sid}/report', headers=headers)
                assert r.status_code == 200
                report = r.json()
                saved = store.get_completion(db, sid)
                assert report['score'] == saved['score']
                assert report['headline'] == saved['headline']
                assert report['verdict_counts'] == saved['verdict_counts']
                assert len(report['scene_verdicts']) == 20
                status = await client.get(f'/api/simulations/{sid}', headers=headers)
                assert status.json()['status'] == 'completed'
                assert status.json()['score'] == report['score']
                events = store.list_events(db, sid)
                assert events[-1]['data']['score'] == report['score']
    asyncio.run(asyncio.wait_for(run(), 10))
