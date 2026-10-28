# 룸메궁합 API 명세서

| 항목 | 내용 |
| --- | --- |
| 버전 | v1.0 초안 (2026-10-19) |
| 확정 | 10/26까지 리뷰 → 10/27 개발 착수 시 확정 |
| 담당 | 백엔드 일준 · 범찬, 프론트엔드 동현, 엔진 인터페이스 건한 |
| 변경 규칙 | 이 문서를 먼저 고치는 PR → 동현 + 백엔드 1명 승인 → 구현 |
| 구현 후 기준 | FastAPI 자동 생성 문서(`http://localhost:8000/docs`). 불일치 시 본 문서 수정 |
| 함께 보는 문서 | [PRD](PRD.md) · [일정](SCHEDULE.md) · [협업 가이드](CONTRIBUTING.md) |

## 목차

1. [공통 규칙](#1-공통-규칙)
2. [전체 구성](#2-전체-구성)
3. [데이터 모델](#3-데이터-모델)
4. [엔드포인트 상세](#4-엔드포인트-상세)
5. [실시간 이벤트 (SSE)](#5-실시간-이벤트-sse)
6. [오류 코드](#6-오류-코드)
7. [엔진 인터페이스](#7-엔진-인터페이스)
8. [로컬 개발 연결](#8-로컬-개발-연결)

---

## 1. 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| Base URL | 백엔드 `http://localhost:8000/api`. 프론트엔드는 `/api`로 호출, Vite 프록시를 통해 백엔드로 전달 |
| 형식 | JSON (UTF-8). 필드 이름은 `snake_case` |
| ID | 문자열. 접두사 + 8자리: `usr_` 사용자, `per_` 페르소나, `sim_` 시뮬레이션, `mat_` 매칭, `rul_` 규칙, `prp_` 수정 제안. 시드 데이터는 읽기 쉬운 ID (`per_haneul`, `per_daeun`) |
| 시각 | 날짜·시각은 ISO 8601 KST (`2026-11-03T10:15:00+09:00`), 하루 중 시각은 `"HH:MM"` |
| 사용자 식별 | 로그인 없음. `POST /api/users` 응답의 `user_id`를 이후 요청 헤더 `X-User-Id`에 포함 (최종 버전에서 학교 메일 인증으로 교체) |
| 오류 | `{ "error": { "code": "...", "message": "..." } }` 형식 ([6장](#6-오류-코드)) |

**공통 값**

| 이름 | 값 |
| --- | --- |
| 판정 `verdict` | `harmonious` 원만 · `negotiated` 조율 · `conflict` 충돌 · `pending` 판정 보류 |
| 대화 방식 `conflict_style` | `direct` 직설 · `avoid` 회피 · `delay` 지연 |
| 규칙 영역 `area` | `quiet_hours` 조용한 시간 · `guests` 친구 초대 · `cleaning` 청소 · `fridge` 냉장고 · `climate` 냉난방 · `supplies` 공용품 |
| 시뮬레이션 모드 `mode` | 요청 · 응답 값: `live` 실제 실행(기본) · `replay` 사전 생성 결과 재생. `live`의 실행 방식(`agents` · `single`)은 서버 환경변수 `SIM_MODE`로 결정 |
| 시뮬레이션 상태 `status` | `queued` · `running` · `completed` · `failed` |

---

## 2. 전체 구성

```mermaid
sequenceDiagram
    participant FE as 프론트엔드
    participant API as 백엔드
    participant ENG as 엔진

    FE->>API: POST /users (닉네임)
    FE->>API: GET /survey
    FE->>API: POST /personas (12문항 응답)
    API->>ENG: build_persona()
    API-->>FE: 페르소나 카드
    FE->>API: GET /personas/ID/candidates
    loop 후보 3명
        FE->>API: POST /simulations
        FE->>API: GET /simulations/ID/events (SSE)
        API->>ENG: simulate()
        API-->>FE: scene_started · utterance · scene_judged
    end
    FE->>API: GET /simulations/ID/report
    FE->>API: POST /matches
    API->>ENG: draft_rules()
    FE->>API: GET /matches/ID/rules
    FE->>API: POST /matches/ID/rules/agree
```

| # | 메서드 | 경로 | 설명 | 우선순위 | 구현 (제안) | 화면 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | GET | `/api/health` | 서버 · LLM 상태 | P0 | 일준 | - |
| 2 | POST | `/api/users` | 닉네임으로 사용자 생성 | P0 | 일준 | A1 |
| 3 | GET | `/api/survey` | 설문 12문항 | P0 | 일준 | A2 · A3 |
| 4 | POST | `/api/personas` | 응답 → 페르소나 생성 | P0 | 일준 | A4 |
| 5 | GET | `/api/personas/{persona_id}` | 페르소나 조회 | P0 | 일준 | A4 |
| 6 | PATCH | `/api/personas/{persona_id}` | 꼭 지켜줘 · 괜찮아요 수정 | P0 | 일준 | A4 |
| 7 | GET | `/api/personas/{persona_id}/candidates` | 후보 3명 | P0 | 일준 | B1 |
| 8 | POST | `/api/simulations` | 시뮬레이션 시작 | P0 | 일준 | B1 · B2 |
| 9 | GET | `/api/simulations/{simulation_id}` | 상태 · 진행률 | P0 | 일준 | B1 · B2 |
| 10 | GET | `/api/simulations/{simulation_id}/events` | 실시간 이벤트 (SSE) | P0 | 일준 | B2 |
| 11 | GET | `/api/simulations/{simulation_id}/report` | 리포트 | P0 | 범찬 | B3 |
| 12 | POST | `/api/matches` | 룸메 신청 (시드 후보는 자동 수락) | P0 | 범찬 | C1 |
| 13 | GET | `/api/matches/{match_id}` | 매칭 정보 | P0 | 범찬 | C1 |
| 14 | GET | `/api/matches/{match_id}/rules` | 생활 규칙 초안 | P0 | 범찬 | C2 |
| 15 | POST | `/api/matches/{match_id}/rules/agree` | 규칙 동의 | P0 | 범찬 | C2 |
| 16 | GET | `/api/simulations/{simulation_id}/scenes` | 장면별 대화 전문 (다시 보기) | P1 | 일준 | B3 |
| 17 | GET | `/api/personas/{persona_id}/comparison` | 후보 비교 (레이더 차트) | P1 | 범찬 | B4 |
| 18 | POST | `/api/rules/{rule_id}/proposals` | 규칙 수정 제안 → AI 중재안 | P1 | 범찬 | C3 |
| 19 | POST | `/api/proposals/{proposal_id}/accept` | 중재안 수락 | P1 | 범찬 | C3 |
| 20 | POST | `/api/mediation/rephrase` | 불편 메모 → 요청형 문장 | P1 | 일준 | D2 |
| 21 | POST | `/api/matches/{match_id}/accept` | 상대 수락 (실사용자끼리 매칭) | P2 | - | - |

---

## 3. 데이터 모델

### Persona

```json
{
  "persona_id": "per_haneul",
  "user_id": "usr_haneul",
  "nickname": "하늘",
  "type_name": "규칙적인 아침형",
  "summary": "23시 취침 · 6시 반 기상. 불편하면 바로, 부드럽게 말하는 편.",
  "sleep": { "bedtime": "23:00", "wake": "06:30", "exam_pattern": "earlier" },
  "axes": {
    "sleep_rhythm": 33,
    "noise_sensitivity": 67,
    "cleanliness": 84,
    "sociability": 33,
    "sharing_tolerance": 0
  },
  "axis_labels": {
    "sleep_rhythm": "아침형",
    "noise_sensitivity": "예민",
    "cleanliness": "높음",
    "sociability": "보통",
    "sharing_tolerance": "낮음"
  },
  "conflict_style": "direct",
  "preferences": { "temperature": "moderate" },
  "must_keep": ["24시 이후 통화·게임 소리 X"],
  "okay_with": ["친구 초대 (미리 말하면)"],
  "is_seed": true,
  "created_at": "2026-11-03T10:12:00+09:00"
}
```

| 필드 | 설명 |
| --- | --- |
| `axes` | 5개 축 0~100, 계산 규칙: [PRD 부록 C](PRD.md#부록-c-계산-규칙-초안). `sleep_rhythm`: 0 = 아침형, 100 = 올빼미 |
| `axis_labels` | 화면 표시용 이름표 (서버 계산) |
| `sleep.exam_pattern` | q03 응답: `same` · `earlier` · `later` · `all_nighter` |
| `preferences.temperature` | q06 응답: `warm` · `moderate` · `cool` · `any` |
| `must_keep` · `okay_with` | 각 최대 3개, 항목당 30자 이내. 생성 시 LLM 후보 제안 후 사용자 수정 |

### Candidate

```json
{
  "candidate_id": "per_daeun",
  "alias": "후보 A",
  "department": "간호학과",
  "year": 1,
  "type_name": "깔끔한 집순이",
  "pre_score": 91,
  "highlight": "청결 기준 비슷",
  "simulation": {
    "simulation_id": "sim_7k2m9q1a",
    "status": "completed",
    "progress": { "done": 20, "total": 20 },
    "score": 88
  }
}
```

- 매칭 전 이름 미제공, `alias`는 1차 점수 순 후보 A · B · C
- `simulation`: 미시작 시 `null`

### Simulation

```json
{
  "simulation_id": "sim_7k2m9q1a",
  "persona_id": "per_haneul",
  "candidate_id": "per_daeun",
  "mode": "live",
  "status": "running",
  "progress": { "done": 9, "total": 20 },
  "verdict_counts": { "harmonious": 7, "negotiated": 2, "conflict": 0, "pending": 0 },
  "score": null,
  "started_at": "2026-11-03T10:14:05+09:00",
  "completed_at": null
}
```

- `mode`의 `live`: 서버 설정(`SIM_MODE`)에 따른 `agents` 또는 `single` 실행

### SceneResult

```json
{
  "scene_index": 9,
  "scene": {
    "scene_id": "S09",
    "day": 3,
    "weekday": "수",
    "time": "01:10",
    "category": "수면·소음",
    "title": "심야 게임",
    "situation": "후보 C가 친구와 음성 채팅으로 게임 중, 하늘은 내일 9시 수업"
  },
  "dialogue": [
    { "turn": 1, "speaker": "me", "name": "하늘 AI", "text": "내일 아침 수업이라 이제 자야 할 것 같아. 혹시 헤드셋 쓰고 조금만 작게 해줄 수 있어?" },
    { "turn": 2, "speaker": "candidate", "name": "후보 C AI", "text": "아 미안! 게임은 보통 이 시간이 제일 재밌는데… 헤드셋은 쓸 수 있어. 대신 주말 밤엔 좀 봐줘?" },
    { "turn": 3, "speaker": "me", "name": "하늘 AI", "text": "좋아. 평일 24시 이후엔 헤드셋, 금·토는 1시까지 괜찮아." }
  ],
  "verdict": "negotiated",
  "reason": "소음 기준 차이가 있었으나 헤드셋 사용으로 합의",
  "agreement": "평일 24시 이후 헤드셋, 금·토는 1시까지",
  "rule_candidate": { "area": "quiet_hours", "text": "평일 24시 이후 헤드셋 사용" },
  "unresolved": null
}
```

- `speaker`: `me`(내 AI) 또는 `candidate`(후보 AI). 매칭 전 후보 이름은 `후보 C AI` 등 별칭 표시
- 발화 최대 4개, 조기 합의 시 단축 가능

### Report

```json
{
  "simulation_id": "sim_7k2m9q1a",
  "candidate": { "candidate_id": "per_daeun", "alias": "후보 A", "type_name": "깔끔한 집순이" },
  "score": 88,
  "headline": "함께 살기 무난한 조합이에요",
  "verdict_counts": { "harmonious": 16, "negotiated": 3, "conflict": 1, "pending": 0 },
  "scene_verdicts": [
    "harmonious", "harmonious", "harmonious", "harmonious", "harmonious",
    "negotiated", "negotiated", "harmonious", "harmonious", "harmonious",
    "harmonious", "harmonious", "harmonious", "conflict", "harmonious",
    "negotiated", "harmonious", "harmonious", "harmonious", "harmonious"
  ],
  "highlights": [
    { "scene_index": 14, "day": 5, "title": "냉장고 반찬", "verdict": "conflict", "agreement": "칸 나누기 + 공용 칸은 주 1회 정리" },
    { "scene_index": 6, "day": 2, "title": "난방 온도", "verdict": "negotiated", "agreement": "밤 23도로 합의" },
    { "scene_index": 7, "day": 3, "title": "친구 초대", "verdict": "negotiated", "agreement": "하루 전 공지, 주 1회, 22시까지" },
    { "scene_index": 16, "day": 6, "title": "주말 늦잠", "verdict": "negotiated", "agreement": "청소는 일요일 오후 2시" }
  ],
  "expected_conflicts_per_month": null
}
```

- `scene_verdicts`: 장면 순서 20개, 진행 막대 색상 표시용
- `highlights`: 충돌 → 조율 순, 동일 판정은 장면 순
- `expected_conflicts_per_month`: P1, 산식 확정 전까지 `null`

### Match

```json
{
  "match_id": "mat_3p8x2c4d",
  "simulation_id": "sim_7k2m9q1a",
  "status": "accepted",
  "partner": {
    "persona_id": "per_daeun",
    "name": "다은",
    "department": "간호학과",
    "year": 1,
    "type_name": "깔끔한 집순이",
    "greeting": "아침형이시라니 반가워요! 저도 실습 때문에 일찍 자요 🙂"
  },
  "room": "302호 (배정 예정)",
  "rules_status": "draft"
}
```

- `status`: `pending` · `accepted` · `declined`. 시드 후보는 신청 즉시 `accepted`, 이 시점부터 `partner.name` 공개

### RuleSet

```json
{
  "match_id": "mat_3p8x2c4d",
  "status": "draft",
  "rules": [
    { "rule_id": "rul_q1w2e3r4", "area": "quiet_hours", "area_label": "조용한 시간", "text": "23:30 ~ 07:00", "source": { "scene_index": 4, "day": 2, "verdict": "harmonious" } },
    { "rule_id": "rul_t5y6u7i8", "area": "guests", "area_label": "친구 초대", "text": "하루 전 공지 · 주 1회 · 22시까지", "source": { "scene_index": 7, "day": 3, "verdict": "negotiated" } },
    { "rule_id": "rul_o9p0a1s2", "area": "cleaning", "area_label": "청소", "text": "일요일 14시 · 격주 화장실 당번", "source": { "scene_index": 16, "day": 6, "verdict": "negotiated" } },
    { "rule_id": "rul_d3f4g5h6", "area": "fridge", "area_label": "냉장고", "text": "칸 나누기 · 공용 칸 주 1회 정리", "source": { "scene_index": 14, "day": 5, "verdict": "conflict" } },
    { "rule_id": "rul_j7k8l9z0", "area": "climate", "area_label": "냉난방", "text": "밤 23도 · 외출 시 끄기", "source": { "scene_index": 6, "day": 2, "verdict": "negotiated" } },
    { "rule_id": "rul_x1c2v3b4", "area": "supplies", "area_label": "공용품", "text": "휴지·세제 번갈아 구매 · 앱 정산", "source": { "scene_index": 11, "day": 4, "verdict": "harmonious" } }
  ],
  "agreements": { "me": false, "partner": false }
}
```

- 영역별 규칙 1개(총 6개), 화면 출처 표시는 `source` 기반 (예: `5일차 충돌`, `2일차 장면`)
- `status`: `draft` → 양측 동의 시 `confirmed`

---

## 4. 엔드포인트 상세

- `X-User-Id` 헤더: `POST /api/users`, `GET /api/health`, `GET /api/survey`를 제외한 전 요청에 포함

### 4.1 GET /api/health

- 서버 · LLM 설정 확인
- 프론트엔드 초기 세팅 시 연결 확인용

```jsonc
// 200
{ "status": "ok", "llm": { "provider": "anthropic", "model": "claude-haiku-5-5" }, "sim_mode": "agents" }
```

### 4.2 POST /api/users

```jsonc
// 요청
{ "nickname": "하늘" }

// 201
{ "user_id": "usr_k3j9x2ab", "nickname": "하늘", "created_at": "2026-11-03T10:11:30+09:00" }
```

- `nickname`: 1~10자, 중복 허용
- 오류: `422 VALIDATION_ERROR`

### 4.3 GET /api/survey

- 설문 12문항 제공
- 문항 내용은 `data/seed/survey.json`(PM 관리) 기반, 프론트엔드 문구 하드코딩 금지

```jsonc
// 200
{
  "version": "2026-10-26",
  "questions": [
    {
      "question_id": "q01",
      "section": "life",
      "type": "time_range",
      "title": "평일에는 보통 몇 시에 자고 일어나요?",
      "fields": [
        { "key": "bedtime", "label": "취침", "min": "21:00", "max": "03:00", "step_minutes": 30, "default": "23:00" },
        { "key": "wake", "label": "기상", "min": "05:00", "max": "11:00", "step_minutes": 30, "default": "07:00" }
      ]
    },
    {
      "question_id": "q02",
      "section": "life",
      "type": "choice",
      "title": "잠잘 때 소리에 얼마나 예민해요?",
      "options": [
        { "value": "insensitive", "label": "둔감" },
        { "value": "normal", "label": "보통" },
        { "value": "sensitive", "label": "예민" },
        { "value": "very_sensitive", "label": "아주 예민" }
      ]
    },
    {
      "question_id": "q09",
      "section": "situation",
      "type": "choice",
      "title": "룸메이트가 새벽 1시에 친구와 통화하고 있어요",
      "hint": "정답은 없어요. 내 AI가 시뮬레이션에서 나처럼 대화하도록 쓰여요.",
      "options": [
        { "value": "say_now", "label": "\"조금만 작게 해줄래?\" 바로 말한다", "style": "direct" },
        { "value": "earplugs", "label": "이어폰을 끼고 그냥 잔다", "style": "avoid" },
        { "value": "talk_tomorrow", "label": "참았다가 다음 날 이야기한다", "style": "delay" },
        { "value": "step_out", "label": "잠깐 밖에 나가 있는다", "style": "avoid" }
      ]
    }
  ]
}
```

- `section`: `life` 생활 설문(q01~q08) · `situation` 상황 질문(q09~q12)
- `type`: `time_range` 슬라이더 · `choice` 4지선다
- 위 예시는 3문항 발췌, 전체 문항은 [PRD 부록 A](PRD.md#부록-a-설문-12문항-초안) 참고

### 4.4 POST /api/personas

```jsonc
// 요청 (X-User-Id 헤더 필요)
{
  "answers": {
    "q01": { "bedtime": "23:00", "wake": "06:30" },
    "q02": "sensitive",
    "q03": "earlier",
    "q04": "every_2_3_days",
    "q05": "right_away",
    "q06": "moderate",
    "q07": "when_needed",
    "q08": "all_separate",
    "q09": "say_now",
    "q10": "ask_now",
    "q11": "say_now",
    "q12": "after_friend_leaves"
  }
}

// 201 → Persona
```

- 각 값은 `GET /api/survey`의 `options[].value`(시간 범위 문항은 `fields[].key`별 시각) 그대로 전송
- 응답 시간 최대 10초 (LLM의 유형명 · 요약 · 꼭 지켜줘/괜찮아요 후보 생성). LLM 실패 시 서버의 규칙 기반 문구 대체, **실패 응답 미반환**
- 오류: `400 SURVEY_INCOMPLETE` (빠진 문항 ID를 `message`에 표시), `401 USER_REQUIRED`, `422 VALIDATION_ERROR`

### 4.5 GET /api/personas/{persona_id}

`200` → Persona · 오류: `404 PERSONA_NOT_FOUND`

### 4.6 PATCH /api/personas/{persona_id}

```jsonc
// 요청 (전송 필드만 변경)
{ "must_keep": ["24시 이후 통화·게임 소리 X"], "okay_with": ["친구 초대 (미리 말하면)", "공용품 같이 쓰기"] }

// 200 → Persona
```

- 완료된 시뮬레이션은 재실행하지 않음, 이후 시작 시뮬레이션부터 반영
- 오류: `404 PERSONA_NOT_FOUND`, `422 VALIDATION_ERROR` (3개 초과, 30자 초과)

### 4.7 GET /api/personas/{persona_id}/candidates

- 시드 후보 풀(10명, 본인 제외) 중 1차 점수 상위 3명 반환

```jsonc
// 200
{ "candidates": [ /* Candidate × 3, pre_score 내림차순 */ ] }
```

오류: `404 PERSONA_NOT_FOUND`

### 4.8 POST /api/simulations

```jsonc
// 요청
{ "persona_id": "per_haneul", "candidate_id": "per_daeun", "mode": "live" }

// 202 → Simulation (status: queued 또는 running)
```

- `mode`: `live`(기본) 또는 `replay`. `replay` 요청 시 사전 생성 파일이 없으면 `live`로 실행, 응답 `mode`에 실제 실행 모드 표기
- 동일 페르소나 · 후보 · 모드의 `running` 또는 `completed` 시뮬레이션 존재 시 신규 생성 없이 `200`으로 기존 건 반환
- 오류: `404 PERSONA_NOT_FOUND`

### 4.9 GET /api/simulations/{simulation_id}

`200` → Simulation. SSE 연결 불가 시 2초 간격 폴링용으로도 사용. 오류: `404 SIMULATION_NOT_FOUND`

### 4.10 GET /api/simulations/{simulation_id}/events

SSE 스트림. [5장](#5-실시간-이벤트-sse) 참고.

### 4.11 GET /api/simulations/{simulation_id}/report

`200` → Report · 오류: `404 SIMULATION_NOT_FOUND`, `409 SIMULATION_NOT_COMPLETED`

### 4.12 POST /api/matches

```jsonc
// 요청
{ "simulation_id": "sim_7k2m9q1a" }

// 201 → Match
```

- 시드 후보는 즉시 수락(`accepted`), 동일 요청 내 엔진의 생활 규칙 초안 생성 (최대 10초)
- 오류: `404 SIMULATION_NOT_FOUND`, `409 SIMULATION_NOT_COMPLETED`

### 4.13 GET /api/matches/{match_id}

`200` → Match · 오류: `404 MATCH_NOT_FOUND`

### 4.14 GET /api/matches/{match_id}/rules

`200` → RuleSet · 오류: `404 MATCH_NOT_FOUND`

### 4.15 POST /api/matches/{match_id}/rules/agree

- 요청 본문 없음
- 본인 동의 기록, 시드 후보는 자동 동의

```jsonc
// 200 → RuleSet
{ "match_id": "mat_3p8x2c4d", "status": "confirmed", "rules": [ /* ... */ ], "agreements": { "me": true, "partner": true } }
```

### 4.16 P1 엔드포인트

**GET /api/simulations/{simulation_id}/scenes** — `200` `{ "scenes": [SceneResult × 20] }`

**GET /api/personas/{persona_id}/comparison**

```jsonc
// 200
{
  "me": { "axes": { "sleep_rhythm": 33, "noise_sensitivity": 67, "cleanliness": 84, "sociability": 33, "sharing_tolerance": 0 } },
  "candidates": [
    {
      "candidate_id": "per_daeun",
      "alias": "후보 A",
      "axes": { "sleep_rhythm": 25, "noise_sensitivity": 67, "cleanliness": 100, "sociability": 33, "sharing_tolerance": 33 },
      "score": 88,
      "expected_conflicts_per_month": 0.5
    }
  ],
  "recommended_candidate_id": "per_daeun"
}
```

**POST /api/rules/{rule_id}/proposals**

```jsonc
// 요청
{ "text": "시험 기간엔 22:30부터", "reason": "실습 평가 주간엔 일찍 자야 해서요" }

// 201
{
  "proposal_id": "prp_9d8s7a6f",
  "rule_id": "rul_q1w2e3r4",
  "mediation": {
    "text": "시험 기간 22:30부터 조용한 시간, 대신 아침 드라이기는 욕실에서 사용",
    "rationale": ["아침형이라 22:30 취침과 충돌 적음", "실습 기간 수면 확보"]
  }
}
```

**POST /api/proposals/{proposal_id}/accept** — `200` → 바뀐 Rule

**POST /api/mediation/rephrase**

```jsonc
// 요청
{ "match_id": "mat_3p8x2c4d", "memo": "요즘 다은이 새벽에 알람을 여러 번 끄고 다시 자서 나도 깨… 짜증나" }

// 200
{
  "message": "요즘 아침 알람 소리에 나도 같이 깨더라 😅 진동으로 바꾸거나 한 번만 울리게 해줄 수 있을까?",
  "suggested_rule": { "area": "quiet_hours", "text": "평일 알람은 진동 · 다시 알림 1회까지" }
}
```

- 메모 원문 미저장 · 상대 미전달

---

## 5. 실시간 이벤트 (SSE)

`GET /api/simulations/{simulation_id}/events` (`Content-Type: text/event-stream`)

### 5.1 이벤트 종류

| `event` | 발생 시점 | `data` |
| --- | --- | --- |
| `simulation_started` | 연결 직후 1회 | `{ simulation_id, mode, total_scenes, me: { name, type_name }, candidate: { alias, type_name } }` |
| `scene_started` | 장면 시작 | `{ scene_index, scene: { scene_id, day, weekday, time, category, title, situation } }` |
| `utterance` | 발화 1개 | `{ scene_index, turn, speaker, name, text }` |
| `scene_judged` | 장면 판정 | `{ scene_index, verdict, reason, agreement, rule_candidate, unresolved, progress: { done, total } }` |
| `simulation_completed` | 20장면 종료 | `{ score, headline, verdict_counts }` |
| `error` | 오류 | `{ code, message, scene_index, retryable }` (`scene_index`: 장면 무관 오류면 `null`) |

### 5.2 예시

```text
id: 9-0
event: scene_started
data: {"scene_index":9,"scene":{"scene_id":"S09","day":3,"weekday":"수","time":"01:10","category":"수면·소음","title":"심야 게임","situation":"후보 C가 친구와 음성 채팅으로 게임 중, 하늘은 내일 9시 수업"}}

id: 9-1
event: utterance
data: {"scene_index":9,"turn":1,"speaker":"me","name":"하늘 AI","text":"내일 아침 수업이라 이제 자야 할 것 같아. 혹시 헤드셋 쓰고 조금만 작게 해줄 수 있어?"}

id: 9-4
event: scene_judged
data: {"scene_index":9,"verdict":"negotiated","reason":"소음 기준 차이가 있었으나 헤드셋 사용으로 합의","agreement":"평일 24시 이후 헤드셋, 금·토는 1시까지","rule_candidate":{"area":"quiet_hours","text":"평일 24시 이후 헤드셋 사용"},"unresolved":null,"progress":{"done":9,"total":20}}
```

### 5.3 규칙

- 이벤트 `id`: `{scene_index}-{순번}`, 시작 이벤트는 `0-0`
- 서버의 전 이벤트 DB 저장. 재연결 시 클라이언트가 보내는 `Last-Event-ID` 헤더 이후부터 재전송, 헤더 부재 시 처음부터 전송. 완료된 시뮬레이션 연결 시에도 전체 이벤트 수신 후 `simulation_completed`로 종료
- 15초 간격 `: ping` 주석 전송으로 연결 유지
- `replay` 모드: 동일 이벤트를 `REPLAY_DELAY_MS` 간격으로 전송
- 장면 판정 실패 시 `scene_judged`의 `verdict`는 `pending`, 다음 장면으로 진행
- `error` 이벤트 후 서버는 스트림 종료. 클라이언트는 `retryable=true`일 때만 재연결, `false`면 즉시 중단

### 5.4 프론트엔드 사용 예

- 브라우저 기본 `EventSource`는 `X-User-Id` 헤더 전송 불가 → `fetch` 스트림으로 구독 (`frontend/src/api/real.ts`의 `subscribeSimulation` 참고)

```ts
const res = await fetch(`/api/simulations/${simulationId}/events`, {
  headers: { Accept: "text/event-stream", "X-User-Id": userId, ...(lastId ? { "Last-Event-ID": lastId } : {}) },
});
const reader = res.body!.getReader();
// 빈 줄("\n\n") 단위로 이벤트 블록을 나눈 뒤 id · event · data 필드를 파싱하여 처리
```

- 재연결 시 동일 `id` 이벤트 중복 수신 가능 → 화면 반영 전 `id` 기준 중복 제거

---

## 6. 오류 코드

```json
{ "error": { "code": "PERSONA_NOT_FOUND", "message": "페르소나를 찾을 수 없어요." } }
```

| HTTP | `code` | 의미 |
| --- | --- | --- |
| 400 | `SURVEY_INCOMPLETE` | 12문항 중 응답 누락 |
| 401 | `USER_REQUIRED` | `X-User-Id` 누락 또는 미등록 사용자 |
| 404 | `USER_NOT_FOUND` · `PERSONA_NOT_FOUND` · `SIMULATION_NOT_FOUND` · `MATCH_NOT_FOUND` · `RULE_NOT_FOUND` · `PROPOSAL_NOT_FOUND` | 대상 없음 |
| 409 | `SIMULATION_NOT_COMPLETED` | 시뮬레이션 완료 전 리포트 · 매칭 요청 |
| 422 | `VALIDATION_ERROR` | 형식 오류 (FastAPI 기본 422 응답을 본 형식으로 변환) |
| 429 | `LLM_RATE_LIMITED` | LLM 분당 한도 초과, 잠시 후 재시도 |
| 503 | `LLM_UNAVAILABLE` | LLM 호출 실패, 부스에서는 리플레이 모드 전환 |
| 500 | `INTERNAL_ERROR` | 기타 서버 오류 |

---

## 7. 엔진 인터페이스

- 백엔드(일준 · 범찬)와 엔진(건한) 간 인터페이스 약속
- 백엔드는 `engine` 패키지의 아래 함수만 호출

```python
# engine/__init__.py
from typing import AsyncIterator
from engine.models import Persona, SceneTemplate, SimEvent, SceneJudgement, RuleDraft, Mediation, Rephrased

async def build_persona(nickname: str, answers: dict) -> Persona:
    """12문항 응답 → 페르소나 (5개 축 계산 + 유형명 · 요약 · 꼭 지켜줘/괜찮아요 후보 생성)"""

def load_scenes() -> list[SceneTemplate]:
    """data/seed/scenes.json의 장면 20개"""

async def simulate(me: Persona, candidate: Persona, *, mode: str = "agents") -> AsyncIterator[SimEvent]:
    """장면 20개 순차 실행 및 이벤트 단위 반환 (mode: agents | single)"""

def score(judgements: list[SceneJudgement]) -> int:
    """궁합 점수 (PRD 8.5)"""

def headline(score: int) -> str:
    """한 줄 판정 (PRD 8.5)"""

async def draft_rules(me: Persona, candidate: Persona, judgements: list[SceneJudgement]) -> list[RuleDraft]:
    """6개 영역 생활 규칙 초안"""

# P1
async def mediate(rule: RuleDraft, proposal_text: str, reason: str, proposer: Persona, other: Persona) -> Mediation: ...
async def rephrase(memo: str, sender: Persona, receiver: Persona) -> Rephrased: ...
```

| 약속 | 내용 |
| --- | --- |
| 모델 | `engine/models.py`의 Pydantic 모델. 필드 이름은 본 문서 3장과 동일 (ID 필드는 백엔드 부여) |
| 이벤트 | `SimEvent` 형식은 `{ "type": "utterance", "data": {...} }`로 5장 SSE 이벤트와 동일. 백엔드는 수신 이벤트 저장 후 SSE로 그대로 전달 |
| 판정 모델 `SceneJudgement` | `scene_index` · `scene_id` · `verdict` · `reason` · `agreement` · `rule_candidate` · `unresolved`. `scene_judged` 이벤트 `data`에서 `progress`를 뺀 형태 |
| 실행 모드 | `simulate(mode=...)`는 `agents` · `single`만 허용. 요청의 `live`는 엔진 어댑터가 `SIM_MODE` 값으로 변환, `replay`는 엔진 호출 없이 백엔드가 처리 |
| 후보 익명 | 매칭 전 시뮬레이션에서는 백엔드가 후보 페르소나의 `nickname`을 `alias`(예: `후보 A`)로 바꿔 엔진에 전달 |
| 이벤트 범위 (10/28 확정) | 엔진 `simulate()`는 장면 이벤트(`scene_started` · `utterance` · `scene_judged` · `error`)만 반환. `simulation_started` · `simulation_completed`는 백엔드 시뮬레이션 실행기가 생성 |
| 의존성 | 엔진의 FastAPI · DB 비의존. 순수 Python + Anthropic SDK |
| 가짜 엔진 | `engine/fake.py`: 동일 함수명으로 `data/replays/` 결과 반환. 엔진 완성 전 백엔드 개발 및 `replay` 모드 공용 |
| 단독 실행 | `python -m engine.cli simulate --me per_haneul --candidate per_daeun`로 터미널 내 결과 확인 지원 |

---

## 8. 로컬 개발 연결

### 8.1 포트와 프록시

| 서비스 | 주소 |
| --- | --- |
| 프론트엔드 (Vite) | `http://localhost:5173` |
| 백엔드 (FastAPI) | `http://localhost:8000` (API 문서 `/docs`) |

```ts
// frontend/vite.config.ts
export default defineConfig({
  server: { proxy: { "/api": "http://localhost:8000" } },
});
```

- 프록시 사용 시 브라우저 기준 동일 출처로 CORS 설정 불필요

### 8.2 mock 기반 선행 개발

- 프론트엔드: 본 문서 JSON 예시 기반 mock 응답으로 화면 선행 개발 (`VITE_USE_MOCK=true`)
- 백엔드: 엔진 완성 전까지 가짜 엔진 사용. `engine/fake.py` 도착 전에는 백엔드 임시 가짜 엔진(`backend/app/fake_engine.py`, LLM 미호출) 사용
- 백엔드의 엔진 호출은 엔진 어댑터(`backend/app/engine_adapter.py`) 단일 경유
- 10/28(M1)까지 화면 → API → 가짜 엔진 → DB 한 줄 연결로 통합 문제 조기 발견

### 8.3 환경변수 (`backend/.env`)

| 이름 | 예시 | 설명 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | (비공개) | 건한으로부터 비공개 수령, 커밋 금지 |
| `LLM_PROVIDER` | `anthropic` | 타 API 전환 시 변경 |
| `LLM_MODEL` | `claude-haiku-5-5` | |
| `LLM_MAX_CONCURRENCY` | `8` | 동시 LLM 요청 수 상한 |
| `ENGINE_IMPL` | `fake` | `fake` 백엔드 임시 가짜 엔진(LLM 미호출, 기본값) · `real` `engine` 패키지 |
| `SIM_MODE` | `agents` | `live` 실행 방식: `agents` · `single` (`replay`는 요청 `mode`로 지정) |
| `REPLAY_DELAY_MS` | `600` | 리플레이 발화 간격 |
| `DATABASE_URL` | `sqlite:///./roommate.db` | |

예시 파일: [`backend/.env.example`](../backend/.env.example)
