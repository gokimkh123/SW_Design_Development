# 기능: 시뮬레이션 실행·장면·이벤트의 보존형 추가 스키마를 정의한다.
# 시스템 범위: 공통 DB 초기화에서 사용하는 내부 DDL이며 매칭·규칙은 제외한다.
# 결과: 입력 스냅샷, 재사용 유일성, 장면 순서와 이벤트 재전송 키를 보장한다.
SCHEMAS = {
    'simulations': '''CREATE TABLE simulations (
        simulation_id TEXT NOT NULL PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(user_id),
        persona_id TEXT NOT NULL REFERENCES personas(persona_id),
        candidate_id TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('live', 'replay')),
        engine_mode TEXT CHECK (engine_mode IN ('agents', 'single')),
        status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
        alias TEXT NOT NULL,
        inputs TEXT NOT NULL,
        engine_inputs TEXT NOT NULL,
        total INTEGER NOT NULL CHECK (total > 0),
        done INTEGER NOT NULL DEFAULT 0 CHECK (done >= 0 AND done <= total),
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        failed_at TEXT,
        result TEXT,
        failure TEXT,
        CHECK ((mode = 'live' AND engine_mode IS NOT NULL) OR
               (mode = 'replay' AND engine_mode IS NULL)),
        CHECK ((status = 'completed' AND result IS NOT NULL AND completed_at IS NOT NULL AND done = total)
               OR (status != 'completed' AND result IS NULL AND completed_at IS NULL)),
        CHECK ((status = 'failed' AND failure IS NOT NULL AND failed_at IS NOT NULL)
               OR (status != 'failed' AND failure IS NULL AND failed_at IS NULL))
    )''',
    'simulation_scenes': '''CREATE TABLE simulation_scenes (
        simulation_id TEXT NOT NULL REFERENCES simulations(simulation_id),
        scene_index INTEGER NOT NULL CHECK (scene_index > 0),
        scene TEXT NOT NULL,
        dialogue TEXT NOT NULL,
        judgement TEXT,
        PRIMARY KEY (simulation_id, scene_index)
    )''',
    'simulation_events': '''CREATE TABLE simulation_events (
        simulation_id TEXT NOT NULL REFERENCES simulations(simulation_id),
        sequence INTEGER NOT NULL CHECK (sequence > 0),
        event_id TEXT NOT NULL,
        event_key TEXT NOT NULL,
        type TEXT NOT NULL CHECK (type IN ('simulation_started', 'scene_started', 'utterance',
                                          'scene_judged', 'simulation_completed', 'error')),
        data TEXT NOT NULL,
        internal_data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (simulation_id, sequence),
        UNIQUE (simulation_id, event_id),
        UNIQUE (simulation_id, event_key)
    )''',
}
INDEXES = {
    'simulation_reuse': '''CREATE UNIQUE INDEX simulation_reuse
        ON simulations(persona_id, candidate_id, mode)
        WHERE status IN ('queued', 'running', 'completed')''',
    'simulation_owner': 'CREATE INDEX simulation_owner ON simulations(user_id, created_at)',
}
