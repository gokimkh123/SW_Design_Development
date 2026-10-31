# 기능: 공통 DB 초기화와 페르소나 저장·조회의 무결성을 검사한다.
# 시스템 범위: pytest 임시 SQLite만 사용하며 실제 개발 DB에는 접근하지 않는다.
# 결과: 데이터 보존, 외래키, 자료형 복원, 충돌과 롤백이 올바르면 통과한다.
from datetime import datetime, timedelta
import re
import sqlite3

import pytest

from app.database import connect_database, initialize_database, SchemaConflictError
from app import personas
from app.users import create_user


@pytest.fixture
def payload():
    return dict(type_name='아침형', summary='규칙적인 생활',
                sleep=dict(bedtime='23:00', wake='06:30', exam_pattern='earlier'),
                axes=dict(sleep_rhythm=33, noise_sensitivity=67, cleanliness=84,
                          sociability=33, sharing_tolerance=0),
                axis_labels=dict(sleep_rhythm='아침형', noise_sensitivity='예민',
                                 cleanliness='높음', sociability='보통', sharing_tolerance='낮음'),
                conflict_style='direct', preferences={'temperature': 'moderate'},
                must_keep=['조용히', "x');--"], okay_with=['친구 초대'], is_seed=False)


def test_extend_existing_users(tmp_path):
    path = tmp_path / 'test.db'
    with connect_database(path) as db:
        db.execute('CREATE TABLE users (user_id TEXT PRIMARY KEY, nickname TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('INSERT INTO users VALUES (?, ?, ?)', ('usr_original', '기존', '2026-10-29T12:00:00+09:00'))
    for _ in range(3):
        initialize_database(path)
    with connect_database(path) as db:
        assert db.execute('SELECT * FROM users').fetchall() == [('usr_original', '기존', '2026-10-29T12:00:00+09:00')]
        assert db.execute('SELECT * FROM personas').fetchall() == []


def test_roundtrip_and_many_personas(tmp_path, payload):
    path = tmp_path / 'test.db'
    user = create_user(path, '하늘')
    first = personas.create_persona(path, user['user_id'], payload)
    second = personas.create_persona(path, user['user_id'], payload)
    assert first['persona_id'] != second['persona_id']
    assert re.fullmatch(r'per_[a-z0-9]{8}', first['persona_id'])
    created = datetime.fromisoformat(first['created_at'])
    assert created.utcoffset() == timedelta(hours=9)
    assert abs((datetime.now(created.tzinfo) - created).total_seconds()) < 10
    result = personas.get_persona(path, first['persona_id'])
    assert result is not None
    assert result == first
    for field, value in payload.items():
        assert result[field] == value and type(result[field]) is type(value)
    assert result['nickname'] == '하늘'
    assert personas.get_persona(path, "missing' OR 1=1 --") is None
    with connect_database(path) as db:
        db.execute('UPDATE users SET nickname=? WHERE user_id=?', ('변경', user['user_id']))
    updated = personas.get_persona(path, first['persona_id'])
    assert updated is not None
    assert updated['nickname'] == '변경'


def test_foreign_key_new_connections_and_rollback(tmp_path, payload):
    path = tmp_path / 'test.db'
    user = create_user(path, '하늘')
    saved = personas.create_persona(path, user['user_id'], payload)
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        personas.create_persona(path, 'usr_missing', payload)
    for _ in range(2):
        with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
            with connect_database(path) as db:
                assert db.execute('PRAGMA foreign_keys').fetchone() == (1,)
                db.execute('UPDATE users SET nickname=?', ('롤백 대상',))
                db.execute('UPDATE personas SET user_id=?', ('usr_missing',))
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            db.execute('SELECT 1')
    with pytest.raises(sqlite3.IntegrityError, match='FOREIGN KEY'):
        with connect_database(path) as db:
            db.execute('DELETE FROM users WHERE user_id=?', (user['user_id'],))
    assert personas.get_persona(path, saved['persona_id']) == saved
    with connect_database(path) as db:
        assert db.execute('SELECT count(*) FROM personas').fetchone() == (1,)


def test_primary_key_and_generated_collision(tmp_path, payload, monkeypatch):
    path = tmp_path / 'test.db'
    user = create_user(path, '하늘')
    monkeypatch.setattr(personas, 'new_persona_id', lambda: 'per_aaaaaaaa')
    first = personas.create_persona(path, user['user_id'], payload)
    with pytest.raises(sqlite3.IntegrityError, match='UNIQUE'):
        with connect_database(path) as db:
            db.execute('INSERT INTO personas SELECT * FROM personas')
    ids = iter(['per_aaaaaaaa', 'per_bbbbbbbb'])
    monkeypatch.setattr(personas, 'new_persona_id', lambda: next(ids))
    assert personas.create_persona(path, user['user_id'], payload)['persona_id'] == 'per_bbbbbbbb'
    monkeypatch.setattr(personas, 'new_persona_id', lambda: 'per_aaaaaaaa')
    with pytest.raises(RuntimeError, match='재시도'):
        personas.create_persona(path, user['user_id'], payload)
    assert personas.get_persona(path, first['persona_id']) == first


def test_schema_conflict_preserves_database(tmp_path):
    path = tmp_path / 'test.db'
    with connect_database(path) as db:
        db.execute('CREATE TABLE users (user_id TEXT PRIMARY KEY, nickname TEXT)')
        db.execute('INSERT INTO users VALUES (?, ?)', ('old', '보존'))
    before = path.read_bytes()
    with pytest.raises(SchemaConflictError, match='users'):
        initialize_database(path)
    assert path.read_bytes() == before


def test_empty_initialization_and_unique_conflict(tmp_path):
    path = tmp_path / 'test.db'
    initialize_database(path)
    initialize_database(path)
    with connect_database(path) as db:
        assert {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {'users', 'personas', 'simulations', 'simulation_scenes', 'simulation_events'}
        db.execute('CREATE UNIQUE INDEX one_persona ON personas(user_id)')
    with pytest.raises(SchemaConflictError, match='personas'):
        initialize_database(path)
