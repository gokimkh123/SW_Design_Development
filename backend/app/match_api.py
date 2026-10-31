# 기능: 룸메 신청과 매칭 조회, 생활 규칙 조회·동의 API를 제공한다.
# 시스템 범위: 사용자·소유자 확인과 응답 형식을 담당하며 규칙 초안은 엔진 어댑터로 만든다.
# 결과: 명세의 Match·RuleSet 또는 공통 오류 형식을 반환한다.
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from app import matches as store
from app.engine_adapter import EngineAdapter, get_engine
from app.persona_api import PersonaAPIError
from app.simulations import StorageConflictError
from app.users import get_user


class MatchCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    simulation_id: str = Field(min_length=1)


class Partner(BaseModel):
    persona_id: str
    name: str
    department: str
    year: int
    type_name: str
    greeting: str


class MatchResponse(BaseModel):
    match_id: str
    simulation_id: str
    status: Literal['pending', 'accepted', 'declined']
    partner: Partner | None
    room: str | None
    rules_status: Literal['draft', 'confirmed']


class RuleSource(BaseModel):
    scene_index: int
    day: int
    verdict: Literal['harmonious', 'negotiated', 'conflict', 'pending']


class Rule(BaseModel):
    rule_id: str
    area: Literal['quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies']
    area_label: str
    text: str
    source: RuleSource


class Agreements(BaseModel):
    me: bool
    partner: bool


class RuleSet(BaseModel):
    match_id: str
    status: Literal['draft', 'confirmed']
    rules: list[Rule]
    agreements: Agreements


def create_match_router(database, error_model):
    router = APIRouter(prefix='/api/matches', tags=['matches'])

    def require_user(x_user_id):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')

    def found(value):
        if value is None:
            raise PersonaAPIError(404, 'MATCH_NOT_FOUND', '매칭을 찾을 수 없어요.')
        return value

    def load(simulation_id, x_user_id):
        require_user(x_user_id)
        try:
            loaded = store.load_match_inputs(database, simulation_id, user_id=x_user_id)
        except StorageConflictError:
            raise PersonaAPIError(409, 'SIMULATION_NOT_COMPLETED', '아직 완료되지 않은 시뮬레이션이에요.')
        if loaded is None:
            raise PersonaAPIError(404, 'SIMULATION_NOT_FOUND', '시뮬레이션을 찾을 수 없어요.')
        return loaded, store.get_match_for_simulation(database, simulation_id, user_id=x_user_id)

    def owned(handler, match_id, x_user_id):
        require_user(x_user_id)
        return found(handler(database, match_id, user_id=x_user_id))

    errors = {status: {'model': error_model} for status in (401, 404, 422, 500)}

    @router.post('', status_code=201, response_model=MatchResponse, responses={
        **errors, **{status: {'model': error_model} for status in (409, 429, 503)}})
    async def create(payload: MatchCreate, engine: Annotated[EngineAdapter, Depends(get_engine)],
                     x_user_id: Annotated[str | None, Header()] = None):
        (record, scenes), existing = await run_in_threadpool(load, payload.simulation_id, x_user_id)
        if existing is not None:
            return existing
        # DB 연결을 닫은 상태로 엔진을 호출한다. 실패하면 아무것도 저장하지 않아 다시 신청할 수 있다.
        rules = await store.draft_match_rules(engine, record, scenes)
        return await run_in_threadpool(store.create_match, database, record, rules)

    @router.get('/{match_id}', response_model=MatchResponse, responses=errors)
    def read(match_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return owned(store.get_match, match_id, x_user_id)

    @router.get('/{match_id}/rules', response_model=RuleSet, responses=errors)
    def rules(match_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return owned(store.get_rules, match_id, x_user_id)

    @router.post('/{match_id}/rules/agree', response_model=RuleSet, responses=errors)
    def agree(match_id: str, x_user_id: Annotated[str | None, Header()] = None):
        return owned(store.agree_rules, match_id, x_user_id)

    return router
