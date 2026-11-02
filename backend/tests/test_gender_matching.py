# 기능: 동성 룸메이트 매칭 — 사용자 성별 저장과 후보 · 비교 · 진단 · 시뮬레이션 시작의 같은 성별 제한을 검증한다.
# 시스템 범위: 임시 SQLite와 실제 시드 후보(여 10 · 남 10)를 사용하며 엔진 실행 결과는 확인하지 않는다.
# 결과: 남학생은 남학생 후보만, 여학생은 여학생 후보만 받고, 다른 성별 후보로는 가상 동거를 시작할 수 없음을 확인한다.
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.main import create_app
from conftest import HANEUL_ANSWERS

SEEDS = json.loads((Path(__file__).resolve().parents[2] / 'data/seed/personas.json').read_text(encoding='utf-8'))['personas']
GENDER = {p['persona_id']: p['gender'] for p in SEEDS}


@pytest.fixture
def call(tmp_path, monkeypatch):
    monkeypatch.setenv('ENGINE_IMPL', 'fake')
    application = create_app(db_path=tmp_path / 'gender.sqlite3')

    def request(method, path, user=None, body=None):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                                         base_url='http://test') as client:
                return await client.request(method, path, json=body, headers={'X-User-Id': user} if user else {})
        return asyncio.run(run())
    return request


def setup_user(call, gender):
    body = {'nickname': '테스터', **({'gender': gender} if gender else {})}
    created = call('POST', '/api/users', body=body)
    assert created.status_code == 201
    assert created.json().get('gender') == gender
    user = created.json()['user_id']
    persona = call('POST', '/api/personas', user, {'answers': HANEUL_ANSWERS})
    assert persona.status_code == 201
    return user, persona.json()['persona_id']


@pytest.mark.parametrize('gender', ['male', 'female'])
def test_same_gender_candidates_comparison_and_diagnosis(call, gender):
    user, pid = setup_user(call, gender)
    cards = call('GET', f'/api/personas/{pid}/candidates', user).json()['candidates']
    assert len(cards) == 6 and {GENDER[c['candidate_id']] for c in cards} == {gender}
    comparison = call('GET', f'/api/personas/{pid}/comparison', user).json()['candidates']
    assert {GENDER[c['candidate_id']] for c in comparison} == {gender}
    diagnosis = call('GET', f'/api/personas/{pid}/diagnosis', user).json()
    assert diagnosis['pool_size'] == 10


def test_cannot_start_with_other_gender_candidate(call):
    user, pid = setup_user(call, 'male')
    female = next(p['persona_id'] for p in SEEDS if p['candidate_pool'] and p['gender'] == 'female')
    response = call('POST', '/api/simulations', user, {'persona_id': pid, 'candidate_id': female})
    assert response.status_code == 404 and response.json()['error']['code'] == 'PERSONA_NOT_FOUND'


def test_user_without_gender_keeps_previous_behavior(call):
    user, pid = setup_user(call, None)
    cards = call('GET', f'/api/personas/{pid}/candidates', user).json()['candidates']
    assert len(cards) == 6  # 성별 미입력 기존 사용자: 성별 필터 없이 점수 상위 6명


def test_invalid_gender_rejected(call):
    for gender in ('other', 'M', 1):
        response = call('POST', '/api/users', body={'nickname': '테스터', 'gender': gender})
        assert response.status_code == 422
