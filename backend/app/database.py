# 기능: 사용자·페르소나·시뮬레이션 테이블을 안전하게 준비하고 DB 연결을 관리한다.
# 시스템 범위: 모든 앱 저장 모듈이 사용하는 SQLite 연결과 트랜잭션을 담당한다.
# 결과: 외래키를 적용하고 성공 시 커밋, 실패 시 롤백하며 연결을 항상 닫는다.
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import sqlite3

from app.simulation_schema import SCHEMAS as SIMULATION_SCHEMAS, INDEXES

SCHEMAS = {
    'users': '''CREATE TABLE users (
        user_id TEXT PRIMARY KEY,
        nickname TEXT NOT NULL,
        created_at TEXT NOT NULL
    )''',
    'personas': '''CREATE TABLE personas (
        persona_id TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        type_name TEXT NOT NULL,
        summary TEXT NOT NULL,
        sleep TEXT NOT NULL,
        axes TEXT NOT NULL,
        axis_labels TEXT NOT NULL,
        conflict_style TEXT NOT NULL,
        preferences TEXT NOT NULL,
        must_keep TEXT NOT NULL,
        okay_with TEXT NOT NULL,
        is_seed INTEGER NOT NULL CHECK (is_seed IN (0, 1)),
        created_at TEXT NOT NULL
    )''',
}

SCHEMAS.update(SIMULATION_SCHEMAS)


class SchemaConflictError(RuntimeError):
    """기존 스키마가 예상 구조와 다름. 자동 삭제나 이관을 하지 않는다."""


@contextmanager
def connect_database(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    """테이블 생성 없이 연결한다. 블록 전체를 커밋/롤백하고 연결을 닫는다."""
    db = sqlite3.connect(db_path, timeout=10)
    try:
        db.execute('PRAGMA foreign_keys = ON')
        with db:
            yield db
    finally:
        db.close()


def _structure(db, table):
    # 테이블명은 내부 상수만 사용한다. UNIQUE 인덱스도 비교해 1:N 제한을 감지한다.
    columns = db.execute(f'PRAGMA table_info({table})').fetchall()
    foreign_keys = db.execute(f'PRAGMA foreign_key_list({table})').fetchall()
    unique = []
    for index in db.execute(f'PRAGMA index_list({table})'):
        if index[2]:
            unique.append(db.execute('SELECT name FROM pragma_index_info(?) ORDER BY seqno',
                                     (index[1],)).fetchall())
    return columns, foreign_keys, sorted(unique)


def initialize_database(db_path: Path) -> None:
    """반복 호출 가능. 기존 테이블 충돌은 변경 전에 예외로 보고한다."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_database(':memory:') as expected:
        for sql in SCHEMAS.values():
            expected.execute(sql)
        for sql in INDEXES.values():
            expected.execute(sql)
        with connect_database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            existing = dict(db.execute("SELECT name, type FROM sqlite_master"))
            for table in SCHEMAS:
                if table in existing and (existing[table] != 'table' or
                        _structure(db, table) != _structure(expected, table)):
                    raise SchemaConflictError(f'{table} 테이블 구조 충돌: 기존 데이터를 보존했습니다. 수동 검토가 필요합니다.')
            # 추가 테이블의 CHECK와 부분 UNIQUE 조건도 비교한다. 충돌 시 DDL 전에 중단한다.
            for name in (*SIMULATION_SCHEMAS, *INDEXES):
                if name in existing:
                    actual = db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0]
                    wanted = expected.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0]
                    if actual != wanted:
                        raise SchemaConflictError(f'{name} 구조 충돌: 기존 데이터를 보존했습니다.')
            for table, sql in SCHEMAS.items():
                if table not in existing:
                    db.execute(sql)
            for name, sql in INDEXES.items():
                if name not in existing:
                    db.execute(sql)
