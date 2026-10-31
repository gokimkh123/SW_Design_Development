# 기능: 상태 조회와 SSE의 접근 제어·재연결·실시간 전달·구독 정리를 검증한다.
# 시스템 범위: 임시 SQLite, 가짜 엔진, 임시 로컬 포트만 사용하며 유료 LLM은 호출하지 않는다.
# 결과: 스트림 종료 전 수신과 경계 시점 저장, 재시작 후 재조회까지 제한 시간 안에 확인한다.
import asyncio
from contextlib import asynccontextmanager
import json
import socket

import httpx
import pytest
import uvicorn

from app import simulations as store, simulation_stream
from app.main import create_app
from app.users import create_user
from test_simulations import context, create, engine_events, finish_scenes
from test_simulation_start import context as start_context, setup


@pytest.mark.parametrize('terminal', ['running', 'completed', 'failed'])
def test_status_is_read_only(context, terminal):
    db, args, *_ = context
    sid = create(context)
    if terminal == 'completed':
        finish_scenes(db, sid)
        store.complete_simulation(db, sid, score=80, headline='완료')
    else:
        store.start_simulation(db, sid)
        for event in engine_events(db, sid)[:4]:
            store.save_event(db, sid, event)
        if terminal == 'failed':
            store.fail_simulation(db, sid, dict(code='INTERNAL_ERROR', message='private', retryable=False))
    before = db.read_bytes()
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_path=db)), base_url='http://test') as client:
            for _ in range(3):
                r = await client.get(f'/api/simulations/{sid}', headers={'X-User-Id': args['user_id']})
                assert r.status_code == 200
                assert r.json() == store.get_simulation(db, sid)
                assert r.json()['status'] == terminal
                assert r.json()['progress'] == {'done': 20 if terminal == 'completed' else 1, 'total': 20}
                assert 'dialogue' not in r.text and 'private' not in r.text
    asyncio.run(asyncio.wait_for(run(), 5))
    assert db.read_bytes() == before


@pytest.mark.parametrize('suffix', ['', '/events'])
def test_access_errors_before_stream(context, suffix):
    db, args, *_ = context
    sid = create(context)
    other = create_user(db, '다른 사람')['user_id']
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_path=db)), base_url='http://test') as client:
            for headers, target, status, code in [
                ({}, sid, 401, 'USER_REQUIRED'),
                ({'X-User-Id': 'missing'}, sid, 401, 'USER_REQUIRED'),
                ({'X-User-Id': other}, sid, 404, 'SIMULATION_NOT_FOUND'),
                ({'X-User-Id': args['user_id']}, 'missing', 404, 'SIMULATION_NOT_FOUND'),
            ]:
                r = await client.get(f'/api/simulations/{target}{suffix}', headers=headers)
                assert r.status_code == status
                assert r.headers['content-type'] == 'application/json'
                assert r.json()['error']['code'] == code
    asyncio.run(asyncio.wait_for(run(), 5))


@pytest.mark.parametrize('cursor', ['', 'garbage', '-1-0', '01-0', '999999-0', '0-1'])
def test_bad_cursor(context, cursor):
    db, args, *_ = context
    sid = create(context)
    store.start_simulation(db, sid)
    # 0-1은 다른 실행에는 있지만 대상 실행에는 없는 ID다.
    other = store.create_or_reuse_simulation(db, **args, mode='replay')[0]['simulation_id']
    store.start_simulation(db, other)
    store.fail_simulation(db, other, dict(code='INTERNAL_ERROR', message='other private', retryable=False))
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(db_path=db)), base_url='http://test') as client:
            r = await client.get(f'/api/simulations/{sid}/events', headers={
                'X-User-Id': args['user_id'], 'Last-Event-ID': cursor})
            assert r.status_code == 422
            assert r.json()['error']['code'] == 'VALIDATION_ERROR'
    asyncio.run(asyncio.wait_for(run(), 5))


def parse(text):
    result = []
    for block in text.split('\n\n'):
        if not block or block.startswith(':'):
            continue
        fields = dict(line.split(': ', 1) for line in block.splitlines())
        assert set(fields) == {'id', 'event', 'data'}
        fields['data'] = json.loads(fields['data'])
        result.append(fields)
    return result


