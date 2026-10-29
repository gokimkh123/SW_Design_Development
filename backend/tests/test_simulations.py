# 기능: 시뮬레이션 저장·재사용·재시도·익명화·상태 전이의 무결성을 검사한다.
# 시스템 범위: 임시 SQLite와 가짜 엔진만 사용하며 실제 DB·LLM·HTTP 실행기는 사용하지 않는다.
# 결과: 동시 요청, 재연결, 부분 실패에서도 입력과 공개 이벤트가 일관되면 통과한다.
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
import sqlite3
from threading import Barrier

import pytest

from app import simulations as store
from app.database import connect_database, initialize_database, SchemaConflictError
from app.engine_adapter import load_engine
from app.personas import create_persona, get_persona, update_preferences, PersonaData
from app.users import create_user, get_user


@pytest.fixture
def context(tmp_path):
    path = tmp_path / 'simulation.db'
    seeds = json.loads((Path(__file__).resolve().parents[2] / 'data/seed/personas.json').read_text())['personas']
    seed = deepcopy(next(s for s in seeds if s['candidate_pool']))
    me = seeds[0]
    user = create_user(path, '테스터')
    data = {k: me[k] for k in PersonaData.model_fields}
    data['is_seed'] = False
    persona = create_persona(path, user['user_id'], data)
    args = dict(user_id=user['user_id'], persona_id=persona['persona_id'], candidate=seed,
                alias='후보 A', scenes=load_engine('fake').load_scenes())
    return path, args, user, persona


def create(context):
    path, args, *_ = context
    sim, created = store.create_or_reuse_simulation(path, **args)
    assert created
    return sim['simulation_id']


def engine_events(path, sid):
    inputs = store.get_execution_inputs(path, sid)
    async def collect():
        return [e async for e in load_engine('fake').simulate(inputs['me'], inputs['candidate'],
                                                             mode=inputs['engine_mode'])]
    return asyncio.run(collect())


def finish_scenes(path, sid):
    store.start_simulation(path, sid)
    for event in engine_events(path, sid):
        store.save_event(path, sid, event)


def test_initialization_preserves_legacy_and_reconnect(context):
    path, args, user, persona = context
    # 기존 두 테이블만 있던 DB에서의 추가 초기화도 검사한다.
    with connect_database(path) as db:
        for table in ('simulation_events', 'simulation_scenes', 'simulations'):
            db.execute(f'DROP TABLE {table}')
    for _ in range(3):
        initialize_database(path)
    assert get_user(path, user['user_id']) == user
    assert get_persona(path, persona['persona_id']) == persona
    sid = create(context)
    assert re.fullmatch(r'sim_[a-z0-9]{8}', sid)
    record = store.get_internal_record(path, sid)
    assert datetime.fromisoformat(record['created_at']).utcoffset() == timedelta(hours=9)
    initialize_database(path)
    assert store.get_internal_record(path, sid) == record
    with connect_database(path) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        assert db.execute('SELECT count(*) FROM personas').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 1
        assert db.execute('SELECT 1 FROM personas WHERE persona_id=?', (args['candidate']['persona_id'],)).fetchone() is None


def test_snapshots_privacy_and_mode(context, monkeypatch):
    path, args, _, persona = context
    monkeypatch.setenv('SIM_MODE', 'single')
    sid = create(context)
    internal = store.get_internal_record(path, sid)
    inputs = store.get_execution_inputs(path, sid)
    assert internal['inputs']['candidate'] == args['candidate']
    assert inputs['engine_mode'] == 'single'
    assert inputs['candidate']['nickname'] == '후보 A'
    assert not {'name', 'answers', 'greeting', 'department'} & inputs['candidate'].keys()
    update_preferences(path, persona['persona_id'], args['user_id'], {'must_keep': ['변경']})
    args['candidate']['summary'] = '변경된 시드'
    args['scenes'][0]['title'] = '변경된 장면'
    monkeypatch.setenv('SIM_MODE', 'agents')
    assert store.get_execution_inputs(path, sid) == inputs
    assert store.get_internal_record(path, sid) == internal
    reused, fresh = store.create_or_reuse_simulation(path, **args)
    assert not fresh and reused['simulation_id'] == sid
    replay, fresh = store.create_or_reuse_simulation(path, **args, mode='replay')
    assert fresh and store.get_execution_inputs(path, replay['simulation_id'])['engine_mode'] is None
    with pytest.raises(ValueError):
        store.create_or_reuse_simulation(path, **args, mode='agents')


