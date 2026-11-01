# 기능: 동시 실행 한도(사용자별 · 서버 전체)를 실행 기록 전에 확인하는지 검사한다.
# 시스템 범위: 임시 SQLite와 시드 후보만 사용하며 실행기 · 엔진 · 네트워크는 사용하지 않는다.
# 결과: 한도를 넘는 요청은 행을 남기지 않고 거절되며, 같은 후보 재요청(재사용)은 한도와 무관하게 통과한다.
from copy import deepcopy
import json
from pathlib import Path

import pytest

from app import simulations as store
from app.database import connect_database
from app.personas import PersonaData, create_persona
from app.users import create_user
from test_simulations import context  # noqa: F401 (pytest fixture)

SEEDS = json.loads((Path(__file__).resolve().parents[2] / 'data/seed/personas.json').read_text(encoding='utf-8'))['personas']
POOL = [s for s in SEEDS if s['candidate_pool']]


def running_count(path):
    with connect_database(path) as db:
        return db.execute("SELECT COUNT(*) FROM simulations WHERE status='running'").fetchone()[0]


def test_per_user_limit_blocks_before_insert(context):
    path, args, *_ = context
    for seed in POOL[:3]:
        _, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(seed)), max_running_per_user=3)
        assert created
    with pytest.raises(store.SimulationLimitError) as info:
        store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[3])), max_running_per_user=3)
    assert info.value.scope == 'user'
    assert running_count(path) == 3
    # 이미 진행 중인 같은 후보는 재사용이므로 한도와 무관하게 그대로 반환
    sim, created = store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])), max_running_per_user=3)
    assert not created and sim['status'] == 'running'


def test_total_limit_counts_all_users(context):
    path, args, *_ = context
    store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])), max_running_total=2)
    other = create_user(path, '다른 사람')
    data = {k: SEEDS[0][k] for k in PersonaData.model_fields}
    data['is_seed'] = False
    persona = create_persona(path, other['user_id'], data)
    other_args = dict(args, user_id=other['user_id'], persona_id=persona['persona_id'])
    store.create_or_reuse_simulation(path, **dict(other_args, candidate=deepcopy(POOL[1])), max_running_total=2)
    with pytest.raises(store.SimulationLimitError) as info:
        store.create_or_reuse_simulation(path, **dict(other_args, candidate=deepcopy(POOL[2])), max_running_total=2)
    assert info.value.scope == 'total'
    assert running_count(path) == 2


def test_wal_mode_enabled(context):
    path, args, *_ = context
    store.create_or_reuse_simulation(path, **dict(args, candidate=deepcopy(POOL[0])))
    with connect_database(path) as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
