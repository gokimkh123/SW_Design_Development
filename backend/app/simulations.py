# 기능: 실행 입력을 고정하고 장면·이벤트·진행률·완료·실패를 원자적으로 저장한다.
# 시스템 범위: 실행기에서 호출할 SQLite 저장 계층이며 엔진 실행·HTTP·SSE 전송은 제외한다.
# 결과: 소유자별 조회, 중복 없는 실행 재사용과 재시도, 익명 공개 이벤트를 제공한다.
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sqlite3
import string
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.database import connect_database, initialize_database
from app.engine_adapter import resolve_mode
from app.personas import JSON_FIELDS, PersonaData

VERDICTS = ('harmonious', 'negotiated', 'conflict', 'pending')
TRANSITIONS = {'queued': {'running', 'failed'}, 'running': {'completed', 'failed'},
               'completed': set(), 'failed': set()}


class StorageConflictError(ValueError):
    """상태·순서 또는 동일 재시도 키의 내용이 기존 데이터와 충돌한다."""


class EventData(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')


class Scene(EventData):
    scene_id: str
    day: int = Field(ge=1, le=7)
    weekday: str
    time: str
    category: str
    title: str
    situation: str


class SceneStarted(EventData):
    scene_index: int = Field(ge=1)
    scene: Scene


class Utterance(EventData):
    scene_index: int = Field(ge=1)
    turn: int = Field(ge=1, le=4)
    speaker: Literal['me', 'candidate']
    name: str
    text: str


class RuleCandidate(EventData):
    area: Literal['quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies']
    text: str


class Progress(EventData):
    done: int = Field(ge=0)
    total: int = Field(gt=0)


class Judged(EventData):
    scene_index: int = Field(ge=1)
    scene_id: str | None = None  # fake_engine에는 없고 실제 판정 모델에는 있음
    verdict: Literal['harmonious', 'negotiated', 'conflict', 'pending']
    reason: str
    agreement: str | None
    rule_candidate: RuleCandidate | None
    unresolved: str | None
    progress: Progress


class Failure(EventData):
    code: str
    message: str
    scene_index: int | None = Field(default=None, ge=1)
    retryable: bool


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _now():
    return datetime.now(timezone(timedelta(hours=9))).isoformat()


def new_simulation_id():
    return 'sim_' + ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))


@contextmanager
def _connection(path, *, write=False):
    initialize_database(path)
    with connect_database(path) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db


def _run(db, simulation_id, user_id=None):
    return db.execute('SELECT * FROM simulations WHERE simulation_id=? '
                      'AND (? IS NULL OR user_id=?)',
                      (simulation_id, user_id, user_id)).fetchone()


def _required(db, simulation_id, user_id=None):
    row = _run(db, simulation_id, user_id)
    if row is None:
        raise LookupError('시뮬레이션을 찾을 수 없습니다.')
    return row


def _persona(db, persona_id, user_id=None):
    row = db.execute('SELECT p.*, u.nickname FROM personas p JOIN users u USING(user_id) '
                     'WHERE persona_id=? AND (? IS NULL OR p.user_id=?)',
                     (persona_id, user_id, user_id)).fetchone()
    if row is None:
        raise LookupError('페르소나를 찾을 수 없습니다.')
    value = dict(row)
    for field in JSON_FIELDS:
        value[field] = json.loads(value[field])
    value['is_seed'] = bool(value['is_seed'])
    return value


def _anonymize(value, candidate, alias):
    # 자유 문구에도 알려진 이름을 치환한다. 공개 스키마의 키에는 원본 메타데이터를 넣지 않는다.
    names = sorted({candidate.get(k) for k in ('name', 'nickname') if candidate.get(k)}, key=len, reverse=True)
    def clean(item):
        if isinstance(item, str):
            for name in names:
                item = item.replace(name, alias)
            return item
        if isinstance(item, list):
            return [clean(v) for v in item]
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items()}
        return item
    return clean(value)


def _public_data(row, value):
    return _anonymize(value, json.loads(row['inputs'])['candidate'], row['alias'])


def _counts(db, simulation_id):
    counts = dict.fromkeys(VERDICTS, 0)
    for row in db.execute('SELECT judgement FROM simulation_scenes '
                          'WHERE simulation_id=? AND judgement IS NOT NULL', (simulation_id,)):
        counts[json.loads(row[0])['verdict']] += 1
    return counts