def test_owner_scope_and_sql_binding(context):
    path, args, *_ = context
    sid = create(context)
    other = create_user(path, "x');--")['user_id']
    for getter in (store.get_simulation, store.get_execution_inputs, store.get_internal_record,
                   store.list_scenes, store.list_events, store.get_completion):
        assert getter(path, sid, user_id=other) is None
        assert getter(path, "x' OR 1=1 --") is None
    with pytest.raises(LookupError):
        store.start_simulation(path, sid, user_id=other)
    with pytest.raises(LookupError):
        store.create_or_reuse_simulation(path, **dict(args, user_id=other))
    assert store.get_simulation(path, sid, user_id=args['user_id'])['status'] == 'running'


def test_concurrent_reuse_and_database_unique_constraint(context):
    path, args, *_ = context
    barrier = Barrier(8)
    def request(_):
        barrier.wait()
        return store.create_or_reuse_simulation(path, **args)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(request, range(8)))
    assert sum(created for _, created in results) == 1
    assert len({s['simulation_id'] for s, _ in results}) == 1
    sid = results[0][0]['simulation_id']
    with pytest.raises(sqlite3.IntegrityError):
        with connect_database(path) as db:
            cols = [r[1] for r in db.execute('PRAGMA table_info(simulations)')]
            row = list(db.execute('SELECT * FROM simulations WHERE simulation_id=?', (sid,)).fetchone())
            row[cols.index('simulation_id')] = 'sim_other123'
            db.execute(f'INSERT INTO simulations VALUES ({",".join("?" for _ in cols)})', row)


def test_full_fake_event_contract_idempotence_and_completion(context):
    path, args, *_ = context
    sid = create(context)
    started = store.start_simulation(path, sid)
    assert started['id'] == '0-0'
    assert store.start_simulation(path, sid) == started
    events = engine_events(path, sid)
    for event in events:
        saved = store.save_event(path, sid, event)
        assert store.save_event(path, sid, event) == saved
    assert store.update_progress(path, sid) == {'done': 20, 'total': 20}
    scenes = store.list_scenes(path, sid)
    assert [s['scene_index'] for s in scenes] == list(range(1, 21))
    assert all(len(s['dialogue']) == 2 for s in scenes)
    assert all(s['dialogue'][1]['name'] == '후보 A AI' for s in scenes)
    completed = store.complete_simulation(path, sid, score=80, headline='저장된 결과', report={'summary': '리포트'})
    assert store.complete_simulation(path, sid, score=80, headline='저장된 결과', report={'summary': '리포트'}) == completed
    assert store.save_event(path, sid, events[-1])['type'] == 'scene_judged'
    sim = store.get_simulation(path, sid)
    assert sim['status'] == 'completed' and sim['score'] == 80 and sim['completed_at']
    assert sum(sim['verdict_counts'].values()) == 20
    assert store.get_completion(path, sid)['report'] == {'summary': '리포트'}
    all_events = store.list_events(path, sid)
    assert [e['sequence'] for e in all_events] == list(range(1, 83))
    assert all_events[-1]['id'] == '20-4'
    assert store.list_events(path, sid, after_event_id='9-0') == all_events[34:]
    assert store.list_events(path, sid, after_event_id=completed['id']) == []
    with pytest.raises(ValueError):
        store.list_events(path, sid, after_event_id='unknown')
    public = json.dumps([sim, scenes, all_events, store.get_completion(path, sid)], ensure_ascii=False)
    assert args['candidate']['name'] not in public
    assert not store.create_or_reuse_simulation(path, **args)[1]
    with pytest.raises(store.StorageConflictError):
        store.complete_simulation(path, sid, score=81, headline='다른 결과')
    with pytest.raises(store.StorageConflictError):
        store.complete_simulation(path, sid, score=80, headline='저장된 결과', report={'summary': '변경'})
    with pytest.raises(store.StorageConflictError):
        store.fail_simulation(path, sid, {'code': 'INTERNAL_ERROR', 'message': '실패', 'retryable': False})


