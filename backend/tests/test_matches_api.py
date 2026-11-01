# 기능: 매칭 신청·조회와 생활 규칙 조회·동의의 명세·접근 제어·실패 처리를 검증한다.
# 시스템 범위: 임시 SQLite와 가짜 엔진만 사용하며 실제 사용자 DB와 유료 LLM은 접근하지 않는다.
# 결과: API.md 필드 일치, 소유자 격리, 재신청·동시 신청, 실패 시 무저장을 확인한다.
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import re

import httpx
import pytest

from app import matches as match_store, simulations as store
from app.database import connect_database
from app.engine_adapter import EngineError, get_engine, load_engine
from app.main import create_app
from app.users import create_user
from test_simulations import context, create, finish_scenes

MATCH_KEYS = {'match_id', 'simulation_id', 'status', 'partner', 'room', 'rules_status'}
PARTNER_KEYS = {'persona_id', 'name', 'department', 'year', 'type_name', 'greeting'}
RULE_KEYS = {'rule_id', 'area', 'area_label', 'text', 'source'}
AREAS = ['quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies']


class CountingEngine:
    """가짜 엔진 호출 횟수와 입력을 기록한다. 대체 동작을 주면 draft_rules만 바꾼다."""

    def __init__(self, draft=None):
        self.real, self.draft, self.calls = load_engine('fake'), draft, []

    async def draft_rules(self, me, candidate, judgements):
        self.calls.append((me, candidate, judgements))
        await asyncio.sleep(0)
        if self.draft:
            return await self.draft(me, candidate, judgements)
        return await self.real.draft_rules(me, candidate, judgements)


def api(db, calls, engine=None):
    """같은 앱에서 요청을 동시에 보낸다. calls: [(method, path, user, json), ...]"""
    application = create_app(db_path=db)
    application.dependency_overrides[get_engine] = lambda: engine or CountingEngine()

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(
                app=application, raise_app_exceptions=False), base_url='http://test') as client:
            return await asyncio.gather(*(client.request(
                method, path, json=body, headers={'X-User-Id': user} if user else {})
                for method, path, user, body in calls))
    return asyncio.run(run())


def apply(db, sid, user, engine=None):
    return api(db, [('POST', '/api/matches', user, {'simulation_id': sid})], engine)[0]


def get(db, path, user):
    return api(db, [('GET', path, user, None)])[0]


def completed(context, *, candidate=None, alias='후보 A'):
    db, args, *_ = context
    params = dict(args, candidate=candidate or args['candidate'], alias=alias)
    sim, _ = store.create_or_reuse_simulation(db, **params)
    sid = sim['simulation_id']
    finish_scenes(db, sid)
    store.complete_simulation(db, sid, score=80, headline='몇 가지만 맞추면 잘 지낼 수 있어요')
    return sid


def counts(db):
    with connect_database(db) as conn:
        return tuple(conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('matches', 'rules'))


def seed(persona_id):
    seeds = json.loads((Path(__file__).resolve().parents[2] / 'data/seed/personas.json')
                       .read_text(encoding='utf-8'))['personas']
    return deepcopy(next(s for s in seeds if s['persona_id'] == persona_id))


def test_apply_returns_accepted_match_with_partner(context):
    db, args, user, _ = context
    sid = completed(context)
    response = apply(db, sid, user['user_id'])
    body = response.json()
    assert response.status_code == 201
    assert set(body) == MATCH_KEYS and set(body['partner']) == PARTNER_KEYS
    assert re.fullmatch(r'mat_[a-z0-9]{8}', body['match_id'])
    candidate = args['candidate']
    assert body['simulation_id'] == sid and body['status'] == 'accepted' and body['rules_status'] == 'draft'
    assert body['room'] == '302호 (배정 예정)'
    assert body['partner'] == {k: candidate[k] for k in PARTNER_KEYS}
    assert body['partner']['name'] == '다은'

    read = get(db, f"/api/matches/{body['match_id']}", user['user_id'])
    assert read.status_code == 200 and read.json() == body


