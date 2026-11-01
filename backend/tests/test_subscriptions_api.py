# 기능: 멤버십 사전 구독 신청 API(API.md 4.17)의 조회 · 신청 · 변경 · 취소와 오류 응답을 검증한다.
# 시스템 범위: 임시 SQLite만 사용하며 결제 · 외부 서비스는 호출하지 않는다.
# 결과: 사용자별 플랜 1건만 저장되고, 다른 사용자와 격리되며, 결제 · 연락처 필드는 받지 않음을 확인한다.
import asyncio

import httpx

from app.database import connect_database
from app.main import create_app
from app.users import create_user


def call(db, method, user, body=None):
    application = create_app(db_path=db)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
                                     base_url='http://test') as client:
            return await client.request(method, '/api/subscriptions/me', json=body,
                                        headers={'X-User-Id': user} if user else {})
    return asyncio.run(run())


def test_subscription_lifecycle_and_isolation(tmp_path):
    db = tmp_path / 'users.sqlite3'
    me = create_user(db, '하늘')['user_id']
    other = create_user(db, '다른 사람')['user_id']

    empty = call(db, 'GET', me)
    assert empty.status_code == 200 and empty.json() == {'plan': None, 'updated_at': None}

    first = call(db, 'PUT', me, {'plan': 'plus_semester'})
    assert first.status_code == 200 and first.json()['plan'] == 'plus_semester' and first.json()['updated_at']
    changed = call(db, 'PUT', me, {'plan': 'plus_monthly'})
    assert changed.json()['plan'] == 'plus_monthly'
    assert call(db, 'GET', me).json()['plan'] == 'plus_monthly'
    assert call(db, 'GET', other).json()['plan'] is None
    with connect_database(db) as conn:
        assert conn.execute('SELECT COUNT(*) FROM subscription_intents').fetchone()[0] == 1

    cancelled = call(db, 'DELETE', me)
    assert cancelled.status_code == 200 and cancelled.json() == {'plan': None, 'updated_at': None}
    assert call(db, 'GET', me).json()['plan'] is None
    assert call(db, 'DELETE', me).status_code == 200  # 반복 취소도 안전


def test_subscription_errors(tmp_path):
    db = tmp_path / 'users.sqlite3'
    me = create_user(db, '하늘')['user_id']
    for method, body in (('GET', None), ('PUT', {'plan': 'dorm'}), ('DELETE', None)):
        response = call(db, method, None, body)
        assert response.status_code == 401 and response.json()['error']['code'] == 'USER_REQUIRED'
    assert call(db, 'GET', 'usr_unknown').status_code == 401
    for body in ({'plan': 'premium'}, {'plan': 'dorm', 'card_number': '1234'}, {}, {'plan': 1}):
        response = call(db, 'PUT', me, body)
        assert response.status_code == 422 and response.json()['error']['code'] == 'VALIDATION_ERROR'
    assert call(db, 'GET', me).json()['plan'] is None