def test_invalid_order_payload_and_progress(context):
    path, *_ = context
    sid = create(context)
    events = engine_events(path, sid)
    with pytest.raises(store.StorageConflictError):
        store.save_event(path, sid, events[0])
    store.start_simulation(path, sid)
    for event in (events[1], events[3], events[4]):
        with pytest.raises(store.StorageConflictError):
            store.save_event(path, sid, event)
    store.save_event(path, sid, events[0])
    with pytest.raises(store.StorageConflictError):
        store.save_event(path, sid, events[2])
    store.save_event(path, sid, events[1])
    changed = deepcopy(events[1])
    changed['data']['text'] = '재시도 내용 변경'
    with pytest.raises(store.StorageConflictError):
        store.save_event(path, sid, changed)
    store.save_event(path, sid, events[2])
    wrong = deepcopy(events[3])
    wrong['data']['progress']['done'] = 2
    with pytest.raises(store.StorageConflictError):
        store.save_event(path, sid, wrong)
    assert store.update_progress(path, sid)['done'] == 0
    assert len(store.list_events(path, sid)) == 4
    assert 'verdict' not in store.list_scenes(path, sid)[0]
    with pytest.raises(store.StorageConflictError):
        store.complete_simulation(path, sid, score=80, headline='일찍 완료')
    with pytest.raises(store.StorageConflictError):
        store.get_completion(path, sid)


def test_pending_and_failure_atomic_retry(context):
    path, args, *_ = context
    sid = create(context)
    store.start_simulation(path, sid)
    events = engine_events(path, sid)
    for e in events[:3]:
        store.save_event(path, sid, e)
    pending = deepcopy(events[3])
    pending['data']['verdict'] = 'pending'
    store.save_event(path, sid, pending)
    error = {'type': 'error', 'data': {'code': 'LLM_UNAVAILABLE', 'message': '중단',
                                      'scene_index': 2, 'retryable': True}}
    saved = store.save_event(path, sid, error)
    assert store.save_event(path, sid, error) == saved
    record = store.get_internal_record(path, sid)
    assert record['status'] == 'failed' and record['failed_at'] and record['failure'] == error['data']
    assert record['completed_at'] is None and record['result'] is None and record['done'] == 1
    assert store.get_simulation(path, sid)['verdict_counts']['pending'] == 1
    for action in (lambda: store.save_event(path, sid, events[4]),
                   lambda: store.complete_simulation(path, sid, score=0, headline='실패 후 완료'),
                   lambda: store.update_progress(path, sid)):
        with pytest.raises(store.StorageConflictError):
            action()
    new, created = store.create_or_reuse_simulation(path, **args)
    assert created and new['simulation_id'] != sid


@pytest.mark.parametrize('stage', ['scene', 'judgement', 'complete', 'failure', 'start'])
def test_transaction_rolls_back_when_event_insert_fails(context, stage):
    path, *_ = context
    sid = create(context)
    events = engine_events(path, sid)
    if stage != 'start':
        store.start_simulation(path, sid)
    if stage == 'judgement':
        for e in events[:3]:
            store.save_event(path, sid, e)
    if stage == 'complete':
        for e in events:
            store.save_event(path, sid, e)
    before = (store.get_internal_record(path, sid), store.list_scenes(path, sid), store.list_events(path, sid))
    with connect_database(path) as db:
        db.execute("CREATE TRIGGER reject_event BEFORE INSERT ON simulation_events BEGIN SELECT RAISE(ABORT, 'injected'); END")
    actions = {'scene': lambda: store.save_event(path, sid, events[0]),
               'judgement': lambda: store.save_event(path, sid, events[3]),
               'complete': lambda: store.complete_simulation(path, sid, score=50, headline='완료'),
               'failure': lambda: store.fail_simulation(path, sid, {'code': 'INTERNAL_ERROR', 'message': '실패', 'retryable': False}),
               'start': lambda: store.start_simulation(path, sid)}
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        actions[stage]()
    assert (store.get_internal_record(path, sid), store.list_scenes(path, sid), store.list_events(path, sid)) == before


def test_database_candidate_and_candidate_foreign_key_policy(context):
    path, args, _, persona = context
    other = create_user(path, '다른 사용자')
    candidate = create_persona(path, other['user_id'], {k: persona[k] for k in PersonaData.model_fields})
    sim, fresh = store.create_or_reuse_simulation(path, **dict(args, candidate=candidate))
    assert fresh
    assert store.get_internal_record(path, sim['simulation_id'])['inputs']['candidate'] == candidate
    with pytest.raises(LookupError):
        store.create_or_reuse_simulation(path, **dict(args, candidate={'persona_id': 'missing', 'is_seed': False}))


