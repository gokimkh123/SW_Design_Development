# 기능: P1 API(API.md 4.16)와 후보 카드의 실행 상태 · 닉네임 익명 충돌 방지를 검증한다.
# 시스템 범위: 임시 SQLite와 가짜 엔진만 사용하며 실제 사용자 DB와 유료 LLM은 접근하지 않는다.
# 결과: 명세 필드, 소유자 격리, 완료 전 409, 제안 수락의 반복 안전성, 메모 원문 미저장을 확인한다.
import asyncio
import json
from pathlib import Path
import re

import httpx

from app import simulations as store
from app.candidates import select_candidates
from app.database import connect_database
from app.engine_adapter import get_engine, load_engine
from app.main import create_app
from app.users import create_user
from test_matches_api import completed
from test_simulations import context, create  # noqa: F401 (pytest fixture)

SEEDS = Path(__file__).resolve().parents[2] / 'data/seed/personas.json'


def request(db, method, path, user, body=None):
    application = create_app(db_path=db)
    application.dependency_overrides[get_engine] = lambda: load_engine('fake')

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            return await client.request(method, path, json=body, headers={'X-User-Id': user} if user else {})
    return asyncio.run(run())


def get(db, path, user):
    return request(db, 'GET', path, user)


def post(db, path, user, body):
    return request(db, 'POST', path, user, body)


def apply(db, sid, user):
    return post(db, '/api/matches', user, {'simulation_id': sid})


def matched(context):
    db, _, user, _ = context
    sid = completed(context)
    match = apply(db, sid, user['user_id']).json()
    rules = get(db, f"/api/matches/{match['match_id']}/rules", user['user_id']).json()
    return sid, match, rules


def test_scenes_replay_requires_completed_owned_run(context):
    db, args, user, _ = context
    running = create(context)
    assert get(db, f'/api/simulations/{running}/scenes', user['user_id']).status_code == 409
    store.fail_simulation(db, running, {'code': 'INTERNAL_ERROR', 'message': '중단', 'retryable': False})
    sid = completed(context)
    response = get(db, f'/api/simulations/{sid}/scenes', user['user_id'])
    assert response.status_code == 200
    scenes = response.json()['scenes']
    assert [s['scene_index'] for s in scenes] == list(range(1, 21))
    assert {'scene', 'dialogue', 'verdict', 'reason', 'agreement', 'rule_candidate', 'unresolved'} <= set(scenes[0])
    assert args['candidate']['name'] not in json.dumps(scenes, ensure_ascii=False)
    other = create_user(db, '다른 사람')['user_id']
    assert get(db, f'/api/simulations/{sid}/scenes', other).status_code == 404
    assert get(db, f'/api/simulations/{sid}/scenes', None).status_code == 401


def test_comparison_uses_simulation_score_when_completed(context):
    db, args, user, persona = context
    before = get(db, f"/api/personas/{persona['persona_id']}/comparison", user['user_id']).json()
    assert set(before) == {'me', 'candidates', 'recommended_candidate_id'}
    assert len(before['candidates']) == 6 and all(c['expected_conflicts_per_month'] is None for c in before['candidates'])
    assert set(before['candidates'][0]) == {'candidate_id', 'alias', 'axes', 'score', 'expected_conflicts_per_month'}
    completed(context)
    after = get(db, f"/api/personas/{persona['persona_id']}/comparison", user['user_id']).json()
    target = next(c for c in after['candidates'] if c['candidate_id'] == args['candidate']['persona_id'])
    assert target['score'] == 80 and target['expected_conflicts_per_month'] is not None
    # 추천은 가상 동거를 마친 후보 우선 (1차 점수가 더 높아도 시뮬레이션 결과를 우선)
    assert before['recommended_candidate_id'] == max(before['candidates'], key=lambda c: c['score'])['candidate_id']
    assert after['recommended_candidate_id'] == target['candidate_id']
    other = create_user(db, '다른 사람')['user_id']
    assert get(db, f"/api/personas/{persona['persona_id']}/comparison", other).status_code == 404


