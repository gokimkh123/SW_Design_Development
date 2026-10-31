# 기능: 저장된 공개 이벤트를 구독별 커서로 읽어 SSE 프레임으로 전달한다.
# 시스템 범위: 실행기와 독립된 읽기 전용 구독이며 연결 취소 시 대기 작업도 취소된다.
# 결과: 제한된 페이지 조회, 15초 heartbeat, 종료 이벤트 전송 후 연결 종료를 제공한다.
import asyncio
import json
import logging

from starlette.concurrency import run_in_threadpool

from app import simulations as store

POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 15
logger = logging.getLogger(__name__)
ERROR_MESSAGES = {
    'INTERNAL_ERROR': '시뮬레이션 처리 중 오류가 발생했어요.',
    'LLM_UNAVAILABLE': 'AI 연결에 실패했어요.',
    'LLM_RATE_LIMITED': 'AI 요청이 많아요. 잠시 후 다시 시도해 주세요.',
}


def frame(event):
    data = event['data']
    if event['type'] == 'error':
        # 과거 저장 데이터에도 내부 예외·경로가 있을 수 있어 오류 자유 문구를 공개하지 않는다.
        code = data['code'] if data['code'] in ERROR_MESSAGES else 'INTERNAL_ERROR'
        data = dict(code=code, message=ERROR_MESSAGES[code], scene_index=data['scene_index'],
                    retryable=data['retryable'] if code != 'INTERNAL_ERROR' else False)
    return f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_events(database, sid, user_id, cursor, batch):
    last_sent = asyncio.get_running_loop().time()
    try:
        while batch is not None:
            status, events = batch
            for event in events:
                yield frame(event)
                cursor = event['id']
                last_sent = asyncio.get_running_loop().time()
                if event['type'] in ('simulation_completed', 'error'):
                    return
            # 상태와 페이지가 같은 트랜잭션의 스냅샷이라 종료 직전 이벤트를 놓치지 않는다.
            if not events:
                if status in ('completed', 'failed'):
                    return
                if asyncio.get_running_loop().time() - last_sent >= HEARTBEAT_SECONDS:
                    yield ': ping\n\n'
                    last_sent = asyncio.get_running_loop().time()
                await asyncio.sleep(POLL_SECONDS)
            batch = await run_in_threadpool(store.read_event_batch, database, sid,
                user_id=user_id, after_event_id=cursor)
    except Exception:
        # 이미 200을 시작한 뒤의 장애는 가짜 업무 이벤트를 만들지 않고 연결만 닫는다.
        logger.exception('SSE 저장 이벤트 조회 실패: %s', sid)
