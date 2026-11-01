# 기능: 멤버십 사전 구독 신청 API(API.md 4.17) — 조회 · 신청(변경) · 취소.
# 시스템 범위: 결제 · 카드 · 연락처를 받지 않고, 사용자 ID별 선택 플랜(plus_monthly · plus_semester · dorm)만 저장한다.
# 결과: {plan, updated_at}을 반환하며 미신청 · 취소 상태는 plan이 null이다. 오류는 공통 형식(401 · 422)을 따른다.
from typing import Annotated, Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app import simulations as store
from app.matches import _now
from app.persona_api import PersonaAPIError
from app.users import get_user

Plan = Literal['plus_monthly', 'plus_semester', 'dorm']


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    plan: Plan


class Subscription(BaseModel):
    plan: Plan | None
    updated_at: str | None


def get_intent(db_path, user_id):
    with store._connection(db_path) as db:
        row = db.execute('SELECT plan, updated_at FROM subscription_intents WHERE user_id=?', (user_id,)).fetchone()
    return {'plan': row['plan'], 'updated_at': row['updated_at']} if row else {'plan': None, 'updated_at': None}


def save_intent(db_path, user_id, plan):
    now = _now()
    with store._connection(db_path, write=True) as db:
        db.execute('INSERT INTO subscription_intents (user_id, plan, created_at, updated_at) VALUES (?,?,?,?) '
                   'ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan, updated_at=excluded.updated_at',
                   (user_id, plan, now, now))
    return {'plan': plan, 'updated_at': now}


def delete_intent(db_path, user_id):
    with store._connection(db_path, write=True) as db:
        db.execute('DELETE FROM subscription_intents WHERE user_id=?', (user_id,))
    return {'plan': None, 'updated_at': None}


def create_subscription_router(database, error_model):
    router = APIRouter(tags=['subscriptions'])
    errors = {status: {'model': error_model} for status in (401, 422, 500)}

    def require_user(x_user_id):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')

    @router.get('/api/subscriptions/me', response_model=Subscription, responses=errors)
    async def current(x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(get_intent, database, x_user_id)

    @router.put('/api/subscriptions/me', response_model=Subscription, responses=errors)
    async def apply(payload: SubscriptionUpdate, x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(save_intent, database, x_user_id, payload.plan)

    @router.delete('/api/subscriptions/me', response_model=Subscription, responses=errors)
    async def cancel(x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(delete_intent, database, x_user_id)

    return router
