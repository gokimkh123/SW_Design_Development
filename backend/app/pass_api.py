# 기능: 가상 동거 이용권 API(API.md 4.18) — 이용 현황 조회 · 이용권 구매.
# 시스템 범위: 베이직 무료 횟수와 구매 횟수를 합산해 남은 횟수를 계산한다. 결제 수단 · 카드 · 연락처는 받지 않는다.
# 결과: 이용 현황(PassSummary)을 반환하며 오류는 공통 형식(401 · 409 · 422)을 따른다.
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Header
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from app import simulations as store
from app.matches import _now
from app.persona_api import PersonaAPIError
from app.simulation_api import FREE_SIMULATIONS
from app.users import get_user

# 상품: (가상 동거 횟수, 가격(원)). 룸메이트는 입사 신청 시기(학기 전)에 한 번 정하므로 월 구독 대신 횟수제로 판매
PRODUCTS = {'pass_5': (5, 2900), 'pass_15': (15, 6900)}
MAX_PURCHASED_CREDITS = 60  # 사용자당 누적 구매 상한(오조작 · 반복 호출 방지)
Product = Literal['pass_5', 'pass_15']


class PassPurchaseCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    product: Product


class PassPurchase(BaseModel):
    purchase_id: str
    product: Product
    credits: int
    price: int
    created_at: str


class PassSummary(BaseModel):
    free_quota: int
    purchased: int
    used: int
    remaining: int
    purchases: list[PassPurchase]


def summary(db_path, user_id):
    with store._connection(db_path) as db:
        used = db.execute("SELECT COUNT(*) FROM simulations WHERE user_id=? AND status != 'failed'",
                          (user_id,)).fetchone()[0]
        rows = db.execute('SELECT purchase_id, product, credits, price, created_at FROM pass_purchases '
                          'WHERE user_id=? ORDER BY created_at DESC, purchase_id', (user_id,)).fetchall()
    purchases = [dict(row) for row in rows if row['product'] in PRODUCTS]
    purchased = sum(row['credits'] for row in rows)
    return {'free_quota': FREE_SIMULATIONS, 'purchased': purchased, 'used': used,
            'remaining': max(0, FREE_SIMULATIONS + purchased - used), 'purchases': purchases}


def purchase(db_path, user_id, product):
    credits, price = PRODUCTS[product]
    with store._connection(db_path, write=True) as db:
        bought = db.execute('SELECT COALESCE(SUM(credits), 0) FROM pass_purchases WHERE user_id=?',
                            (user_id,)).fetchone()[0]
        if bought + credits > MAX_PURCHASED_CREDITS:
            raise PersonaAPIError(409, 'PASS_LIMIT', f'이용권은 한 계정당 최대 {MAX_PURCHASED_CREDITS}회까지 구매할 수 있어요.')
        db.execute('INSERT INTO pass_purchases (purchase_id, user_id, product, credits, price, created_at) '
                   'VALUES (?,?,?,?,?,?)', ('pas_' + secrets.token_hex(8), user_id, product, credits, price, _now()))
    return summary(db_path, user_id)


def create_pass_router(database, error_model):
    router = APIRouter(tags=['passes'])
    errors = {status: {'model': error_model} for status in (401, 422, 500)}

    def require_user(x_user_id):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')

    @router.get('/api/passes/me', response_model=PassSummary, responses=errors)
    async def current(x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(summary, database, x_user_id)

    @router.post('/api/passes', status_code=201, response_model=PassSummary,
                 responses={**errors, 409: {'model': error_model}})
    async def buy(payload: PassPurchaseCreate, x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        return await run_in_threadpool(purchase, database, x_user_id, payload.product)

    return router