@pytest.mark.parametrize('terminal', ['completed', 'failed'])
def test_terminal_replay_and_restart(context, terminal):
    db, args, *_ = context
    sid = create(context)
    finish_scenes(db, sid)
    if terminal == 'completed':
        store.complete_simulation(db, sid, score=80, headline='완료')
    else:
        store.fail_simulation(db, sid, dict(code='/private/key-secret', message='/private/password secret', retryable=True))
    saved = store.list_events(db, sid)
    async def run():
        for _ in range(2):
            app = create_app(db_path=db)
            async with app.router.lifespan_context(app):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                    for cursor in (None, saved[34]['id'], saved[-1]['id']):
                        headers = {'X-User-Id': args['user_id']}
                        if cursor is not None:
                            headers['Last-Event-ID'] = cursor
                        r = await client.get(f'/api/simulations/{sid}/events', headers=headers)
                        assert r.status_code == 200
                        assert r.headers['content-type'].startswith('text/event-stream')
                        assert r.headers['cache-control'] == 'no-cache'
                        assert r.headers['x-accel-buffering'] == 'no'
                        actual = parse(r.text)
                        expected = store.list_events(db, sid, after_event_id=cursor)
                        assert [(e['id'], e['event']) for e in actual] == [(e['id'], e['type']) for e in expected]
                        for a, e in zip(actual, expected):
                            if e['type'] != 'error':
                                assert a['data'] == e['data']
                        assert args['candidate']['name'] not in r.text
                        assert '/private' not in r.text and 'secret' not in r.text
                        if actual:
                            assert actual[-1]['event'] == ('error' if terminal == 'failed' else 'simulation_completed')
    asyncio.run(asyncio.wait_for(run(), 10))


@asynccontextmanager
async def serve(app):
    ready = asyncio.Event()
    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            ready.set()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = Server(uvicorn.Config(app, log_level='error', timeout_graceful_shutdown=1))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=5) as client:
            yield client
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 5)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            sock.close()


async def read_frame(lines):
    block = []
    async with asyncio.timeout(5):
        async for line in lines:
            if not line:
                return '\n'.join(block) + '\n\n'
            block.append(line)
    return None


def test_real_http_live_independent_subscribers_and_disconnect(start_context, monkeypatch):
    async def run():
        db, _, _, app = start_context
        dummy, payload, headers, impl = await setup(start_context)
        await dummy.aclose()
        closed = asyncio.Event()
        original = simulation_stream.stream_events
        active = 0
        async def tracked(*args):
            nonlocal active
            active += 1
            stream = original(*args)
            try:
                async for frame in stream:
                    yield frame
            finally:
                await stream.aclose()
                active -= 1
                closed.set()
        monkeypatch.setattr('app.simulation_api.stream_events', tracked)
        monkeypatch.setattr(simulation_stream, 'POLL_SECONDS', 0.01)
        monkeypatch.setattr(simulation_stream, 'HEARTBEAT_SECONDS', 0.02)
        async with serve(app) as client:
            r = await client.post('/api/simulations', json=payload, headers=headers)
            sid = r.json()['simulation_id']
            url = f'/api/simulations/{sid}/events'
            async with client.stream('GET', url, headers=headers) as first:
                async with client.stream('GET', url, headers=headers) as second:
                    lines1, lines2 = first.aiter_lines(), second.aiter_lines()
                    a, b = await asyncio.gather(read_frame(lines1), read_frame(lines2))
                    assert a == b and parse(a)[0]['event'] == 'simulation_started'
                    # 실행기가 gate에서 기다리는 동안 이미 첫 프레임을 수신했다.
                    assert store.get_simulation(db, sid)['status'] == 'running'
                    before = store.list_events(db, sid)
                    assert await read_frame(lines1) == ': ping\n\n'
                    assert store.list_events(db, sid) == before
                    assert store.get_simulation(db, sid)['progress']['done'] == 0
                await asyncio.wait_for(closed.wait(), 5)
                assert active == 1
                assert app.state.simulation_runner.tasks and impl.calls == 1
                impl.gate.set()
                received = []
                while True:
                    frame = await read_frame(lines1)
                    if frame is None:
                        break
                    received.extend(parse(frame))
                assert received[-1]['event'] == 'simulation_completed'
                assert len(received) == 81
                assert [e['id'] for e in received] == [e['id'] for e in store.list_events(db, sid)[1:]]
            assert impl.calls == 1
        assert active == 0
    asyncio.run(asyncio.wait_for(run(), 20))


