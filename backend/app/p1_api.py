# 기능: P1 화면용 API(API.md 4.16) — 장면별 대화 다시 보기, 후보 비교, 규칙 수정 제안 · 수락, 불편 문장 변환.
# 시스템 범위: 소유자 확인 후 기존 저장소 · 엔진 어댑터를 호출하며, 엔진 호출 중에는 DB 연결을 열어 두지 않는다.
# 결과: 명세 응답 또는 공통 오류 형식(401 · 404 · 409 · 422 · 503)을 반환한다. 불편 메모 원문은 저장 · 기록하지 않는다.
import asyncio
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app import matches as match_store, simulations as sim_store
from app.candidates import select_candidates
from app.engine_adapter import EngineAdapter, EngineError, get_engine
from app.persona_api import PersonaAPIError
from app.personas import get_persona
from app.simulation_report import expected_conflicts
from app.users import get_user

ENGINE_TIMEOUT_SECONDS = 10
AREAS = ('quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies')


def _text(min_len: int, max_len: int):
    return Annotated[str, Field(min_length=min_len, max_length=max_len)]


class _Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')

    @field_validator('*', mode='after')
    @classmethod
    def _not_blank(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError('빈 문구는 보낼 수 없어요.')
        return value


class ProposalCreate(_Strict):
    text: _text(1, 100)
    reason: _text(1, 200)


class RephraseCreate(_Strict):
    match_id: _text(1, 40)
    memo: _text(1, 500)


class Mediation(BaseModel):
    text: str = Field(min_length=1)
    rationale: list[str] = Field(min_length=1, max_length=4)


class SuggestedRule(BaseModel):
    area: Literal['quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies']
    text: str = Field(min_length=1)


class Rephrased(BaseModel):
    message: str = Field(min_length=1)
    suggested_rule: SuggestedRule


async def _engine_call(coroutine):
    try:
        return await asyncio.wait_for(coroutine, ENGINE_TIMEOUT_SECONDS)
    except TimeoutError:
        raise EngineError('LLM_UNAVAILABLE', 503, 'AI 연결에 실패했어요. 잠시 후 다시 시도해 주세요.', retryable=True) from None


def _named(value, alias, name):
    """매칭 후 화면이므로 엔진 결과의 별칭(후보 A)을 상대 이름으로 표시한다."""
    if isinstance(value, str):
        return value.replace(alias, name)
    if isinstance(value, list):
        return [_named(item, alias, name) for item in value]
    if isinstance(value, dict):
        return {key: _named(item, alias, name) for key, item in value.items()}
    return value


def create_p1_router(database, seeds, error_model):
    router = APIRouter(tags=['p1'])
    errors = {status: {'model': error_model} for status in (401, 404, 422, 500)}

    def require_user(x_user_id):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')

    @router.get('/api/simulations/{simulation_id}/scenes', responses={**errors, 409: {'model': error_model}})
    def scenes(simulation_id: str, x_user_id: Annotated[str | None, Header()] = None):
        require_user(x_user_id)
        simulation = sim_store.get_simulation(database, simulation_id, user_id=x_user_id)
        if simulation is None:
            raise PersonaAPIError(404, 'SIMULATION_NOT_FOUND', '시뮬레이션을 찾을 수 없어요.')
        if simulation['status'] != 'completed':
            raise PersonaAPIError(409, 'SIMULATION_NOT_COMPLETED', '아직 완료되지 않은 시뮬레이션이에요.')
        return {'scenes': sim_store.list_scenes(database, simulation_id, user_id=x_user_id)}

    @router.get('/api/personas/{persona_id}/comparison', responses=errors)
    def comparison(persona_id: str, x_user_id: Annotated[str | None, Header()] = None):
        require_user(x_user_id)
        persona = get_persona(database, persona_id, user_id=x_user_id)
        if persona is None:
            raise PersonaAPIError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.')
        cards = select_candidates(persona, seeds).candidates
        axes = {p['persona_id']: p['axes'] for p in json.loads(seeds.read_text(encoding='utf-8'))['personas']}
        latest = sim_store.latest_by_candidate(database, persona_id, user_id=x_user_id)
        rows = []
        for order, card in enumerate(cards):
            run = latest.get(card.candidate_id)
            done = bool(run and run['status'] == 'completed')
            rows.append(dict(candidate_id=card.candidate_id, alias=card.alias, axes=axes[card.candidate_id],
                             score=run['score'] if done else card.pre_score,
                             expected_conflicts_per_month=expected_conflicts(run['verdict_counts']) if done else None,
                             # 추천: 가상 동거를 마친 후보 우선, 그다음 점수 · 후보 순서
                             _rank=(not done, -(run['score'] if done else card.pre_score), order)))
        best = min(rows, key=lambda row: row['_rank']) if rows else None
        return {'me': {'axes': persona['axes']},
                'candidates': [{k: v for k, v in row.items() if k != '_rank'} for row in rows],
                'recommended_candidate_id': best['candidate_id'] if best else None}

    @router.post('/api/rules/{rule_id}/proposals', status_code=201,
                 responses={**errors, 503: {'model': error_model}})
    async def propose(rule_id: str, payload: ProposalCreate,
                      engine: Annotated[EngineAdapter, Depends(get_engine)],
                      x_user_id: Annotated[str | None, Header()] = None):
        await run_in_threadpool(require_user, x_user_id)
        context = await run_in_threadpool(match_store.load_rule_context, database, rule_id, user_id=x_user_id)
        if context is None:
            raise PersonaAPIError(404, 'RULE_NOT_FOUND', '규칙을 찾을 수 없어요.')
        rule = dict(context['rule'], text=context['rule']['text'].replace(context['name'], context['alias']))
        raw = await _engine_call(engine.mediate(rule, payload.text, payload.reason,
                                                context['me'], context['candidate']))
        mediation = Mediation.model_validate(_named(raw, context['alias'], context['name'])).model_dump()
        return await run_in_threadpool(match_store.create_proposal, database, rule_id, user_id=x_user_id,
                                       text=payload.text, reason=payload.reason, mediation=mediation)

    @router.post('/api/proposals/{proposal_id}/accept', responses=errors)
    def accept(proposal_id: str, x_user_id: Annotated[str | None, Header()] = None):
        require_user(x_user_id)
        rule = match_store.accept_proposal(database, proposal_id, user_id=x_user_id)
        if rule is None:
            raise PersonaAPIError(404, 'PROPOSAL_NOT_FOUND', '수정 제안을 찾을 수 없어요.')
        return rule

    @router.post('/api/mediation/rephrase', responses={**errors, 503: {'model': error_model}})
    async def rephrase(payload: RephraseCreate, engine: Annotated[EngineAdapter, Depends(get_engine)],
                       x_user_id: Annotated[str | None, Header()] = None):
        # 메모 원문은 엔진 호출에만 쓰고 저장 · 로그에 남기지 않는다 (API.md 4.16)
        await run_in_threadpool(require_user, x_user_id)
        context = await run_in_threadpool(match_store.load_match_context, database, payload.match_id,
                                          user_id=x_user_id)
        if context is None:
            raise PersonaAPIError(404, 'MATCH_NOT_FOUND', '매칭을 찾을 수 없어요.')
        raw = await _engine_call(engine.rephrase(payload.memo, context['me'], context['candidate']))
        return Rephrased.model_validate(_named(raw, context['alias'], context['name'])).model_dump()

    return router
