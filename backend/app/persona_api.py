# 기능: 설문 답변으로 페르소나를 만들고 본인의 카드 조회·문구 수정을 제공한다.
# 시스템 범위: API 명세 4.4~4.6에 따라 사용자·설문·엔진 어댑터·SQLite를 연결한다.
# 결과: 생성 201, 조회·수정 200 또는 공통 형식의 400·401·404·422 오류를 반환한다.
import asyncio
from pathlib import Path
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.engine_adapter import EngineAdapter, get_engine, load_engine
from app.personas import PersonaData, create_persona, get_persona, update_preferences
from app.survey import Survey, load_survey
from app.users import get_user

# 전체 응답 예산 10초 중 DB 저장 시간을 남기고, 지연된 LLM은 규칙 기반으로 대체한다.
PERSONA_ENGINE_TIMEOUT_SECONDS = 8.0
PreferenceText = Annotated[str, Field(max_length=30)]


class PersonaAPIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


class PersonaCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    answers: dict[str, Any]


class PersonaResponse(PersonaData):
    persona_id: str
    user_id: str
    nickname: str
    created_at: str


class PersonaPatch(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    must_keep: list[PreferenceText] | None = Field(default=None, max_length=3)
    okay_with: list[PreferenceText] | None = Field(default=None, max_length=3)

    @field_validator('must_keep', 'okay_with')
    @classmethod
    def reject_explicit_null(cls, value):
        if value is None:
            raise ValueError('문구를 비우려면 null 대신 빈 배열을 보내 주세요.')
        return value


def validate_answers(survey: Survey, answers: dict) -> None:
    """GET /survey가 제공한 문항·선택값·시간 범위로 답변을 검사한다."""
    expected = {question.question_id for question in survey.questions}
    missing = [question.question_id for question in survey.questions if question.question_id not in answers]
    if missing:
        raise PersonaAPIError(400, 'SURVEY_INCOMPLETE', '빠진 설문 문항: ' + ', '.join(missing))
    if set(answers) != expected:
        raise PersonaAPIError(422, 'VALIDATION_ERROR', '알 수 없는 설문 문항이 있어요.')
    for question in survey.questions:
        value = answers[question.question_id]
        if question.type == 'choice':
            valid = isinstance(value, str) and value in {option.value for option in question.options}
        else:
            valid = isinstance(value, dict) and set(value) == {field.key for field in question.fields}
            if valid:
                for field in question.fields:
                    time = value[field.key]
                    if not isinstance(time, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', time):
                        valid = False
                        break
                    def minutes(text):
                        return int(text[:2]) * 60 + int(text[3:])
                    offset = (minutes(time) - minutes(field.min)) % 1440
                    duration = (minutes(field.max) - minutes(field.min)) % 1440
                    if offset > duration or offset % field.step_minutes:
                        valid = False
                        break
        if not valid:
            raise PersonaAPIError(422, 'VALIDATION_ERROR', f'{question.question_id}의 선택값 또는 시각을 확인해 주세요.')


def create_persona_router(database: Path, official: Path, draft: Path, *,
                          error_model: type[BaseModel]) -> APIRouter:
    router = APIRouter(prefix='/api/personas', tags=['personas'],
                       responses={status: {'model': error_model} for status in (401, 422, 500)})

    def require_user(x_user_id: Annotated[str | None, Header(alias='X-User-Id')] = None):
        if not x_user_id or not x_user_id.strip():
            raise PersonaAPIError(401, 'USER_REQUIRED', '사용자 ID가 필요해요. 먼저 닉네임으로 시작해 주세요.')
        user = get_user(database, x_user_id)
        if user is None:
            raise PersonaAPIError(401, 'USER_REQUIRED', '등록된 사용자 ID를 보내 주세요.')
        return user

    @router.post('', status_code=201, response_model=PersonaResponse,
                 responses={400: {'model': error_model}})
    async def generate(payload: PersonaCreate, user: Annotated[dict, Depends(require_user)],
                       engine: Annotated[EngineAdapter, Depends(get_engine)]):
        survey = await run_in_threadpool(load_survey, official, draft)
        validate_answers(survey, payload.answers)
        try:
            generated = await asyncio.wait_for(
                engine.build_persona(user['nickname'], payload.answers),
                timeout=PERSONA_ENGINE_TIMEOUT_SECONDS)
        except TimeoutError:
            generated = await load_engine('fake').build_persona(user['nickname'], payload.answers)
        # 엔진의 서버 관리 필드·닉네임은 신뢰하지 않고 생활 성향 내용만 저장한다.
        data = {field: generated[field] for field in PersonaData.model_fields
                if field != 'is_seed' and field in generated}
        data['is_seed'] = False
        return await run_in_threadpool(create_persona, database, user['user_id'], data)

    @router.get('/{persona_id}', response_model=PersonaResponse,
                responses={404: {'model': error_model}})
    def read(persona_id: str, user: Annotated[dict, Depends(require_user)]):
        persona = get_persona(database, persona_id, user_id=user['user_id'])
        if persona is None:
            raise PersonaAPIError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.')
        return persona

    @router.patch('/{persona_id}', response_model=PersonaResponse,
                  responses={404: {'model': error_model}})
    def patch(persona_id: str, payload: PersonaPatch, user: Annotated[dict, Depends(require_user)]):
        persona = update_preferences(database, persona_id, user['user_id'],
                                     payload.model_dump(exclude_unset=True))
        if persona is None:
            raise PersonaAPIError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.')
        return persona

    return router
