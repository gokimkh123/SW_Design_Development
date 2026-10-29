# 기능: 페르소나 정보를 저장하고 사용자 닉네임을 붙여 조회한다.
# 시스템 범위: 다음 단계 API가 호출할 저장 계층이며 엔진과 HTTP 경로는 다루지 않는다.
# 결과: ID와 KST 생성 시각을 부여하고 JSON을 원래 객체와 배열로 복원한다.
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import string
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.database import connect_database, initialize_database


class PersonaData(BaseModel):
    """호출자가 전달할 명세 데이터. 소유자·ID·시각·닉네임은 별도 관리한다."""
    model_config = ConfigDict(strict=True, extra='forbid')
    type_name: str
    summary: str
    sleep: dict[str, str]
    axes: dict[str, int]
    axis_labels: dict[str, str]
    conflict_style: Literal['direct', 'avoid', 'delay']
    preferences: dict[str, str]
    must_keep: list[str] = Field(max_length=3)
    okay_with: list[str] = Field(max_length=3)
    is_seed: bool = False


JSON_FIELDS = ('sleep', 'axes', 'axis_labels', 'preferences', 'must_keep', 'okay_with')
AXES = {'sleep_rhythm', 'noise_sensitivity', 'cleanliness', 'sociability', 'sharing_tolerance'}


def new_persona_id() -> str:
    return 'per_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


def create_persona(db_path: Path, user_id: str, data: dict) -> dict:
    """기존 user_id를 받는다. PK 충돌만 10회 재시도; FK 오류는 IntegrityError."""
    payload = PersonaData.model_validate(data).model_dump()
    if (set(payload['axes']) != AXES or set(payload['axis_labels']) != AXES
            or any(not 0 <= value <= 100 for value in payload['axes'].values())
            or not {'bedtime', 'wake', 'exam_pattern'} <= payload['sleep'].keys()
            or 'temperature' not in payload['preferences']
            or any(len(item) > 30 for field in ('must_keep', 'okay_with') for item in payload[field])):
        raise ValueError('Persona 축·수면·선호·문구 형식을 확인해 주세요.')
    initialize_database(db_path)
    with connect_database(db_path) as db:
        for _ in range(10):
            persona = dict(payload, persona_id=new_persona_id(), user_id=user_id,
                           created_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
            stored = {key: json.dumps(value, ensure_ascii=False, allow_nan=False)
                      if key in JSON_FIELDS else value for key, value in persona.items()}
            columns = ', '.join(stored)  # 검증된 내부 필드명만 SQL에 사용한다.
            cursor = db.execute(
                f'INSERT INTO personas ({columns}) VALUES ({", ".join("?" for _ in stored)}) '
                'ON CONFLICT(persona_id) DO NOTHING', tuple(stored.values()))
            if cursor.rowcount == 1:
                persona['nickname'] = db.execute('SELECT nickname FROM users WHERE user_id=?', (user_id,)).fetchone()[0]
                return persona
        raise RuntimeError('페르소나 ID 생성 재시도 한도 초과')


def get_persona(db_path: Path, persona_id: str) -> dict | None:
    """없으면 None, DB 오류는 그대로 전파한다. HTTP 오류 변환은 API의 책임이다."""
    initialize_database(db_path)
    with connect_database(db_path) as db:
        cursor = db.execute('SELECT p.*, u.nickname FROM personas p JOIN users u ON u.user_id=p.user_id '
                            'WHERE p.persona_id=?', (persona_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        persona = dict(zip((column[0] for column in cursor.description), row))
        for field in JSON_FIELDS:
            persona[field] = json.loads(persona[field])
        persona['is_seed'] = bool(persona['is_seed'])
        return persona