def _simulation(db, row):
    result = json.loads(row['result']) if row['result'] else None
    return {**{k: row[k] for k in ('simulation_id', 'persona_id', 'candidate_id', 'mode',
                                  'status', 'started_at', 'completed_at')},
            'progress': {'done': row['done'], 'total': row['total']},
            'verdict_counts': _counts(db, row['simulation_id']),
            'score': result['score'] if result else None}


def create_or_reuse_simulation(db_path: Path, *, user_id: str, persona_id: str,
                               candidate: dict, alias: str, scenes: list[dict],
                               mode: str = 'live') -> tuple[dict, bool]:
    """실제 API 모드를 받아 (공개 Simulation, created)를 반환한다.

    시드는 검증·선정한 원본 dict, DB 후보는 persona_id/is_seed=false를 전달한다.
    같은 키의 running/completed를 재사용한다. 생성 시 running으로 예약하며 실행하지 않는다.
    """
    if mode not in ('live', 'replay') or alias not in ('후보 A', '후보 B', '후보 C'):
        raise ValueError('실제 API 모드와 후보 별칭을 확인해 주세요.')
    if not scenes or len({s['scene_id'] for s in scenes}) != len(scenes):
        raise ValueError('장면 목록은 비어 있거나 ID가 중복될 수 없습니다.')
    with _connection(db_path, write=True) as db:
        me = _persona(db, persona_id, user_id)
        candidate_id = candidate['persona_id']
        existing = db.execute('SELECT * FROM simulations WHERE persona_id=? AND candidate_id=? '
                              "AND mode=? AND status IN ('running', 'completed', 'queued')",
                              (persona_id, candidate_id, mode)).fetchone()
        if existing:
            if existing['status'] == 'queued':
                raise StorageConflictError('대기 실행이 이미 예약되어 있습니다. 실행기 정책을 확인하세요.')
            return _simulation(db, existing), False
        if candidate.get('is_seed') is not True:
            candidate = _persona(db, candidate_id)
        else:
            # JSON 시드 ID는 personas FK로 참조하거나 가짜 사용자 행으로 삽입하지 않는다.
            PersonaData.model_validate({k: candidate[k] for k in PersonaData.model_fields})
            if candidate.get('candidate_pool') is not True:
                raise ValueError('후보 풀의 시드가 아닙니다.')
        if candidate_id == persona_id or candidate.get('user_id') == user_id:
            raise ValueError('본인은 후보가 될 수 없습니다.')
        if not isinstance(candidate.get('nickname'), str) or not candidate['nickname']:
            raise ValueError('후보 닉네임이 필요합니다.')
        candidate_input = {k: candidate[k] for k in PersonaData.model_fields}
        candidate_input.update(persona_id=candidate_id, user_id=candidate['user_id'], nickname=alias)
        if 'created_at' in candidate:
            candidate_input['created_at'] = candidate['created_at']
        candidate_input = _anonymize(candidate_input, candidate, alias)
        inputs = _json({'me': me, 'candidate': candidate, 'scenes': scenes})
        engine_inputs = _json({'me': _anonymize(me, candidate, alias), 'candidate': candidate_input,
                              'scenes': _anonymize(scenes, candidate, alias)})
        engine_mode = resolve_mode('live') if mode == 'live' else None
        for _ in range(10):
            sim_id, now = new_simulation_id(), _now()
            cursor = db.execute('''INSERT INTO simulations
                (simulation_id,user_id,persona_id,candidate_id,mode,engine_mode,status,alias,
                 inputs,engine_inputs,total,created_at,started_at)
                VALUES (?,?,?,?,?,?,'running',?,?,?,?,?,?)
                ON CONFLICT(simulation_id) DO NOTHING''',
                (sim_id, user_id, persona_id, candidate_id, mode, engine_mode, alias,
                 inputs, engine_inputs, len(scenes), now, now))
            if cursor.rowcount:
                return _simulation(db, _required(db, sim_id)), True
        raise RuntimeError('시뮬레이션 ID 생성 재시도 한도 초과')


def get_simulation(db_path, simulation_id, *, user_id=None):
    with _connection(db_path) as db:
        row = _run(db, simulation_id, user_id)
        return _simulation(db, row) if row else None


