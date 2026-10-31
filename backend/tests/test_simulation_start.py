# 기능: 시작 API와 백그라운드 실행의 저장·종료 계약을 검증한다.
# 시스템 범위: 임시 DB와 제어 가능한 가짜 어댑터만 사용한다.
# 결과: 중복·오류·취소·재시작에서도 공개 결과와 상태가 일관적인지 검사한다.
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app import simulations as store, fake_engine
from app.engine_adapter import EngineAdapter, get_engine
from app.main import create_app
from app.personas import create_persona, PersonaData
from app.users import create_user
from app.candidates import select_candidates
from app.database import connect_database

SEEDS = Path(__file__).resolve().parents[2] / 'data/seed/personas.json'


@pytest.fixture
def context(tmp_path):
    db = tmp_path / 'test.db'
    user = create_user(db, '테스터')
    raw = json.loads(SEEDS.read_text())['personas'][0]
    data = {k: raw[k] for k in PersonaData.model_fields}
    data['is_seed'] = False
    me = create_persona(db, user['user_id'], data)
    app = create_app(db_path=db)
    return db, user, me, app


class Controlled:
    load_scenes = staticmethod(fake_engine.load_scenes)
    score = staticmethod(fake_engine.score)
    headline = staticmethod(fake_engine.headline)

    def __init__(self, kind='ok'):
        self.kind = kind
        self.calls = 0
        self.gate = asyncio.Event()
        self.inputs = []

    async def simulate(self, me, candidate, **kwargs):
        self.calls += 1
        self.inputs.append(candidate)
        await self.gate.wait()
        if self.kind == 'error':
            raise RuntimeError('private failure')
        if self.kind == 'short':
            return
        async for event in fake_engine.simulate(me, candidate, **kwargs):
            yield event


async def setup(context, kind='ok'):
    db, user, me, app = context
    impl = Controlled(kind)
    app.dependency_overrides[get_engine] = lambda: EngineAdapter(impl)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test')
    payload = dict(persona_id=me['persona_id'], candidate_id=select_candidates(me, SEEDS).candidates[0].candidate_id)
    return client, payload, {'X-User-Id': user['user_id']}, impl


def test_start_parallel_reuse_and_complete(context):
    async def run():
        db, _, me, app = context
        client, payload, headers, impl = await setup(context)
        async with client:
            responses = await asyncio.gather(*[client.post('/api/simulations', json=payload, headers=headers) for _ in range(8)])
            assert sorted(r.status_code for r in responses) == [200]*7+[202]
            sid = responses[0].json()['simulation_id']
            assert {r.json()['simulation_id'] for r in responses} == {sid}
            await asyncio.sleep(0)
            assert impl.calls == 1
            assert store.get_simulation(db, sid)['progress']['done'] == 0
            # 세 후보 작업을 동시에 예약하며 첫 작업은 아직 gate에서 대기한다.
            for card in select_candidates(me, SEEDS).candidates[1:]:
                r = await client.post('/api/simulations', json=dict(payload, candidate_id=card.candidate_id), headers=headers)
                assert r.status_code == 202
            impl.gate.set()
            await asyncio.gather(*list(app.state.simulation_runner.tasks))
            assert impl.calls == 3
            assert all(c['nickname'].startswith('후보 ') for c in impl.inputs)
            assert store.get_simulation(db, sid)['status'] == 'completed'
            assert len(store.list_scenes(db, sid)) == 20
            assert store.get_completion(db, sid)['report'] is None
            with connect_database(db) as conn:
                ids = [r[0] for r in conn.execute('SELECT simulation_id FROM simulations')]
            for run_id in ids:
                assert store.get_simulation(db, run_id)['progress'] == {'done': 20, 'total': 20}
                events = store.list_events(db, run_id)
                assert events[0]['data']['simulation_id'] == run_id
                record = store.get_internal_record(db, run_id)
                for key in ('name', 'nickname'):
                    name = record['inputs']['candidate'].get(key)
                    if name:
                        assert name not in json.dumps(events, ensure_ascii=False)
            r = await client.post('/api/simulations', json=payload, headers=headers)
            assert r.status_code == 200 and r.json()['status'] == 'completed'
    asyncio.run(run())


@pytest.mark.parametrize('kind, expected', [('error', '실행 또는 DB'), ('short', '모든 장면'), ('timeout', '시간이 초과'), ('cancel', '취소')])
def test_terminal_failures(context, kind, expected):
    async def run():
        db, _, _, app = context
        client, payload, headers, impl = await setup(context, kind)
        if kind == 'timeout':
            app.state.simulation_runner.timeout = .02
        async with client:
            r = await client.post('/api/simulations', json=payload, headers=headers)
            sid = r.json()['simulation_id']
            await asyncio.sleep(0)
            tasks = list(app.state.simulation_runner.tasks)
            if kind == 'cancel':
                await app.state.simulation_runner.close()
            else:
                if kind != 'timeout':
                    impl.gate.set()
                await asyncio.gather(*tasks)
            record = store.get_internal_record(db, sid)
            assert record['status'] == 'failed'
            assert expected in record['failure']['message']
    asyncio.run(run())


