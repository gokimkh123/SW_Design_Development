# 기능: 닉네임을 검증하고 충돌하지 않는 사용자 ID와 한국 시각을 만든다.
# 시스템 범위: 사용자 API가 호출하며 공통 DB 모듈로 테이블과 연결을 관리한다.
# 결과: 사용자 한 명을 영구 저장한 뒤 ID, 정리한 닉네임, 생성 시각을 반환한다.

from datetime import datetime, timedelta, timezone
from pathlib import Path
import secrets
import string

from pydantic import BaseModel, ConfigDict, Field

from app.database import connect_database, initialize_database


class UserCreate(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True)
    nickname: str = Field(min_length=1, max_length=10)


class UserResponse(BaseModel):
    user_id: str
    nickname: str
    created_at: str


def new_user_id() -> str:
    return 'usr_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


def create_user(db_path: Path, nickname: str) -> dict[str, str]:
    initialize_database(db_path)
    with connect_database(db_path) as db:
        for _ in range(10):
            user = {
                'user_id': new_user_id(),
                'nickname': nickname,
                'created_at': datetime.now(timezone(timedelta(hours=9))).isoformat(),
            }
            cursor = db.execute(
                'INSERT INTO users (user_id, nickname, created_at) VALUES (?, ?, ?) '
                'ON CONFLICT(user_id) DO NOTHING',
                (user['user_id'], user['nickname'], user['created_at']),
            )
            if cursor.rowcount == 1:
                return user
    raise RuntimeError('사용자 ID 생성 재시도 한도 초과')


def get_user(db_path: Path, user_id: str) -> dict[str, str] | None:
    """보호된 API에서 등록 사용자를 확인한다. 연결은 엔진 호출 전에 닫는다."""
    initialize_database(db_path)
    with connect_database(db_path) as db:
        row = db.execute('SELECT user_id, nickname, created_at FROM users WHERE user_id=?',
                         (user_id,)).fetchone()
        return dict(zip(('user_id', 'nickname', 'created_at'), row)) if row else None