def test_rule_set_contract_and_source_from_stored_scenes(context):
    db, _, user, _ = context
    sid = completed(context)
    match_id = apply(db, sid, user['user_id']).json()['match_id']
    body = get(db, f'/api/matches/{match_id}/rules', user['user_id']).json()
    assert set(body) == {'match_id', 'status', 'rules', 'agreements'}
    assert body['match_id'] == match_id and body['status'] == 'draft'
    assert body['agreements'] == {'me': False, 'partner': False}
    assert [r['area'] for r in body['rules']] == AREAS
    assert [r['area_label'] for r in body['rules']] == ['조용한 시간', '친구 초대', '청소', '냉장고', '냉난방', '공용품']

    scenes = {s['scene_index']: s for s in store.list_scenes(db, sid)}
    for rule in body['rules']:
        assert set(rule) == RULE_KEYS and set(rule['source']) == {'scene_index', 'day', 'verdict'}
        assert re.fullmatch(r'rul_[a-z0-9]{8}', rule['rule_id'])
        stored = scenes[rule['source']['scene_index']]
        assert rule['source']['day'] == stored['scene']['day']
        assert rule['source']['verdict'] == stored['verdict']


def test_agree_confirms_with_seed_partner_and_is_repeatable(context):
    db, _, user, _ = context
    match_id = apply(db, completed(context), user['user_id']).json()['match_id']
    path = f'/api/matches/{match_id}/rules/agree'
    first = api(db, [('POST', path, user['user_id'], None)])[0]
    second = api(db, [('POST', path, user['user_id'], None)])[0]
    assert first.status_code == 200
    assert first.json()['status'] == 'confirmed'
    assert first.json()['agreements'] == {'me': True, 'partner': True}
    assert second.json() == first.json()
    assert len(first.json()['rules']) == 6
    assert get(db, f'/api/matches/{match_id}', user['user_id']).json()['rules_status'] == 'confirmed'


def test_reapply_returns_same_match_without_engine_call(context):
    db, _, user, _ = context
    sid = completed(context)
    engine = CountingEngine()
    first, second = apply(db, sid, user['user_id'], engine), apply(db, sid, user['user_id'], engine)
    assert (first.status_code, second.status_code) == (201, 201)
    assert second.json() == first.json()
    assert len(engine.calls) == 1 and counts(db) == (1, 6)


def test_concurrent_apply_creates_one_match(context):
    db, _, user, _ = context
    sid = completed(context)
    call = ('POST', '/api/matches', user['user_id'], {'simulation_id': sid})
    responses = api(db, [call, call, call])
    assert {r.status_code for r in responses} == {201}
    assert len({r.json()['match_id'] for r in responses}) == 1
    assert counts(db) == (1, 6)


def test_rule_ids_are_unique_across_matches(context):
    db, _, user, _ = context
    first = apply(db, completed(context), user['user_id']).json()['match_id']
    other = completed(context, candidate=seed('per_jiho'), alias='후보 B')
    second = apply(db, other, user['user_id']).json()['match_id']
    ids = [r['rule_id'] for m in (first, second)
           for r in get(db, f'/api/matches/{m}/rules', user['user_id']).json()['rules']]
    assert first != second and len(set(ids)) == 12


def test_engine_gets_anonymous_snapshot_and_rule_text_uses_partner_name(context):
    db, args, user, _ = context
    sid = completed(context)

    async def draft(me, candidate, judgements):
        rules = await load_engine('fake').draft_rules(me, candidate, judgements)
        rules[0]['text'] = f"{candidate['nickname']}와 23시 이후 조용히"
        return rules

    engine = CountingEngine(draft)
    match_id = apply(db, sid, user['user_id'], engine).json()['match_id']
    me, candidate, judgements = engine.calls[0]
    assert candidate['nickname'] == '후보 A' and '다은' not in repr((me, candidate, judgements))
    assert 'name' not in candidate and len(judgements) == 20
    assert {'scene_index', 'scene_id', 'verdict', 'reason', 'agreement', 'rule_candidate',
            'unresolved'} == set(judgements[0])
    rules = get(db, f'/api/matches/{match_id}/rules', user['user_id']).json()['rules']
    assert rules[0]['text'] == '다은와 23시 이후 조용히'


def test_user_required_on_every_endpoint(context):
    db, *_ = context
    calls = [('POST', '/api/matches', {'simulation_id': 'sim_x'}), ('GET', '/api/matches/mat_x', None),
             ('GET', '/api/matches/mat_x/rules', None), ('POST', '/api/matches/mat_x/rules/agree', None)]
    for user in (None, 'usr_unknown'):
        for response in api(db, [(m, p, user, b) for m, p, b in calls]):
            assert response.status_code == 401
            assert response.json()['error']['code'] == 'USER_REQUIRED'