def get_execution_inputs(db_path, simulation_id, *, user_id=None):
    """엔진용 익명 입력과 고정 모드. HTTP 응답용이 아닌 내부 실행기 전용."""
    with _connection(db_path) as db:
        row = _run(db, simulation_id, user_id)
        return dict(json.loads(row['engine_inputs']), mode=row['mode'], engine_mode=row['engine_mode']) if row else None


def get_internal_record(db_path, simulation_id, *, user_id=None):
    """운영·후속 내부 처리 전용. 원본 후보 실명이 있으므로 공개 응답에 사용 금지."""
    with _connection(db_path) as db:
        row = _run(db, simulation_id, user_id)
        if row is None:
            return None
        value = dict(row)
        for field in ('inputs', 'engine_inputs', 'result', 'failure'):
            value[field] = json.loads(value[field]) if value[field] else None
        return value


def _transition(row, target):
    if target not in TRANSITIONS[row['status']]:
        raise StorageConflictError(f"허용되지 않는 상태 전이: {row['status']} → {target}")


def _event_value(row):
    return {'id': row['event_id'], 'sequence': row['sequence'], 'type': row['type'],
            'data': json.loads(row['data'])}


def _previous(db, sid, key, event_type, data):
    previous = db.execute('SELECT * FROM simulation_events WHERE simulation_id=? AND event_key=?',
                          (sid, key)).fetchone()
    if previous:
        if previous['type'] != event_type or previous['internal_data'] != _json(data):
            raise StorageConflictError('동일 이벤트 재시도의 내용이 다릅니다.')
        return _event_value(previous)
    return None


def _append(db, row, key, event_type, data, scene_index):
    sid = row['simulation_id']
    sequence = db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM simulation_events '
                          'WHERE simulation_id=?', (sid,)).fetchone()[0]
    # 문자열 ID를 정렬하지 않는다. 장면별 순번과 전역 sequence를 별도로 유지한다.
    ordinal = db.execute('SELECT count(*) FROM simulation_events WHERE simulation_id=? '
                         "AND event_id LIKE ?", (sid, f'{scene_index}-%')).fetchone()[0]
    event_id = f'{scene_index}-{ordinal}'
    public = _public_data(row, data)
    db.execute('INSERT INTO simulation_events VALUES (?,?,?,?,?,?,?,?)',
               (sid, sequence, event_id, key, event_type, _json(public), _json(data), _now()))
    return {'id': event_id, 'sequence': sequence, 'type': event_type, 'data': public}


def start_simulation(db_path, simulation_id, *, user_id=None):
    """백엔드 시작 이벤트를 저장한다. 재호출은 동일 이벤트를 반환하며 엔진은 호출하지 않는다."""
    with _connection(db_path, write=True) as db:
        row = _required(db, simulation_id, user_id)
        inputs = json.loads(row['engine_inputs'])
        data = {'simulation_id': simulation_id, 'mode': row['mode'], 'total_scenes': row['total'],
                'me': {'name': inputs['me']['nickname'], 'type_name': inputs['me']['type_name']},
                'candidate': {'alias': row['alias'], 'type_name': inputs['candidate']['type_name']}}
        previous = _previous(db, simulation_id, 'started', 'simulation_started', data)
        if previous:
            return previous
        if row['status'] == 'queued':
            _transition(row, 'running')
            db.execute("UPDATE simulations SET status='running', started_at=? WHERE simulation_id=?",
                       (_now(), simulation_id))
        elif row['status'] != 'running':
            raise StorageConflictError('종료된 실행은 시작할 수 없습니다.')
        return _append(db, row, 'started', 'simulation_started', data, 0)


def _progress(db, row):
    count = db.execute('SELECT count(*) FROM simulation_scenes WHERE simulation_id=? '
                       'AND judgement IS NOT NULL', (row['simulation_id'],)).fetchone()[0]
    db.execute('UPDATE simulations SET done=? WHERE simulation_id=?', (count, row['simulation_id']))
    return {'done': count, 'total': row['total']}


