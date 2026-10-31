# 기능: 소유자와 선정 후보를 검증하고 시뮬레이션 시작을 예약한다.
# 시스템 범위: POST 시작 API만 제공하며 조회·SSE·리포트 API는 제외한다.
# 결과: 신규 실행은 202, 기존 실행은 200 또는 공통 오류 형식을 반환한다.
# 한계
# 1. 리플레이 데이터와 파일 형식 계약이 없어 실제 replay 재생은 아직 구현하지 않았다.
#    파일이 없으면 명세대로 live로 실행하고, 파일이 있으면 연결 미완료 오류(500)를 반환한다.
# 2. queued 중복 요청의 HTTP 정책은 미정이며, 현재 저장 계약의 충돌을 500으로 반환한다.
#    통합 시 팀과 응답 정책을 확정해야 한다.
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ConfigDict, Field

from app.candidates import select_candidates
from app.engine_adapter import EngineAdapter, get_engine
from app.persona_api import PersonaAPIError
from app.personas import get_persona
from app.users import get_user
from app import simulations as store


class SimulationCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    persona_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    mode: Literal['live', 'replay'] = 'live'


class SimulationResponse(BaseModel):
    simulation_id: str
    persona_id: str
    candidate_id: str
    mode: Literal['live', 'replay']
    status: Literal['queued', 'running', 'completed', 'failed']
    progress: store.Progress
    verdict_counts: dict[str, int]
    score: int | None
    started_at: str | None
    completed_at: str | None


def create_simulation_router(database, seeds, runner, replay_path, error_model):
    router = APIRouter(prefix='/api/simulations', tags=['simulations'])

    @router.post('', status_code=202, response_model=SimulationResponse,
                 responses={200: {'model': SimulationResponse}, **{
                     status: {'model': error_model} for status in (401, 404, 422, 500)}})
    async def start(payload: SimulationCreate, response: Response,
                    engine: Annotated[EngineAdapter, Depends(get_engine)],
                    x_user_id: Annotated[str | None, Header()] = None):
        if not x_user_id or get_user(database, x_user_id) is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')
        me = get_persona(database, payload.persona_id, user_id=x_user_id)
        if me is None:
            raise PersonaAPIError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.')
        cards = select_candidates(me, seeds).candidates
        card = next((c for c in cards if c.candidate_id == payload.candidate_id), None)
        if card is None:
            raise PersonaAPIError(404, 'PERSONA_NOT_FOUND', '선택할 수 있는 후보를 찾을 수 없어요.')
        candidate = next(c for c in json.loads(seeds.read_text())['personas']
                         if c['persona_id'] == card.candidate_id)
        # 저장소에는 리플레이 파일·파일명·스키마 계약이 아직 없다.
        if payload.mode == 'replay' and replay_path.exists() and any(
                p.is_file() and not p.name.startswith('.') for p in replay_path.rglob('*')):
            raise PersonaAPIError(500, 'INTERNAL_ERROR', '리플레이 데이터 형식 연결이 필요합니다.')
        scenes = engine.load_scenes()
        if len(scenes) != 20:
            raise ValueError('서비스 시뮬레이션에는 20개 장면이 필요합니다.')
        # 아래 저장과 task 등록 사이에는 await가 없다. 연결 취소가 예약을 분리하지 않는다.
        sim, created = store.create_or_reuse_simulation(database, user_id=x_user_id,
            persona_id=payload.persona_id, candidate=candidate, alias=card.alias, scenes=scenes, mode='live')
        if not created:
            response.status_code = 200
            return sim
        try:
            runner.launch(sim['simulation_id'], engine)
        except BaseException:
            runner.fail(sim['simulation_id'], '백그라운드 실행 시작에 실패했습니다.')
            raise
        return sim

    return router