def test_other_users_data_is_hidden(context):
    db, _, user, _ = context
    sid = completed(context)
    match_id = apply(db, sid, user['user_id']).json()['match_id']
    other = create_user(db, '다른 사람')['user_id']

    response = apply(db, sid, other)
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'SIMULATION_NOT_FOUND'
    for method, path in (('GET', f'/api/matches/{match_id}'), ('GET', f'/api/matches/{match_id}/rules'),
                         ('POST', f'/api/matches/{match_id}/rules/agree')):
        response = api(db, [(method, path, other, None)])[0]
        assert response.status_code == 404
        assert response.json()['error']['code'] == 'MATCH_NOT_FOUND'
    assert get(db, f'/api/matches/{match_id}/rules', user['user_id']).json()['agreements']['me'] is False


def test_missing_targets_return_not_found(context):
    db, _, user, _ = context
    assert apply(db, 'sim_missing', user['user_id']).json()['error']['code'] == 'SIMULATION_NOT_FOUND'
    for path in ('/api/matches/mat_missing', '/api/matches/mat_missing/rules'):
        response = get(db, path, user['user_id'])
        assert response.status_code == 404 and response.json()['error']['code'] == 'MATCH_NOT_FOUND'


def test_incomplete_simulation_returns_409(context):
    db, _, user, _ = context
    sid = create(context)
    response = apply(db, sid, user['user_id'])
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'SIMULATION_NOT_COMPLETED'
    store.fail_simulation(db, sid, {'code': 'INTERNAL_ERROR', 'message': '실패', 'retryable': False})
    assert apply(db, sid, user['user_id']).status_code == 409
    assert counts(db) == (0, 0)


@pytest.mark.parametrize('body', [{}, {'simulation_id': ''}, {'simulation_id': 1}, {'simulation_id': 's', 'x': 1}])
def test_invalid_body_returns_validation_error(context, body):
    db, _, user, _ = context
    response = api(db, [('POST', '/api/matches', user['user_id'], body)])[0]
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert '닉네임' not in response.json()['error']['message']


@pytest.mark.parametrize('code, status', [('LLM_UNAVAILABLE', 503), ('LLM_RATE_LIMITED', 429)])
def test_engine_failure_saves_nothing_and_allows_retry(context, code, status):
    db, _, user, _ = context
    sid = completed(context)

    async def fail(*_):
        raise EngineError(code, status, '실패', retryable=True)

    response = apply(db, sid, user['user_id'], CountingEngine(fail))
    assert response.status_code == status and response.json()['error']['code'] == code
    assert counts(db) == (0, 0)
    assert apply(db, sid, user['user_id']).status_code == 201


def test_slow_engine_times_out_as_unavailable(context, monkeypatch):
    db, _, user, _ = context
    sid = completed(context)
    monkeypatch.setattr(match_store, 'DRAFT_TIMEOUT_SECONDS', 0.01)

    async def slow(*_):
        await asyncio.sleep(5)

    response = apply(db, sid, user['user_id'], CountingEngine(slow))
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'LLM_UNAVAILABLE'
    assert counts(db) == (0, 0)


def _break(rules, kind):
    if kind == 'missing_area':
        return rules[:5]
    if kind == 'duplicate_area':
        return [rules[0], *rules[:5]]
    if kind == 'empty_text':
        rules[0]['text'] = ' '
    if kind == 'unknown_scene':
        rules[0]['source']['scene_index'] = 99
    return rules


@pytest.mark.parametrize('kind', ['missing_area', 'duplicate_area', 'empty_text', 'unknown_scene'])
def test_invalid_rule_drafts_are_rejected(context, kind):
    db, _, user, _ = context
    sid = completed(context)

    async def broken(me, candidate, judgements):
        return _break(await load_engine('fake').draft_rules(me, candidate, judgements), kind)

    response = apply(db, sid, user['user_id'], CountingEngine(broken))
    assert response.status_code == 500
    assert response.json()['error']['code'] == 'INTERNAL_ERROR'
    assert counts(db) == (0, 0)


def test_tables_are_added_to_existing_database_and_initialization_repeats(context):
    db, _, user, _ = context
    with connect_database(db) as conn:
        conn.execute('DROP TABLE rules')
        conn.execute('DROP TABLE matches')
    sid = completed(context, candidate=seed('per_jiho'), alias='후보 B')
    assert apply(db, sid, user['user_id']).status_code == 201
    assert counts(db) == (1, 6)