def test_snapshot_wait_boundary_and_recovery(context, monkeypatch):
    db, args, *_ = context
    sid = create(context)
    store.start_simulation(db, sid)
    # 빈 페이지 스냅샷 직후 종료를 저장해도 다음 조회에서 반드시 받는다.
    batch = store.read_event_batch(db, sid, user_id=args['user_id'], after_event_id='0-0')
    assert batch == ('running', [])
    store.fail_simulation(db, sid, dict(code='INTERNAL_ERROR', message='private', retryable=False))
    monkeypatch.setattr(simulation_stream, 'POLL_SECONDS', 0.01)
    async def run():
        result = [frame async for frame in simulation_stream.stream_events(db, sid, args['user_id'], '0-0', batch)]
        assert parse(''.join(result))[0]['event'] == 'error'
        # 재시작 복구도 기존 실행기에 맡기며 저장된 시작 이벤트 다음 실패 이벤트를 읽는다.
        new_sid = store.create_or_reuse_simulation(db, **args)[0]['simulation_id']
        store.start_simulation(db, new_sid)
        app = create_app(db_path=db)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                r = await client.get(f'/api/simulations/{new_sid}/events', headers={
                    'X-User-Id': args['user_id'], 'Last-Event-ID': '0-0'})
                events = parse(r.text)
                assert len(events) == 1 and events[0]['event'] == 'error'
                assert events[0]['data']['retryable'] is False
                assert store.get_simulation(db, new_sid)['status'] == 'failed'
    asyncio.run(asyncio.wait_for(run(), 5))


def test_real_http_two_subscribers_receive_new_failure(start_context, monkeypatch):
    async def run():
        db, _, _, app = start_context
        dummy, payload, headers, impl = await setup(start_context, kind='error')
        await dummy.aclose()
        monkeypatch.setattr(simulation_stream, 'POLL_SECONDS', 0.01)
        async with serve(app) as client:
            r = await client.post('/api/simulations', json=payload, headers=headers)
            sid = r.json()['simulation_id']
            url = f'/api/simulations/{sid}/events'
            async with client.stream('GET', url, headers=headers) as first:
                async with client.stream('GET', url, headers={**headers, 'Last-Event-ID': '0-0'}) as second:
                    lines1, lines2 = first.aiter_lines(), second.aiter_lines()
                    assert parse(await read_frame(lines1))[0]['id'] == '0-0'
                    impl.gate.set()
                    a, b = await asyncio.gather(read_frame(lines1), read_frame(lines2))
                    assert a == b
                    assert parse(a)[0]['event'] == 'error'
                    assert 'private failure' not in a
                    assert await read_frame(lines1) is None
                    assert await read_frame(lines2) is None
                    assert impl.calls == 1
    asyncio.run(asyncio.wait_for(run(), 20))


def test_snapshot_boundary_preserves_new_scene(context, monkeypatch):
    db, args, *_ = context
    sid = create(context)
    store.start_simulation(db, sid)
    first = store.read_event_batch(db, sid, user_id=args['user_id'])
    event = engine_events(db, sid)[0]
    event['data']['scene']['situation'] = args['candidate']['name'] + '의 장면'
    store.save_event(db, sid, event)
    store.fail_simulation(db, sid, dict(code='INTERNAL_ERROR', message='private', retryable=False))
    async def run():
        result = [frame async for frame in simulation_stream.stream_events(db, sid, args['user_id'], None, first)]
        actual = parse(''.join(result))
        assert [e['event'] for e in actual] == ['simulation_started', 'scene_started', 'error']
        assert [e['id'] for e in actual] == ['0-0', '1-0', '1-1']
        assert actual[1]['data']['scene']['situation'] == '후보 A의 장면'
    asyncio.run(asyncio.wait_for(run(), 5))