def update_progress(db_path, simulation_id, *, user_id=None):
    """판정 저장 건수에서 재계산한다. 증가량을 받지 않아 재시도 시 중복 증가하지 않는다."""
    with _connection(db_path, write=True) as db:
        row = _required(db, simulation_id, user_id)
        if row['status'] not in ('running', 'completed'):
            raise StorageConflictError('진행률을 갱신할 수 없는 상태입니다.')
        return _progress(db, row)


def save_event(db_path, simulation_id, event: dict, *, user_id=None):
    """어댑터 장면 이벤트를 받아 장면·공개 이벤트·진행률을 한 트랜잭션으로 저장한다."""
    kind = event['type']
    if kind == 'error':
        return fail_simulation(db_path, simulation_id, event['data'], user_id=user_id)
    models = {'scene_started': SceneStarted, 'utterance': Utterance, 'scene_judged': Judged}
    if kind not in models:
        raise ValueError('시작·완료 이벤트는 전용 저장 함수를 사용하세요.')
    data = models[kind].model_validate(event['data']).model_dump(exclude_none=False)
    if kind == 'scene_judged' and data['scene_id'] is None:
        del data['scene_id']
    index = data['scene_index']
    key = f'{kind}:{index}:{data.get("turn", 0)}'
    with _connection(db_path, write=True) as db:
        row = _required(db, simulation_id, user_id)
        previous = _previous(db, simulation_id, key, kind, data)
        if previous:
            return previous
        if row['status'] != 'running' or index > row['total']:
            raise StorageConflictError('실행 상태 또는 장면 범위가 올바르지 않습니다.')
        if not db.execute("SELECT 1 FROM simulation_events WHERE simulation_id=? AND event_key='started'",
                          (simulation_id,)).fetchone():
            raise StorageConflictError('시작 이벤트를 먼저 저장해야 합니다.')
        scene_row = db.execute('SELECT * FROM simulation_scenes WHERE simulation_id=? AND scene_index=?',
                               (simulation_id, index)).fetchone()
        public = _public_data(row, data)
        if kind == 'scene_started':
            if index != row['done'] + 1 or scene_row:
                raise StorageConflictError('장면은 판정 완료 후 순서대로 시작해야 합니다.')
            template = json.loads(row['inputs'])['scenes'][index - 1]
            if data['scene']['scene_id'] != template['scene_id']:
                raise StorageConflictError('입력 스냅샷의 장면 ID와 다릅니다.')
            db.execute('INSERT INTO simulation_scenes VALUES (?,?,?,?,NULL)',
                       (simulation_id, index, _json(public['scene']), '[]'))
        else:
            if scene_row is None or scene_row['judgement'] is not None or index != row['done'] + 1:
                raise StorageConflictError('진행 중인 장면에만 발화·판정을 저장할 수 있습니다.')
            dialogue = json.loads(scene_row['dialogue'])
            if kind == 'utterance':
                if data['turn'] != len(dialogue) + 1:
                    raise StorageConflictError('발화 순서가 올바르지 않습니다.')
                inputs = json.loads(row['engine_inputs'])
                public['name'] = inputs[data['speaker']]['nickname'] + ' AI'
                dialogue.append({k: public[k] for k in ('turn', 'speaker', 'name', 'text')})
                db.execute('UPDATE simulation_scenes SET dialogue=? WHERE simulation_id=? AND scene_index=?',
                           (_json(dialogue), simulation_id, index))
            else:
                if data['progress'] != {'done': index, 'total': row['total']}:
                    raise StorageConflictError('판정 진행률이 저장 장면 순서와 다릅니다.')
                scene_id = json.loads(scene_row['scene'])['scene_id']
                if data.get('scene_id', scene_id) != scene_id:
                    raise StorageConflictError('판정 장면 ID가 다릅니다.')
                judgement = {k: v for k, v in public.items() if k != 'progress'}
                judgement['scene_id'] = scene_id
                db.execute('UPDATE simulation_scenes SET judgement=? WHERE simulation_id=? AND scene_index=?',
                           (_json(judgement), simulation_id, index))
                _progress(db, row)
        saved = _append(db, row, key, kind, data, index)
        if kind == 'utterance':
            saved['data']['name'] = public['name']
            db.execute('UPDATE simulation_events SET data=? WHERE simulation_id=? AND event_id=?',
                       (_json(saved['data']), simulation_id, saved['id']))
        return saved


