# 기능: 기존 상태 확인과 사용자 생성, 설문 제공 경로 및 공통 오류 응답을 등록한다.
# 시스템 범위: DB 환경설정을 해석하고 FastAPI 앱을 사용자 저장 모듈과 앱에 포함된 설문 초안 로더에 연결한다.
# 결과: health 200, 사용자 201, 설문 200 또는 한국어 설명을 담은 공통 오류 JSON을 반환한다.
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.config import database_path
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
               draft_path: Path | None = None) -> FastAPI:
    application = FastAPI()
    database = database_path(db_path)
    official = survey_path if survey_path is not None else BACKEND_DIR.parent / 'data' / 'seed' / 'survey.json'
    draft = draft_path if draft_path is not None else BACKEND_DIR / 'app' / 'data' / 'survey.draft.json'

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(422, 'VALIDATION_ERROR', '요청 JSON 형식을 확인해 주세요. 닉네임은 앞뒤 공백을 제외한 1~10자 문자열이어야 해요.')

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

    return application


app = create_app()
