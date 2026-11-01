# 기능: 매칭과 생활 규칙의 추가 스키마를 정의한다.
# 시스템 범위: 공통 DB 초기화에서 사용하는 내부 DDL이며 P1 수정 제안은 제외한다.
# 결과: 시뮬레이션당 매칭 1건, 매칭·영역당 규칙 1개, 양측 동의와 확정 상태의 일치를 보장한다.
SCHEMAS = {
    'matches': '''CREATE TABLE matches (
        match_id TEXT NOT NULL PRIMARY KEY,
        simulation_id TEXT NOT NULL UNIQUE REFERENCES simulations(simulation_id),
        user_id TEXT NOT NULL REFERENCES users(user_id),
        status TEXT NOT NULL CHECK (status IN ('pending', 'accepted', 'declined')),
        partner TEXT NOT NULL,
        room TEXT,
        rules_status TEXT NOT NULL CHECK (rules_status IN ('draft', 'confirmed')),
        agreed_me INTEGER NOT NULL DEFAULT 0 CHECK (agreed_me IN (0, 1)),
        agreed_partner INTEGER NOT NULL DEFAULT 0 CHECK (agreed_partner IN (0, 1)),
        created_at TEXT NOT NULL,
        CHECK ((rules_status = 'confirmed') = (agreed_me = 1 AND agreed_partner = 1))
    )''',
    'rules': '''CREATE TABLE rules (
        rule_id TEXT NOT NULL PRIMARY KEY,
        match_id TEXT NOT NULL REFERENCES matches(match_id),
        position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 6),
        area TEXT NOT NULL CHECK (area IN ('quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies')),
        area_label TEXT NOT NULL,
        text TEXT NOT NULL,
        source_scene_index INTEGER NOT NULL CHECK (source_scene_index BETWEEN 1 AND 20),
        source_day INTEGER NOT NULL CHECK (source_day BETWEEN 1 AND 7),
        source_verdict TEXT NOT NULL CHECK (source_verdict IN ('harmonious', 'negotiated', 'conflict', 'pending')),
        UNIQUE (match_id, area),
        UNIQUE (match_id, position)
    )''',
}
