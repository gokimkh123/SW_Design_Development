# 기능: SQLite DATABASE_URL과 기존 DATABASE_PATH 설정을 파일 경로로 해석한다.
# 시스템 범위: 앱 생성 시 설정 우선순위를 적용하며 DB 파일을 열거나 변경하지 않는다.
# 결과: 실행 디렉터리를 기준으로 고정한 절대 경로를 반환하고 미지원 설정은 시작 오류로 알린다.
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def sqlite_path(url: str) -> Path:
    """파일 기반 SQLite URL만 지원한다. 슬래시 3개 뒤부터 파일 경로다."""
    prefix = 'sqlite:///'
    if not url.startswith(prefix):
        raise ValueError('DATABASE_URL은 sqlite:///상대경로 또는 sqlite:////절대경로여야 합니다.')
    path = url[len(prefix):]
    if (not path or not path.strip() or path.startswith('//')
            or any(c in path for c in ('?', '#', '%', '\x00', '\\'))
            or ':' in path or path.endswith('/')):
        raise ValueError('DATABASE_URL은 SQLite 파일 경로만 지원합니다. 메모리 DB, URL 옵션 및 인코딩 경로는 지원하지 않습니다.')
    return Path(path).resolve()


def database_path(explicit: Path | None = None) -> Path:
    """명시적 경로 > DATABASE_URL > DATABASE_PATH > 기존 기본 경로."""
    if explicit is not None:
        return Path(explicit).resolve()
    if 'DATABASE_URL' in os.environ:
        return sqlite_path(os.environ['DATABASE_URL'])
    if 'DATABASE_PATH' in os.environ:
        value = os.environ['DATABASE_PATH']
        if not value.strip() or value == ':memory:' or '\x00' in value:
            raise ValueError('DATABASE_PATH에 영구 저장할 SQLite 파일 경로를 지정해야 합니다.')
        return Path(value).resolve()
    return BACKEND_DIR / 'data' / 'users.sqlite3'