def test_private_names_are_scrubbed_from_free_text(context):
    path, args, *_ = context
    sid = create(context)
    store.start_simulation(path, sid)
    event = engine_events(path, sid)[0]
    event['data']['scene']['situation'] = args['candidate']['name'] + '의 대화'
    saved = store.save_event(path, sid, event)
    assert saved['data']['scene']['situation'] == '후보 A의 대화'
    assert store.list_scenes(path, sid)[0]['scene']['situation'] == '후보 A의 대화'


def test_schema_conflict_and_id_collision_preserve_rows(context, monkeypatch):
    path, args, *_ = context
    monkeypatch.setattr(store, 'new_simulation_id', lambda: 'sim_aaaaaaaa')
    sid = create(context)
    with pytest.raises(RuntimeError, match='재시도'):
        store.create_or_reuse_simulation(path, **args, mode='replay')
    ids = iter([sid, 'sim_bbbbbbbb'])
    monkeypatch.setattr(store, 'new_simulation_id', lambda: next(ids))
    assert store.create_or_reuse_simulation(path, **args, mode='replay')[0]['simulation_id'] == 'sim_bbbbbbbb'
    with connect_database(path) as db:
        db.execute('DROP INDEX simulation_reuse')
        db.execute('CREATE UNIQUE INDEX simulation_reuse ON simulations(persona_id,candidate_id,mode)')
    before = path.read_bytes()
    with pytest.raises(SchemaConflictError):
        initialize_database(path)
    assert path.read_bytes() == before


def test_concurrent_event_retries_do_not_increase_progress(context):
    path, *_ = context
    sid = create(context)
    store.start_simulation(path, sid)
    events = engine_events(path, sid)
    for e in events[:3]:
        store.save_event(path, sid, e)
    barrier = Barrier(6)
    def save(_):
        barrier.wait()
        return store.save_event(path, sid, events[3])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(save, range(6)))
    assert all(result == results[0] for result in results)
    assert store.get_simulation(path, sid)['progress']['done'] == 1
    assert len(store.list_events(path, sid)) == 5


def test_queued_state_transition_and_terminal_rejection(context):
    path, args, *_ = context
    sid = create(context)
    # queued는 향후 스케줄러용 상태. 이번 생성 함수는 running으로만 예약한다.
    with connect_database(path) as db:
        db.execute("UPDATE simulations SET status='queued', started_at=NULL WHERE simulation_id=?", (sid,))
    with pytest.raises(store.StorageConflictError, match='대기'):
        store.create_or_reuse_simulation(path, **args)
    with pytest.raises(store.StorageConflictError):
        store.complete_simulation(path, sid, score=0, headline='대기 중 완료')
    store.start_simulation(path, sid)
    assert store.get_simulation(path, sid)['status'] == 'running'
    store.fail_simulation(path, sid, {'code': 'INTERNAL_ERROR', 'message': '중단', 'retryable': False})
    new, _ = store.create_or_reuse_simulation(path, **args)
    sid2 = new['simulation_id']
    with connect_database(path) as db:
        db.execute("UPDATE simulations SET status='queued', started_at=NULL WHERE simulation_id=?", (sid2,))
    store.fail_simulation(path, sid2, {'code': 'INTERNAL_ERROR', 'message': '예약 중단', 'retryable': False})
    with pytest.raises(store.StorageConflictError):
        store.start_simulation(path, sid2)
    assert store.get_simulation(path, sid2)['status'] == 'failed'


def test_new_schema_conflict_rolls_back_all_additions(tmp_path):
    path = tmp_path / 'legacy.db'
    with connect_database(path) as db:
        db.execute('CREATE TABLE users (user_id TEXT PRIMARY KEY, nickname TEXT NOT NULL, created_at TEXT NOT NULL)')
        db.execute('INSERT INTO users VALUES (?,?,?)', ('usr_old', '보존', '2026-10-30T00:00:00+09:00'))
        db.execute('CREATE TABLE simulation_events (old TEXT)')
    before = path.read_bytes()
    with pytest.raises(SchemaConflictError):
        initialize_database(path)
    assert path.read_bytes() == before