def test_validation(context):
    async def run():
        client, payload, headers, impl = await setup(context)
        async with client:
            for h in ({}, {'X-User-Id': 'missing'}):
                assert (await client.post('/api/simulations', json=payload, headers=h)).status_code == 401
            other = create_user(context[0], '다른사용자')
            assert (await client.post('/api/simulations', json=payload, headers={'X-User-Id': other['user_id']})).status_code == 404
            for change, status in [({'persona_id':'missing'},404), ({'candidate_id':'missing'},404),
                                   ({'candidate_id':context[2]['persona_id']},404), ({'mode':'agents'},422),
                                   ({'candidate_id':1},422), ({'extra':True},422)]:
                r = await client.post('/api/simulations', json=dict(payload, **change), headers=headers)
                assert r.status_code == status
                assert 'error' in r.json()
            assert impl.calls == 0
    asyncio.run(run())


@pytest.mark.parametrize('failure', ['launch', 'save', 'create', 'persistent'])
def test_storage_and_launch_failures(context, monkeypatch, failure):
    async def run():
        db, _, _, app = context
        client, payload, headers, impl = await setup(context)
        def broken(*args, **kwargs):
            raise OSError('DB unavailable')
        with monkeypatch.context() as patch:
            if failure == 'launch':
                patch.setattr(app.state.simulation_runner, 'launch', broken)
            elif failure == 'create':
                patch.setattr(store, 'create_or_reuse_simulation', broken)
            else:
                patch.setattr(store, 'save_event', broken)
                if failure == 'persistent':
                    patch.setattr(store, 'fail_simulation', broken)
            async with client:
                r = await client.post('/api/simulations', json=payload, headers=headers)
                if failure in ('launch', 'create'):
                    assert r.status_code == 500
                else:
                    impl.gate.set()
                    await asyncio.gather(*list(app.state.simulation_runner.tasks))
        await app.state.simulation_runner.close()
        with connect_database(db) as conn:
            statuses = [r[0] for r in conn.execute('SELECT status FROM simulations')]
        assert statuses == ([] if failure == 'create' else ['failed'])
    asyncio.run(run())


def test_replay_and_restart(context, tmp_path):
    async def run():
        db, _, _, app = context
        client, payload, headers, impl = await setup(context)
        async with client:
            r = await client.post('/api/simulations', json=dict(payload, mode='replay'), headers=headers)
            assert r.status_code == 202 and r.json()['mode'] == 'live'
            sid = r.json()['simulation_id']
            await asyncio.sleep(0)
            await app.state.simulation_runner.close()
            assert store.get_simulation(db, sid)['status'] == 'failed'
        # 중단된 프로세스의 미종료 예약을 재현한다.
        record = store.get_internal_record(db, sid)
        fresh, _ = store.create_or_reuse_simulation(db, user_id=context[1]['user_id'],
            persona_id=context[2]['persona_id'], candidate=record['inputs']['candidate'],
            alias='후보 A', scenes=record['inputs']['scenes'])
        restarted = create_app(db_path=db)
        async with restarted.router.lifespan_context(restarted):
            assert store.get_simulation(db, fresh['simulation_id'])['status'] == 'failed'
        # 데이터가 있어도 미정 형식을 성공으로 가장하지 않는다.
        (tmp_path / 'replay.json').write_text('{}')
        replay_app = create_app(db_path=db, replay_path=tmp_path)
        replay_app.dependency_overrides[get_engine] = lambda: EngineAdapter(impl)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=replay_app), base_url='http://test') as c:
            r = await c.post('/api/simulations', json=dict(payload, mode='replay'), headers=headers)
            assert r.status_code == 500
    asyncio.run(run())


def test_queued_reservation_is_not_started(context):
    async def run():
        db, _, _, app = context
        client, payload, headers, impl = await setup(context)
        async with client:
            r = await client.post('/api/simulations', json=payload, headers=headers)
            sid = r.json()['simulation_id']
            await asyncio.sleep(0)
            await app.state.simulation_runner.close()
            with connect_database(db) as conn:
                conn.execute("DELETE FROM simulation_events WHERE simulation_id=?", (sid,))
                conn.execute("UPDATE simulations SET status='queued', failure=NULL, failed_at=NULL WHERE simulation_id=?", (sid,))
            r = await client.post('/api/simulations', json=payload, headers=headers)
            assert r.status_code == 500
            assert impl.calls == 1
            assert store.get_simulation(db, sid)['status'] == 'queued'
    asyncio.run(run())


def test_cancellation_before_first_task_step(context):
    async def run():
        db, _, _, app = context
        client, payload, headers, _ = await setup(context)
        async with client:
            r = await client.post('/api/simulations', json=payload, headers=headers)
            await app.state.simulation_runner.close()
            assert store.get_simulation(db, r.json()['simulation_id'])['status'] == 'failed'
    asyncio.run(run())
