# 기능: 상태 확인·사용자·설문·페르소나 API와 공통 오류 응답을 등록한다.
# 시스템 범위: DB 설정과 설문 로더, 페르소나의 엔진·저장 연결 경로를 구성한다.
# 결과: 각 API의 명세 응답 또는 한국어 설명을 담은 공통 오류 JSON을 반환한다.
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.simulation_api import create_simulation_router
from app.simulation_runner import SimulationRunner
from app.engine_adapter import EngineError
from app.config import database_path
from app.persona_api import PersonaAPIError, create_persona_router
from app.survey import Survey, load_survey
from app.users import UserCreate, UserResponse, create_user

BACKEND_DIR = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={'error': {'code': code, 'message': message}})


def create_app(*, db_path: Path | None = None, survey_path: Path | None = None,
               draft_path: Path | None = None, seed_path: Path | None = None,
               replay_path: Path | None = None) -> FastAPI:
    database = database_path(db_path)
    runner = SimulationRunner(database)

    @asynccontextmanager
    async def lifespan(application):
        runner.recover()
        try:
            yield
        finally:
            await runner.close()

    application = FastAPI(lifespan=lifespan)
    application.state.simulation_runner = runner
    official = survey_path if survey_path is not None else BACKEND_DIR.parent / 'data' / 'seed' / 'survey.json'
    draft = draft_path if draft_path is not None else BACKEND_DIR / 'app' / 'data' / 'survey.draft.json'

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path.startswith(('/api/personas', '/api/simulations')):
            return error_response(422, 'VALIDATION_ERROR', '요청 JSON의 필드·자료형과 문구 길이를 확인해 주세요.')
        return error_response(422, 'VALIDATION_ERROR', '요청 JSON 형식을 확인해 주세요. 닉네임은 앞뒤 공백을 제외한 1~10자 문자열이어야 해요.')

    @application.exception_handler(EngineError)
    @application.exception_handler(PersonaAPIError)
    async def persona_error(request, exc):
        return error_response(exc.status, exc.code, exc.message)

    @application.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(422 if exc.status_code == 400 else exc.status_code, 'VALIDATION_ERROR', '요청 경로, 메서드 또는 형식을 확인해 주세요.')

    @application.exception_handler(Exception)
    async def internal_error(request, exc):
        logger.error('API 처리 실패: %s', request.url.path, exc_info=exc)
        return error_response(500, 'INTERNAL_ERROR', '서버 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.')

    #서버 응답 확인 코드
    @application.get('/api/health')
    def health():
        return {'status': 'ok'}

    @application.post('/api/users', status_code=201, response_model=UserResponse,
                      responses={422: {'model': ErrorResponse}, 500: {'model': ErrorResponse}})
    def users(payload: UserCreate):
        return create_user(database, payload.nickname)

    @application.get('/api/survey', response_model=Survey, response_model_exclude_none=True,
                     responses={500: {'model': ErrorResponse}})
    def survey():
        return load_survey(official, draft)

    seeds = seed_path if seed_path is not None else BACKEND_DIR.parent / 'data/seed/personas.json'
    application.include_router(create_persona_router(database, official, draft,
                                                     error_model=ErrorResponse, seed_path=seeds))
    application.include_router(create_simulation_router(database, seeds, runner,
        replay_path if replay_path is not None else BACKEND_DIR.parent / 'data/replays', ErrorResponse))
    return application


app = create_app()