def test_candidates_report_latest_simulation_status(context):
    db, args, user, persona = context
    sid = completed(context)
    cards = get(db, f"/api/personas/{persona['persona_id']}/candidates", user['user_id']).json()['candidates']
    card = next(c for c in cards if c['candidate_id'] == args['candidate']['persona_id'])
    assert card['simulation'] == {'simulation_id': sid, 'status': 'completed',
                                  'progress': {'done': 20, 'total': 20}, 'score': 80}
    assert all(c['simulation'] is None for c in cards if c is not card)


def test_rule_proposal_mediation_and_accept(context):
    db, args, user, _ = context
    _, match, rules = matched(context)
    rule = rules['rules'][0]
    response = post(db, f"/api/rules/{rule['rule_id']}/proposals", user['user_id'],
                    {'text': '시험 기간엔 22:30부터 조용히', 'reason': '실습 평가 주간이라 일찍 자야 해서'})
    assert response.status_code == 201
    proposal = response.json()
    assert re.fullmatch(r'prp_[a-z0-9]{8}', proposal['proposal_id']) and proposal['rule_id'] == rule['rule_id']
    assert proposal['mediation']['text'].startswith('시험 기간엔 22:30부터 조용히')
    assert 1 <= len(proposal['mediation']['rationale']) <= 4
    assert '후보 A' not in json.dumps(proposal, ensure_ascii=False)

    other = create_user(db, '다른 사람')['user_id']
    assert post(db, f"/api/proposals/{proposal['proposal_id']}/accept", other, None).status_code == 404
    accepted = post(db, f"/api/proposals/{proposal['proposal_id']}/accept", user['user_id'], None)
    assert accepted.status_code == 200
    assert accepted.json() == dict(rule, text=proposal['mediation']['text'])
    again = post(db, f"/api/proposals/{proposal['proposal_id']}/accept", user['user_id'], None)
    assert again.json() == accepted.json()
    current = get(db, f"/api/matches/{match['match_id']}/rules", user['user_id']).json()
    assert current['rules'][0]['text'] == proposal['mediation']['text']

    assert post(db, f"/api/rules/{rule['rule_id']}/proposals", other, {'text': '변경', 'reason': '이유'}).status_code == 404
    assert post(db, f"/api/rules/{rule['rule_id']}/proposals", user['user_id'],
                {'text': '   ', 'reason': '이유'}).status_code == 422


def test_rephrase_returns_request_without_storing_memo(context):
    db, _, user, _ = context
    _, match, _ = matched(context)
    memo = '새벽마다 알람을 다섯 번씩 끄고 다시 자서 너무 짜증나 비밀메모'
    response = post(db, '/api/mediation/rephrase', user['user_id'], {'match_id': match['match_id'], 'memo': memo})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'message', 'suggested_rule'} and body['suggested_rule']['area'] == 'quiet_hours'
    assert '비밀메모' not in body['message']
    with connect_database(db) as conn:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        dump = json.dumps([conn.execute(f'SELECT * FROM {t}').fetchall() for t in tables], ensure_ascii=False)
    assert '비밀메모' not in dump
    other = create_user(db, '다른 사람')['user_id']
    assert post(db, '/api/mediation/rephrase', other, {'match_id': match['match_id'], 'memo': memo}).status_code == 404


def test_nickname_containing_candidate_name_excludes_that_candidate():
    seeds = json.loads(SEEDS.read_text(encoding='utf-8'))['personas']
    daeun = next(s for s in seeds if s['persona_id'] == 'per_daeun')
    me = {'persona_id': 'per_visitor', 'user_id': 'usr_visitor', 'axes': dict(daeun['axes'])}
    assert 'per_daeun' in [c.candidate_id for c in select_candidates(dict(me, nickname='하늘'), SEEDS).candidates]
    assert 'per_daeun' not in [c.candidate_id for c in select_candidates(dict(me, nickname='다은이'), SEEDS).candidates]
