# 기능: 완료된 시뮬레이션으로 매칭과 생활 규칙 초안을 만들고 동의 상태를 저장한다.
# 시스템 범위: SQLite 저장과 규칙 초안 검증을 담당하며 HTTP 응답은 제외한다.
# 결과: 소유자별 조회, 시뮬레이션당 매칭 1건, 매칭 후에만 공개되는 상대 정보를 제공한다.
import asyncio
from datetime import datetime, timedelta, timezone
import json
import secrets
import string

from app.engine_adapter import EngineAdapter, EngineError
from app import simulations as store

ROOM = '302호 (배정 예정)'  # 호실 배정 규칙이 없어 API.md 예시 값을 고정 사용
DRAFT_TIMEOUT_SECONDS = 10  # API.md 4.12: 규칙 초안 생성 최대 10초
AREA_LABELS = {
    'quiet_hours': '조용한 시간',
    'guests': '친구 초대',
    'cleaning': '청소',
    'fridge': '냉장고',
    'climate': '냉난방',
    'supplies': '공용품',
}
PARTNER_FIELDS = ('persona_id', 'name', 'department', 'year', 'type_name', 'greeting')


def _new_id(prefix):
    return prefix + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


def _now():
    return datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')


def _public(row):
    # 상대 이름은 수락된 매칭에서만 공개한다.
    return dict(match_id=row['match_id'], simulation_id=row['simulation_id'], status=row['status'],
                partner=json.loads(row['partner']) if row['status'] == 'accepted' else None,
                room=row['room'], rules_status=row['rules_status'])


def _owned(db, match_id, user_id):
    return db.execute('SELECT * FROM matches WHERE match_id=? AND user_id=?', (match_id, user_id)).fetchone()


def _rule_set(db, row):
    rules = db.execute('SELECT * FROM rules WHERE match_id=? ORDER BY position', (row['match_id'],)).fetchall()
    return dict(match_id=row['match_id'], status=row['rules_status'],
                rules=[dict(rule_id=r['rule_id'], area=r['area'], area_label=r['area_label'], text=r['text'],
                            source=dict(scene_index=r['source_scene_index'], day=r['source_day'],
                                        verdict=r['source_verdict'])) for r in rules],
                agreements=dict(me=bool(row['agreed_me']), partner=bool(row['agreed_partner'])))


def get_match(db_path, match_id, *, user_id):
    with store._connection(db_path) as db:
        row = _owned(db, match_id, user_id)
        return _public(row) if row else None


def get_match_for_simulation(db_path, simulation_id, *, user_id):
    with store._connection(db_path) as db:
        row = db.execute('SELECT * FROM matches WHERE simulation_id=? AND user_id=?',
                         (simulation_id, user_id)).fetchone()
        return _public(row) if row else None


def get_rules(db_path, match_id, *, user_id):
    with store._connection(db_path) as db:
        row = _owned(db, match_id, user_id)
        return _rule_set(db, row) if row else None


def agree_rules(db_path, match_id, *, user_id):
    """본인 동의 기록. 상대는 시드 후보뿐이므로 자동 동의하며 반복 호출해도 결과가 같다."""
    with store._connection(db_path, write=True) as db:
        if _owned(db, match_id, user_id) is None:
            return None
        db.execute("UPDATE matches SET agreed_me=1, agreed_partner=1, rules_status='confirmed' WHERE match_id=?",
                   (match_id,))
        return _rule_set(db, _owned(db, match_id, user_id))


def load_match_inputs(db_path, simulation_id, *, user_id):
    """소유 실행의 내부 입력. 없으면 None, 미완료면 StorageConflictError."""
    record = store.get_internal_record(db_path, simulation_id, user_id=user_id)
    if record is None:
        return None
    if record['status'] != 'completed':
        raise store.StorageConflictError('완료되지 않은 실행입니다.')
    return record, store.list_scenes(db_path, simulation_id, user_id=user_id)


def validate_rules(drafts, scenes, *, alias, name):
    """영역별 1개를 고정 순서로 정리한다. 출처의 일차·판정은 저장된 장면 값을 사용한다."""
    by_area = {d.get('area'): d for d in drafts}
    if len(drafts) != len(AREA_LABELS) or set(by_area) != set(AREA_LABELS):
        raise ValueError('규칙 초안은 6개 영역에 1개씩이어야 합니다.')
    stored = {scene['scene_index']: scene for scene in scenes}
    rules = []
    for area, label in AREA_LABELS.items():
        draft = by_area[area]
        text, source = draft.get('text'), draft.get('source') or {}
        scene = stored.get(source.get('scene_index'))
        if not isinstance(text, str) or not text.strip() or scene is None:
            raise ValueError('규칙 초안의 문구 또는 출처 장면이 올바르지 않습니다.')
        # 초안은 익명 입력으로 만들어지므로 매칭 후 화면에는 상대 이름으로 표시한다.
        rules.append(dict(area=area, area_label=label, text=text.replace(alias, name),
                          source_scene_index=scene['scene_index'], source_day=scene['scene']['day'],
                          source_verdict=scene['verdict']))
    return rules


async def draft_match_rules(engine: EngineAdapter, record, scenes):
    inputs = record['engine_inputs']
    judgements = [dict({k: scene[k] for k in (
        'scene_index', 'verdict', 'reason', 'agreement', 'rule_candidate', 'unresolved')},
        scene_id=scene['scene']['scene_id']) for scene in scenes]
    try:
        drafts = await asyncio.wait_for(engine.draft_rules(inputs['me'], inputs['candidate'], judgements),
                                        DRAFT_TIMEOUT_SECONDS)
    except TimeoutError:
        raise EngineError('LLM_UNAVAILABLE', 503, 'AI 연결에 실패했어요.', retryable=True) from None
    candidate = record['inputs']['candidate']
    return validate_rules(drafts, scenes, alias=record['alias'], name=candidate['name'])


def create_match(db_path, record, rules):
    """매칭과 규칙을 한 트랜잭션으로 저장한다. 동시 신청이면 먼저 저장된 매칭을 반환한다."""
    candidate = record['inputs']['candidate']
    partner = {k: candidate[k] for k in PARTNER_FIELDS}
    with store._connection(db_path, write=True) as db:
        row = db.execute('SELECT * FROM matches WHERE simulation_id=?', (record['simulation_id'],)).fetchone()
        if row is not None:
            return _public(row)
        for _ in range(10):
            match_id = _new_id('mat_')
            if db.execute('''INSERT INTO matches
                    (match_id,simulation_id,user_id,status,partner,room,rules_status,created_at)
                    VALUES (?,?,?,'accepted',?,?,'draft',?) ON CONFLICT(match_id) DO NOTHING''',
                    (match_id, record['simulation_id'], record['user_id'],
                     json.dumps(partner, ensure_ascii=False), ROOM, _now())).rowcount:
                break
        else:
            raise RuntimeError('매칭 ID 생성 재시도 한도 초과')
        for position, rule in enumerate(rules, 1):
            for _ in range(10):
                if db.execute('''INSERT INTO rules
                        (rule_id,match_id,position,area,area_label,text,
                         source_scene_index,source_day,source_verdict)
                        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(rule_id) DO NOTHING''',
                        (_new_id('rul_'), match_id, position, rule['area'], rule['area_label'], rule['text'],
                         rule['source_scene_index'], rule['source_day'], rule['source_verdict'])).rowcount:
                    break
            else:
                raise RuntimeError('규칙 ID 생성 재시도 한도 초과')
        return _public(_owned(db, match_id, record['user_id']))
