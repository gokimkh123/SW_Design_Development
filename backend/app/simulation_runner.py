# 기능: 시뮬레이션 백그라운드 작업과 장면 저장·완료·실패를 관리한다.
# 시스템 범위: 단일 프로세스 실행기이며 엔진 어댑터와 기존 저장 계약만 사용한다.
# 결과: 순차 장면과 최종 점수 또는 구분된 종료 오류를 DB에 남긴다.
# 한계
# 1. 동일 DB당 단일 서버 프로세스(workers=1)만 지원한다. 다중 프로세스에서는
#    재시작 복구가 다른 프로세스의 실행을 실패 처리할 수 있어 실행 관리 보완이 필요하다.
# 2. 현재 체크아웃에는 실제 엔진 구현이 없어 실제 LLM 연동·성능과
#    LLM_MAX_CONCURRENCY 적용 여부를 검증하지 못했다. 엔진 통합 후 확인해야 한다.
# 3. DB가 계속 쓰기 불가능하면 실패 상태도 저장할 수 없다. 종료 시 재시도하며,
#    지속 장애·강제 종료 후에는 DB 복구와 서버 재시작으로 미종료 실행을 정리해야 한다.
# 4. SQLite 호출은 동기 방식이므로 DB 잠금 대기 중 이벤트 루프가 지연될 수 있다.
# 5. 기존 엔진 인터페이스는 저장된 장면 목록을 입력받지 않는다. 장면 ID·순서는
#    저장 시 검증하지만, 템플릿 변경 후 동일 내용 재현에는 엔진 계약 보완이 필요하다.
import asyncio
from contextlib import aclosing
import logging
import os

from app import simulations as store
from app.database import connect_database, initialize_database
from app.engine_adapter import EngineError

logger = logging.getLogger(__name__)


class SimulationRunner:
    def __init__(self, database):
        self.database = database
        self.tasks = set()
        self.task_ids = {}
        self.pending_failures = {}
        self.closing = False
        self.timeout = float(os.getenv('SIMULATION_TIMEOUT_SECONDS', '180'))
        if self.timeout <= 0:
            raise ValueError('SIMULATION_TIMEOUT_SECONDS must be positive')

    def fail(self, sid, message, code='INTERNAL_ERROR', retryable=False):
        error = dict(code=code, message=message, retryable=retryable)
        self.pending_failures[sid] = error
        try:
            store.fail_simulation(self.database, sid, error)
        except Exception:
            logger.exception('시뮬레이션 실패 저장 불가: %s (재시작 복구 필요)', sid)
        else:
            self.pending_failures.pop(sid, None)
            logger.info('시뮬레이션 failed: %s %s', sid, message)

    def recover(self):
        # 기존 저장 계약대로 이전 worker 종료가 보장되는 단일 프로세스에서만 호출한다.
        if not self.database.exists():
            return
        initialize_database(self.database)
        with connect_database(self.database) as db:
            ids = [row[0] for row in db.execute(
                "SELECT simulation_id FROM simulations WHERE status IN ('running','queued')")]
        for sid in ids:
            store.fail_simulation(self.database, sid, dict(code='INTERNAL_ERROR',
                message='서버 재시작으로 실행이 중단되었습니다.', retryable=False))

    def launch(self, sid, engine):
        if self.closing:
            raise RuntimeError('서버가 종료 중입니다.')
        coroutine = self.run(sid, engine)
        try:
            task = asyncio.create_task(coroutine)
        except BaseException:
            coroutine.close()
            raise
        self.tasks.add(task)
        self.task_ids[task] = sid
        task.add_done_callback(self.finished)

    def finished(self, task):
        self.tasks.discard(task)
        sid = self.task_ids.pop(task)
        # 첫 coroutine 실행 전에 취소되면 run의 예외 처리에 진입하지 않는다.
        if task.cancelled():
            try:
                if store.get_simulation(self.database, sid)['status'] == 'running':
                    self.fail(sid, '시뮬레이션 작업이 취소되었습니다.')
            except Exception:
                self.fail(sid, '시뮬레이션 작업이 취소되었습니다.')
        if not task.cancelled() and task.exception() is not None:
            logger.error('실행기 예외', exc_info=task.exception())

    async def run(self, sid, engine):
        try:
            async with asyncio.timeout(self.timeout):
                inputs = store.get_execution_inputs(self.database, sid)
                store.start_simulation(self.database, sid)
                async with aclosing(engine.simulate(inputs['me'], inputs['candidate'],
                                                    mode=inputs['engine_mode'])) as stream:
                    async for event in stream:
                        store.save_event(self.database, sid, event)
                        if event['type'] == 'error':
                            return
                        await asyncio.sleep(0)
                scenes = store.list_scenes(self.database, sid)
                if len(scenes) != 20 or any('verdict' not in scene or not scene['dialogue'] for scene in scenes):
                    self.fail(sid, '엔진 이벤트가 모든 장면을 처리하기 전에 종료되었습니다.')
                    return
                judgements = [dict({k: scene[k] for k in (
                    'scene_index', 'verdict', 'reason', 'agreement', 'rule_candidate', 'unresolved')},
                    scene_id=scene['scene']['scene_id']) for scene in scenes]
                score = engine.score(judgements)
                store.complete_simulation(self.database, sid, score=score, headline=engine.headline(score))
                logger.info('시뮬레이션 completed: %s (20/20)', sid)
        except asyncio.CancelledError:
            self.fail(sid, '시뮬레이션 작업이 취소되었습니다.')
            raise
        except TimeoutError:
            self.fail(sid, '시뮬레이션 실행 시간이 초과되었습니다.', 'LLM_UNAVAILABLE')
        except EngineError as exc:
            self.fail(sid, exc.message, exc.code, exc.retryable)
        except Exception:
            logger.exception('시뮬레이션 실행 또는 저장 실패: %s', sid)
            self.fail(sid, '시뮬레이션 실행 또는 DB 저장에 실패했습니다.')

    async def close(self):
        self.closing = True
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for sid, error in list(self.pending_failures.items()):
            self.fail(sid, error['message'], error['code'], error['retryable'])