def complete_simulation(db_path, simulation_id, *, score: int, headline: str,
                        report: dict | None = None, user_id=None):
    """외부에서 계산한 결과를 저장한다. 저장 계층은 점수·리포트를 계산하지 않는다."""
    if type(score) is not int or not 0 <= score <= 100 or not isinstance(headline, str):
        raise ValueError('점수는 0~100 정수, headline은 문자열이어야 합니다.')
    if report is not None and not isinstance(report, dict):
        raise ValueError('리포트는 dict여야 합니다.')
    with _connection(db_path, write=True) as db:
        row = _required(db, simulation_id, user_id)
        data = {'score': score, 'headline': headline, 'verdict_counts': _counts(db, simulation_id)}
        result = _public_data(row, dict(data, report=report))
        previous = _previous(db, simulation_id, 'completed', 'simulation_completed', data)
        if previous:
            if row['result'] != _json(result):
                raise StorageConflictError('동일 완료 요청의 리포트가 다릅니다.')
            return previous
        _transition(row, 'completed')
        if row['done'] != row['total']:
            raise StorageConflictError('전체 장면 판정 전에는 완료할 수 없습니다.')
        db.execute("UPDATE simulations SET status='completed', completed_at=?, result=? WHERE simulation_id=?",
                   (_now(), _json(result), simulation_id))
        return _append(db, row, 'completed', 'simulation_completed', data, row['total'])


def fail_simulation(db_path, simulation_id, error: dict, *, user_id=None):
    """실패 상태·오류 정보·종료 error 이벤트를 함께 저장한다. 자동 재실행하지 않는다."""
    data = Failure.model_validate(error).model_dump()
    with _connection(db_path, write=True) as db:
        row = _required(db, simulation_id, user_id)
        previous = _previous(db, simulation_id, 'failed', 'error', data)
        if previous:
            return previous
        _transition(row, 'failed')
        if data['scene_index'] is not None and data['scene_index'] > row['total']:
            raise ValueError('오류 장면이 전체 장면 범위를 벗어납니다.')
        db.execute("UPDATE simulations SET status='failed', failed_at=?, failure=? WHERE simulation_id=?",
                   (_now(), _json(data), simulation_id))
        latest = db.execute('SELECT COALESCE(MAX(scene_index),0) FROM simulation_scenes WHERE simulation_id=?',
                            (simulation_id,)).fetchone()[0]
        return _append(db, row, 'failed', 'error', data, data['scene_index'] or latest)


def list_events(db_path, simulation_id, *, after_event_id=None, user_id=None):
    """소유 실행의 공개 이벤트를 전역 순서로 조회. 미존재/비소유는 None, 잘못된 커서는 ValueError."""
    with _connection(db_path) as db:
        if _run(db, simulation_id, user_id) is None:
            return None
        sequence = 0
        if after_event_id is not None:
            cursor = db.execute('SELECT sequence FROM simulation_events WHERE simulation_id=? AND event_id=?',
                                (simulation_id, after_event_id)).fetchone()
            if cursor is None:
                raise ValueError('이 실행에 없는 이벤트 ID입니다.')
            sequence = cursor[0]
        return [_event_value(r) for r in db.execute('SELECT * FROM simulation_events '
                'WHERE simulation_id=? AND sequence>? ORDER BY sequence', (simulation_id, sequence))]


def list_scenes(db_path, simulation_id, *, user_id=None):
    with _connection(db_path) as db:
        if _run(db, simulation_id, user_id) is None:
            return None
        result = []
        for row in db.execute('SELECT * FROM simulation_scenes WHERE simulation_id=? ORDER BY scene_index',
                              (simulation_id,)):
            judgement = json.loads(row['judgement']) if row['judgement'] else {}
            judgement.pop('scene_id', None)
            result.append(dict(judgement, scene_index=row['scene_index'], scene=json.loads(row['scene']),
                               dialogue=json.loads(row['dialogue'])))
        return result


def get_completion(db_path, simulation_id, *, user_id=None):
    """완료 결과만 반환. 없는/다른 소유자 실행은 None, 미완료는 StorageConflictError."""
    with _connection(db_path) as db:
        row = _run(db, simulation_id, user_id)
        if row is None:
            return None
        if row['status'] != 'completed':
            raise StorageConflictError('완료되지 않은 실행입니다.')
        return json.loads(row['result'])
