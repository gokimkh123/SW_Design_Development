# 백엔드 안내 (`backend/`)

- FastAPI 서버
- **담당: 일준 · 범찬**

## 기술

- Python, FastAPI, SQLite, SSE

## 분담 (10/28 일준 · 범찬 협의로 변경)

| 담당 | 담당 업무 | API · 모듈 |
| --- | --- | --- |
| 일준 | API 서버(서버 세팅 · 공통 규칙), DB, 사용자 · 설문 · 페르소나, 후보 추림, 시뮬레이션 API · SSE, 실행 환경 | `/health` `/users` `/survey` `/personas` `/candidates` `/simulations` |
| 범찬 | 리포트, 매칭 · 생활 규칙 로직, 시드 데이터(시드 인물 11명), 엔진 연결(엔진 어댑터 · 시뮬레이션 실행기) | `/report` `/matches` `/rules` (P1 `/proposals`), `app/engine_adapter.py` |

## 현재 구현 현황 (10/31)

| 범위 | 상태 |
| --- | --- |
| 사용자 · 설문 · 페르소나 · 후보 추림 API | 구현 완료 |
| 시뮬레이션 저장 계층 (작업 1) | 입력 고정, 장면 · 이벤트 · 진행률 · 종료 상태 저장 구현 |
| 시뮬레이션 시작 API · 실행기 (작업 2) | `POST /api/simulations`, 백그라운드 20장면 실행, 점수 저장, 실패 · 종료 · 재시작 처리 구현 |
| 상태 조회 · SSE (작업 3) | 저장 상태 조회, 이벤트 전달 · 재연결 · 연결 정리 구현 |
| 완료 리포트 (작업 4) · 매칭 · 규칙 API | 후속 구현 범위 |
| 실제 엔진 통합 · replay 재생 | 실제 엔진 검증 및 replay 데이터 계약 · 연결 필요 |

시뮬레이션 작업 1~4(기존 범찬 담당 연결 · 리포트 부분 포함)는 일준이 진행한다. 위 분담 표는 10/28 협의 기록이며, 현재 시뮬레이션 담당 범위는 이 설명을 따른다. 후보 카드의 `simulation`은 아직 `null`이며 프론트엔드 연결은 후속 작업이다.

## 준수 사항

- 요청 · 응답 형식은 [API 명세서](../common/API.md) 준수, 변경 필요 시 명세서 PR 선행
- 실연동에 필요한 데이터·미정 계약·검증 사례는 [프론트엔드 ↔ 백엔드 인수인계](FRONTEND_HANDOFF.md) 참고 (협의용, 미승인)
- 엔진은 [API 명세서 7장](../common/API.md#7-엔진-인터페이스) 함수만 호출, 엔진 완성 전에는 임시 가짜 엔진(`app/fake_engine.py`, `ENGINE_IMPL=fake`) 사용
- 오류 형식 `{ "error": { "code", "message" } }` 통일
- 환경변수: [`.env.example`](../../backend/.env.example)을 `backend/.env`로 복사하여 사용, `.env` 커밋 금지

## 실행

- Python 가상환경과 `.env` 준비 명령은 [로컬 개발 실행 가이드](../common/LOCAL_DEVELOPMENT.md)를 참고
```bash
# 프로젝트 루트에서 실행
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest backend/tests -q
ENGINE_IMPL=fake backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 --workers 1
```

- 동일 DB당 서버 프로세스 하나(`--workers 1`)만 지원한다. 시작 시 기존 DB의 미종료 시뮬레이션을 실패 처리하므로 같은 DB를 사용하는 서버를 중복 실행하지 않는다.
- Python 3.12.10 기준. 실행 의존성만 설치할 경우 `backend/requirements.txt` 사용
- 기본 포트는 프론트엔드 프록시와 같은 8000. 이미 사용 중이면 기존 서버를 종료하지 않고 `--port 8001`로 별도 실행 가능. 이 경우 `/docs`도 8001로 접속하며 프론트엔드 기본 프록시와는 연결되지 않음
- 자동 문서: `http://localhost:8000/docs` → `POST /api/users`에 `{"nickname":"하늘"}` 입력 → 201 확인, `GET /api/survey` → 200 및 12문항 확인
- `GET /api/health`는 기존 `{"status":"ok"}` 유지. 세 경로 모두 인증 헤더 불필요
- `POST /api/users`: 앞뒤 공백 제거 후 1~10자 문자열 검증, 중복 닉네임 허용. 잘못된 타입·JSON은 422 `VALIDATION_ERROR`
- DB 설정 우선순위: `create_app(db_path=...)` 명시적 인수 → `DATABASE_URL` → 기존 `DATABASE_PATH` → `backend/data/users.sqlite3`. 환경변수를 모두 생략하면 기존 기본 저장 위치 유지
- `DATABASE_URL=sqlite:////srv/var/roommate.db`는 `/srv/var/roommate.db`를 가리킴. 기존 compose의 `backend-db` 볼륨에 저장
- `DATABASE_URL=sqlite:///./roommate.db`는 **앱을 생성할 때의 작업 디렉터리** 기준. 위 루트 실행 명령에서는 프로젝트 루트의 `roommate.db`, Docker의 `WORKDIR /srv/backend`에서는 `/srv/backend/roommate.db`. `--app-dir backend`는 작업 디렉터리를 변경하지 않음
- `DATABASE_PATH`의 상대 경로도 같은 기준이며 앱 생성 시 절대 경로로 고정. `DATABASE_URL`이 설정되어 있으면 빈 값이나 잘못된 값도 오류로 처리하며 `DATABASE_PATH`로 대체하지 않음
- 파일 기반 `sqlite:///` 주소만 지원. 다른 DB·드라이버·호스트 주소, 메모리 DB, 쿼리·fragment·퍼센트 인코딩은 `ValueError`로 앱 시작 실패. 실제 파일 접근 오류는 요청 시 공통 500 응답
- `.env`는 앱과 위 실행 명령에서 자동 로딩하지 않음. 필요한 값은 셸 환경변수로 전달(예: `DATABASE_URL=sqlite:///./roommate.db backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000`). Docker Compose는 기존 `env_file`과 `environment`로 값을 주입
- 첫 사용자 요청 시 DB 생성, 요청마다 커밋 및 연결 종료. 주소를 바꾸면 다른 DB를 사용하므로 기존 사용자가 새 DB에 자동으로 나타나지 않음. 기존 파일 삭제·이동·자동 이관은 수행하지 않음
- ID는 `usr_` + 소문자·숫자 8자리. DB 기본키로 중복 방지, 충돌 시 최대 10회 재시도. 생성 시각은 ISO 8601 `+09:00`
- 오류는 `{ "error": { "code": "...", "message": "한국어 설명" } }` 형식. DB·설문 처리 실패는 500 `INTERNAL_ERROR`, 내부 예외는 서버 로그에 기록

## 설문 파일 및 승인 상태

- 공식 `data/seed/survey.json`이 존재하면 우선 로딩. 요청마다 파일을 읽고 문항 순서·생활 8/상황 4·시간 범위·선택값·대화 방식을 검증
- 공식 파일이 없을 때만 `backend/app/data/survey.draft.json` 사용. **미승인 초안**, 버전 `provisional-prd-2026-10-26`
- 초안은 기존 Dockerfile의 `COPY backend/app ./app`에 포함. 공식 파일은 기존 `COPY data /srv/data`로 포함
- 근거: API 4.3(q01/q02/q09), PRD 부록 A의 문구, `frontend/src/mocks/survey.ts`의 선택값 및 순서. 기존 가짜 엔진과 호환
- 공식 파일의 JSON·인코딩·구조·선택값이 손상되면 500 반환하며 초안으로 대체하지 않음. 초안도 없거나 손상되면 500
- 남은 작업: PM의 공식 설문 승인·제공. 선택값 계약 변경 시 프론트엔드·엔진·백엔드 검증 규칙을 함께 검토
- 테스트는 임시 DB·파일을 사용하며 동시 생성, 강제 ID 충돌, 새 앱·별도 프로세스에서 저장 유지, 파일 우선순위·손상 및 `/docs`·OpenAPI를 검사. 실제 DB는 변경하지 않음


## 사용자 · 페르소나 DB

- `app/database.py`의 `initialize_database(path)`가 사용자·페르소나와 아래 시뮬레이션 저장 테이블을 준비한다. 반복 실행해도 기존 행을 보존하며, 기존 컬럼·외래키·UNIQUE 구조가 다르면 `SchemaConflictError`로 중단한다. 자동 삭제·재생성·이관은 하지 않는다.
- 사용자 저장과 페르소나 저장·조회가 지연 초기화를 호출한다. 앱 import, health, 설문 요청만으로 새 DB를 만들지 않는다. 기존 DB가 있으면 서버 lifespan 시작 시 스키마를 확인하고 미종료 시뮬레이션을 실패 처리한다. `config.py`의 경로 처리와 우선순위는 그대로 유지한다.
- 모든 앱 DB 연결은 `connect_database(path)`를 사용한다. 연결마다 `PRAGMA foreign_keys = ON`, 블록 성공 시 커밋, 예외 시 롤백, 마지막에 연결 종료를 수행한다. 초기화 DDL도 하나의 명시적 트랜잭션이다.

| 테이블 | 컬럼과 관계 |
| --- | --- |
| users | 기존 `user_id TEXT PRIMARY KEY`, `nickname TEXT NOT NULL`, `created_at TEXT NOT NULL` 유지 |
| personas | `persona_id TEXT NOT NULL PRIMARY KEY`, `user_id TEXT NOT NULL REFERENCES users(user_id)` |
| personas 문자열 | `type_name`, `summary`, `conflict_style`, `created_at`: 모두 TEXT NOT NULL |
| personas JSON | `sleep`, `axes`, `axis_labels`, `preferences`, `must_keep`, `okay_with`: 모두 TEXT NOT NULL, 저장 시 JSON 인코딩 · 조회 시 dict/list 복원 |
| personas 불리언 | `is_seed INTEGER NOT NULL CHECK (is_seed IN (0, 1))`, 조회 시 bool 복원 |

- PRD의 USER 1:N PERSONA 관계를 따른다. `user_id`에 UNIQUE를 두지 않아 사용자당 여러 페르소나를 허용한다. 삭제 연쇄 처리는 없으며 페르소나가 있는 사용자 삭제는 외래키가 거부한다.
- 닉네임은 중복 저장하지 않고 `users`와 JOIN하여 현재 값을 반환한다. 닉네임 변경 후 오래된 복사본이 남는 문제를 방지한다. 생성 당시 닉네임 스냅샷은 저장하지 않는다.
- `sleep`에는 bedtime/wake/exam_pattern, `axes`와 `axis_labels`에는 생활 성향 5개 축, `preferences`에는 temperature를 저장한다. API Persona 모델의 모든 정보를 반환한다.
- `create_persona(path, user_id, data)`는 기존 사용자 ID를 호출 계층에서 받는다. data는 아래 예시처럼 내용만 전달한다. 저장 계층이 `per_` + 영문 소문자·숫자 8자리 ID와 timezone-aware KST ISO 8601 생성 시각을 부여한다. 기본키 충돌만 최대 10회 재시도하고 소진 시 RuntimeError, 없는 사용자 저장은 SQLite IntegrityError를 전파한다.
- `get_persona(path, persona_id)`는 닉네임 포함 dict 또는 미존재 시 None을 반환한다. API에서는 `user_id` 조건을 함께 전달하여 다른 사용자의 데이터를 조회하지 않는다. DB·JSON 오류는 공통 HTTP 오류로 변환한다.
- `update_preferences(path, persona_id, user_id, changes)`는 소유자의 `must_keep`·`okay_with`만 수정한다. 과거 시뮬레이션 결과는 변경하지 않는다.

초기화만 실행 (backend 디렉터리에서, 환경변수는 실행 셸에 설정):

```bash
.venv/bin/python -c 'from app.config import database_path; from app.database import initialize_database; initialize_database(database_path())'
```

저장 · 조회 예시 (실제 개발 DB 대신 임시 DB 사용):

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from app.users import create_user
from app.personas import create_persona, get_persona

with TemporaryDirectory() as directory:
    path = Path(directory) / 'example.sqlite3'
    user = create_user(path, '하늘')
    saved = create_persona(path, user['user_id'], {
        'type_name': '규칙적인 아침형', 'summary': '조용한 아침을 좋아해요.',
        'sleep': {'bedtime': '23:00', 'wake': '06:30', 'exam_pattern': 'earlier'},
        'axes': {'sleep_rhythm': 33, 'noise_sensitivity': 67, 'cleanliness': 84,
                 'sociability': 33, 'sharing_tolerance': 0},
        'axis_labels': {'sleep_rhythm': '아침형', 'noise_sensitivity': '예민',
                        'cleanliness': '높음', 'sociability': '보통', 'sharing_tolerance': '낮음'},
        'conflict_style': 'direct', 'preferences': {'temperature': 'moderate'},
        'must_keep': ['밤에는 조용히'], 'okay_with': ['미리 말하고 친구 초대'],
        'is_seed': False,
    })
    assert get_persona(path, saved['persona_id']) == saved
```

검증 (backend 디렉터리에서):

```bash
.venv/bin/python -m pytest tests/test_personas_database.py -q
.venv/bin/python -m pytest tests -q
```

테스트는 임시 DB만 사용한다. 반복 초기화, 기존 사용자 보존, 1:N 저장, JSON 자료형과 bool 복원, 재연결 후 저장 유지, 매 연결의 외래키, 기본키 중복, ID 충돌 재시도와 소진, 실패 트랜잭션 롤백, 연결 종료, 스키마 충돌 보존, 기존 API 전체를 검사한다. 실제 개발 DB에 테스트 페르소나를 넣지 않는다.

## 페르소나 API 연결 (A4)

- 기준: `docs/common/API.md` 4.4~4.6. `app/persona_api.py`에서 기존 엔진 어댑터와 DB 저장·조회 함수를 연결한다.
- `POST /api/personas`는 `X-User-Id`로 등록 사용자를 확인하고 설문 12문항을 검증한 뒤 페르소나를 생성·저장하여 201로 반환한다. 닉네임은 사용자 DB에서 읽고 ID·KST 생성 시각은 저장 계층이 부여한다. 방문객 페르소나는 `is_seed=false`다.
- 설문 응답은 실제 `/api/survey`의 선택값과 시간 범위·30분 간격으로 검사한다. 자정을 넘는 취침 범위를 허용한다. 문항 누락은 400 `SURVEY_INCOMPLETE`이며 빠진 ID를 표시한다. 잘못된 JSON·자료형·선택값·알 수 없는 필드는 422 `VALIDATION_ERROR`다.
- `GET /api/personas/{persona_id}`는 본인 페르소나만 200으로 반환한다. 없는 ID와 다른 사용자의 ID는 동일하게 404 `PERSONA_NOT_FOUND`로 응답한다.
- `PATCH /api/personas/{persona_id}`는 보낸 문구 목록만 수정한다. 각 목록 최대 3개·항목당 30자, 빈 배열로 비우기 가능, 명시적인 `null`과 다른 필드 수정은 422다. 빈 객체는 현재 값을 그대로 반환한다.
- 세 경로 모두 헤더 누락·빈 값·미등록 사용자는 401 `USER_REQUIRED`다. 이 헤더는 발표회용 식별 규칙이며 실제 로그인 인증을 대체하지 않는다.
- 로컬 검증은 `ENGINE_IMPL=fake`로 외부 LLM 호출 없이 진행한다. 실제 엔진의 LLM 실패는 기존 어댑터의 규칙 기반 대체를 사용한다. 엔진 대기가 8초를 넘으면 취소하고 가짜 엔진 어댑터로 대체하여 명세의 10초 응답 예산 중 저장 시간을 남긴다. 예상하지 못한 엔진·DB 오류는 500이며 불완전한 결과는 저장하지 않는다.

### `/docs`에서 직접 확인

1. 서버 실행 후 `http://localhost:8000/docs`를 연다.
2. `POST /api/users`에 `{"nickname":"하늘"}`을 보내 반환된 `user_id`를 복사한다.
3. `POST /api/personas`의 **Try it out**을 누르고 `X-User-Id` 입력칸에 복사한 값을 넣는다. 본문은 다음과 같다(실제 `/api/survey`의 문구·선택값 확정 시 대조 필요).

```json
{
  "answers": {
    "q01": {"bedtime": "23:00", "wake": "06:30"},
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
```

4. 201 응답의 `persona_id`를 복사하고 `GET /api/personas/{persona_id}`에 같은 사용자 헤더로 요청하여 저장된 결과를 확인한다.
5. `PATCH /api/personas/{persona_id}`에 같은 사용자 헤더와 `{"must_keep":["밤에는 조용히"]}`를 보내 해당 목록만 바뀌는지 확인한다.
6. `q12`를 빼면 400, 선택값을 바꾸면 422, 사용자 헤더를 빼면 401, 다른 사용자의 ID로 조회·수정하면 404인지 확인한다.

페르소나 API 검사 (backend 폴더):

```bash
.venv/bin/python -m pytest tests/test_personas_api.py -q
.venv/bin/python -m pytest -q
```

- 프론트엔드 `realApi`의 생성·조회·수정 경로 및 헤더와 동일하다. 실제 화면 연결은 백엔드 8000 실행 후 `VITE_USE_MOCK=false`로 프론트엔드를 재시작하여 확인한다. 후보 조회는 아래 B1 항목을 참고한다. 시뮬레이션 등 이후 기능까지 포함한 전체 A~C 완주를 의미하지 않는다.

## 후보 추림 API (B1)

- `GET /api/personas/{persona_id}/candidates`: 본인 페르소나와 시드 후보의 생활 성향을 비교하여 상위 최대 3명을 반환한다. 요청 본문은 없고 `X-User-Id` 헤더가 필요하다.
- `app/persona_api.py`에서 등록 사용자·페르소나 소유자를 확인하고, `app/candidates.py`에서 후보 검증·점수 계산·정렬을 수행한다.
- 기본 후보 원본은 저장소의 `data/seed/personas.json`이다. 요청마다 파일을 읽으며 `candidate_pool=true`인 시드를 대상으로 한다. 조회 페르소나와 `persona_id` 또는 `user_id`가 같은 시드는 제외한다. 시드 내용을 사용자 DB로 복사하지 않는다.

### 선정 기준 및 현재 범위

사전 점수는 다음 값에 사사오입(half-up)을 적용한 0~100 정수다. 부동소수점 오차와 Python 기본 `round`의 짝수 반올림을 피하도록 정수 연산으로 계산한다.

```text
100 - Σ(가중치 × |내 축 점수 - 후보 축 점수|)
```

| 축 | 가중치 |
| --- | --- |
| 수면 리듬 (`sleep_rhythm`) | 0.30 |
| 소음 민감 (`noise_sensitivity`) | 0.25 |
| 청결 (`cleanliness`) | 0.20 |
| 사교성 (`sociability`) | 0.15 |
| 공유 성향 (`sharing_tolerance`) | 0.10 |

- 반올림한 점수 내림차순으로 정렬하며, 동점은 `candidate_id` 문자열 오름차순으로 정렬한다. 후보가 부족하면 존재하는 0~2명만 반환한다.
- `candidate_id`는 시드의 `persona_id`다. 선정 순서에 따라 `후보 A`, `후보 B`, `후보 C` 별칭을 부여한다. 이름·닉네임·사진·설문 원문은 응답에 포함하지 않는다.
- `highlight`는 두 사람 사이 차이가 가장 작은 축과 차이 점수를 표시한다. 차이가 같으면 위 표의 축 순서를 따른다.
- `pre_score`는 후보를 추리기 위한 사전 점수이며 시뮬레이션의 최종 궁합 점수가 아니다. 현재 구현은 시뮬레이션을 실행하거나 조회하지 않아 `simulation`은 항상 `null`이다. 시뮬레이션 저장·조회 구현 시 기존 실행 상태와의 연결이 별도로 필요하다.
- 필수 시드 정보 누락, 잘못된 축 값, 중복 시드 ID, 파일 손상은 500으로 처리한다. 불완전한 후보를 임의 값으로 채우거나 조용히 제외하지 않는다.

### 응답과 오류

200 응답 형식 예시(설명용 후보 1개, 실제 결과는 최대 3개):

```json
{
  "candidates": [
    {
      "candidate_id": "per_example",
      "alias": "후보 A",
      "department": "예시학과",
      "year": 1,
      "type_name": "예시 유형",
      "pre_score": 90,
      "highlight": "수면 리듬 차이 10점",
      "simulation": null
    }
  ]
}
```

| 상태 | 오류 코드 | 조건 |
| --- | --- | --- |
| 401 | `USER_REQUIRED` | 헤더 누락·빈 값·미등록 사용자 |
| 404 | `PERSONA_NOT_FOUND` | 없는 페르소나 또는 다른 사용자의 페르소나 |
| 500 | `INTERNAL_ERROR` | 시드 파일 누락·손상·필수 정보 오류 또는 DB 처리 오류 |

오류 본문은 기존 `{ "error": { "code": "...", "message": "..." } }` 형식을 사용한다.

### `/docs`에서 후보 조회 확인

1. 위 실행 명령으로 서버를 켜고 `http://localhost:8000/docs`를 연다.
2. `POST /api/users`로 사용자를 생성하고 `user_id`를 복사한다. 이미 만든 사용자가 있으면 해당 ID를 사용해도 된다.
3. 위 페르소나 API 예시대로 `POST /api/personas`에 사용자 헤더와 설문 답변을 보내고 반환된 `persona_id`를 복사한다.
4. `GET /api/personas/{persona_id}/candidates` → **Try it out**을 누른다. `persona_id`에 3번 값을, `X-User-Id`에 2번 값을 넣고 **Execute**를 누른다.
5. 200 응답에 최대 3명의 후보, 점수 내림차순, A·B·C 별칭, `simulation: null`이 표시되는지 확인한다.
6. 사용자 헤더를 비우면 401, 존재하지 않는 페르소나 또는 다른 사용자 헤더로 조회하면 404인지 확인한다.

이 수동 확인 과정의 사용자·페르소나 생성은 서버가 사용하는 개발 DB에 저장된다. 아래 자동 테스트는 임시 DB·시드 파일을 사용하여 실제 개발 데이터를 변경하지 않는다.

후보 API 및 전체 백엔드 검사 (backend 폴더에서):

```bash
.venv/bin/python -m pytest tests/test_candidates_api.py -q
.venv/bin/python -m pytest tests -q
```

테스트는 점수·사사오입, 순위·동점·본인 제외·후보 부족, 응답 필드·개인정보 제외, 사용자·소유권 확인, 시드·DB 데이터 오류를 검증한다. 실제 시드 파일을 임시 위치로 복사하여 사용자 생성 → 페르소나 생성 → 후보 조회 흐름도 검사한다.

## 시뮬레이션 저장 구조 · 실행기 연결 (작업 1)

`app/simulations.py`는 실행기·시작 API·상태 조회·SSE·완료 리포트가 공유할 저장 계층이다. 작업 1은 SQLite 저장과 조회를 제공하며 작업 2에서 시작 API와 실행기를 연결했다(아래 작업 2 절 참고). SSE 전송은 작업 3에서 연결했으며 리포트 조립은 아직 연결하지 않았다. 기존 후보 API의 `simulation: null`도 그대로다. 작업 1~4는 기존 범찬 담당 연결·리포트 부분을 포함하여 일준이 진행하며, 위 분담 표는 10/28 당시 협의 기록이다.

### 테이블 관계와 기존 DB 보존

| 테이블 | 관계와 저장 내용 |
| --- | --- |
| `simulations` | `user_id → users`, `persona_id → personas` FK. 실행 ID, 후보 ID, API 모드, 엔진 모드, 상태, 별칭, 진행률, KST 시각, 입력 스냅샷, 완료 결과와 실패 정보 |
| `simulation_scenes` | `simulation_id → simulations` FK, `(simulation_id, scene_index)` PK. 공개 장면 스냅샷, 순서 있는 발화 목록, 판정 JSON |
| `simulation_events` | `simulation_id → simulations` FK, `(simulation_id, sequence)` PK. 실행별 이벤트 ID와 재시도 키 각각 UNIQUE. 공개 `data`, 내부 `internal_data`, 유형, KST 저장 시각 |

- 시드 후보는 `data/seed/personas.json`에 있고 `personas`에는 없으므로 `candidate_id`는 출처 식별용 TEXT다. 후보 ID에 FK를 걸거나 시드 사용자·페르소나를 DB에 복제하지 않는다. DB 후보는 생성 트랜잭션 안에서 실제 페르소나를 읽고, JSON 시드는 호출자가 검증·선정한 원본을 넘긴다. 장면 템플릿도 JSON 입력 스냅샷으로 보관하고 별도 장면 원본 테이블은 만들지 않는다. PRD 10.3의 초안 FK 그림을 물리적으로 그대로 적용하지 않는 이유다. 매칭·생활 규칙 테이블은 없다.
- `initialize_database(path)`가 기존 users/personas를 보존하면서 세 테이블과 두 인덱스를 **추가**한다. 기존 두 테이블의 컬럼·제약은 바꾸지 않는다. 초기화 전체를 `BEGIN IMMEDIATE`로 처리하므로 실패하면 추가 DDL도 롤백된다.
- 반복 초기화를 지원한다. 구조가 다른 동명 테이블·인덱스가 있으면 `SchemaConflictError`로 중단한다. 새 테이블의 CHECK와 부분 UNIQUE 조건도 검사하며, 동일 의미라도 DDL 문자열이 다르면 수동 검토가 필요하다. 자동 DROP·재생성·데이터 이관은 없다. 이 버전의 기존 DB 확장은 추가 DDL만으로 충분하며, 향후 구조 변경은 백업 후 별도 보존형 마이그레이션을 마련해야 한다.
- `connect_database`를 그대로 사용한다. 매 연결 FK 활성화, 성공 커밋·실패 롤백·항상 연결 종료. 저장은 `BEGIN IMMEDIATE`, 여러 SELECT를 조합하는 조회도 읽기 트랜잭션으로 일관된 스냅샷을 읽는다. 모든 값은 SQL 바인딩한다. 실제 개발 DB에 초기화·테스트를 실행하지 않았다.

### 입력 · 공개 데이터 · 모드

`simulations.inputs`에는 생성 당시 본인 Persona, 후보 원본(시드 메타데이터 포함), 장면 템플릿 목록을 JSON으로 고정한다. 본인 선호·닉네임이나 시드 JSON이 바뀌어도 기존 실행을 다시 읽어 갱신하지 않는다. 별칭도 생성 시점 값을 유지한다. `get_internal_record`는 이 원본과 실패 상세를 포함하므로 내부 운영용으로만 사용하고 HTTP/SSE 응답으로 반환하지 않는다.

`engine_inputs`의 후보는 Persona 필드만 선별하고 `nickname`을 `후보 A/B/C`로 바꾼다. 원본 `name`, `answers`, `greeting`, 학과 등은 엔진 입력에서 제외한다. 알려진 후보 `name`/`nickname`은 자유 문구에서도 별칭으로 치환한다. 공개 이벤트는 유형별 허용 필드를 검증하고 동일한 치환을 적용하며 후보 발화의 `name`은 저장된 별칭 + ` AI`로 강제한다. 원본 이벤트는 내부 컬럼에만 저장한다. 후속 실행기는 반드시 `get_execution_inputs`의 입력을 사용해야 한다. 이 치환은 알려진 원본 이름에 대한 방어이며 LLM이 임의로 생성한 다른 개인정보를 판별하는 기능은 아니다.

- API 모드 `mode`: `live`/`replay`. `create_or_reuse_simulation`에는 **실제 실행 모드**를 전달한다. replay 파일이 없으면 호출 계층에서 먼저 live로 결정한다. 저장 계층은 파일을 탐색하거나 fallback을 결정하지 않는다.
- `engine_mode`: live 생성 시 기존 `engine_adapter.resolve_mode('live')`로 `SIM_MODE`의 `agents`/`single`을 확정하여 저장한다. 이후 환경변수가 바뀌어도 저장된 값을 `EngineAdapter.simulate(mode=...)`에 전달한다. replay의 엔진 모드는 NULL이고 엔진을 호출하면 안 된다.
- 입력의 장면 목록 길이를 `total`로 사용한다(서비스 기본 20). 장면 ID 중복은 거부한다. 테스트·단축 시연을 위해 개수 자체를 20으로 강제하지 않는다.

### 저장 함수 계약

모든 함수의 첫 인수는 DB 경로다. 생성 외 조회·저장 함수는 `simulation_id`와 선택적인 `user_id=...`를 받는다. 공개 요청 경계에서는 반드시 소유자 ID를 전달한다. `user_id=None`은 내부 작업용이다. 다른 소유자와 미존재 실행은 조회에서 동일하게 `None`, 저장에서 `LookupError`다. 형식 오류는 `ValueError`/Pydantic 검증 오류, 상태·순서·재시도 충돌은 `StorageConflictError`, DB 오류는 SQLite 예외로 전파한다. HTTP 오류 변환은 후속 API의 책임이다.

| 함수 | 입력 · 반환 · 책임 |
| --- | --- |
| `create_or_reuse_simulation(path, *, user_id, persona_id, candidate, alias, scenes, mode='live')` | `candidate`는 선정된 시드 원본 dict 또는 DB 후보의 `persona_id`, `is_seed=false`를 포함한 dict. `scenes`는 템플릿 목록. `(Simulation dict, created: bool)` 반환. 소유자 확인·본인 제외·입력 고정·실행 생성/재사용을 한 트랜잭션에서 처리 |
| `get_simulation(path, id, user_id=...)` | API 3장의 Simulation 필드만 반환. 진행률·판정 개수·점수·시작/완료 시각 포함, 원본 입력과 내부 모드는 제외 |
| `get_execution_inputs(path, id, user_id=...)` | 익명 `me`, `candidate`, `scenes`, 실제 `mode`, 고정 `engine_mode` 반환. 내부 실행기용 |
| `get_internal_record(path, id, user_id=...)` | 실행 행과 복원된 원본/엔진 JSON·완료/실패 자료. 원본 실명 포함, 공개 금지 |
| `start_simulation(path, id, user_id=...)` | 입력 스냅샷에서 `simulation_started` 생성·저장. `{id, sequence, type, data}` 반환. 엔진이나 작업을 시작하지 않음 |
| `save_event(path, id, event, user_id=...)` | 실제 어댑터 형태 `{type, data}`를 받는다. 장면 시작·발화·판정 및 관련 진행률을 원자적으로 저장하고 공개 이벤트 반환. `error`는 실패 함수로 위임 |
| `update_progress(path, id, user_id=...)` | 저장된 판정 수에서 `{done, total}` 재계산. 증가량을 받지 않으며 판정 저장 시 이미 같은 트랜잭션에서 갱신됨 |
| `complete_simulation(path, id, *, score, headline, report=None, user_id=...)` | 외부에서 계산한 0~100 정수 점수·문구·선택적인 완성 리포트 dict를 받아 완료 결과와 `simulation_completed`를 함께 저장. 판정 개수는 DB에서 산출, 점수/리포트 계산은 수행하지 않음 |
| `fail_simulation(path, id, error, user_id=...)` | `{code, message, scene_index: int 또는 null, retryable: bool}` 검증 후 실패 시각·정보·종료 error 이벤트를 함께 저장. 생략한 scene_index는 null |
| `list_scenes(path, id, user_id=...)` | 장면 순서의 공개 장면·대화·판정. 진행 중인 미판정 장면에는 판정 필드가 없음 |
| `list_events(path, id, after_event_id=None, user_id=...)` | 전역 sequence 순 공개 이벤트 목록. ID 미지정은 전체, 지정하면 해당 ID **이후**. 해당 실행에 없는 ID는 ValueError, 마지막 ID 이후는 빈 목록 |
| `get_completion(path, id, user_id=...)` | 저장된 `{score, headline, verdict_counts, report}`. 미완료는 StorageConflictError. report는 아직 계산하지 않았다면 null |

완료 함수의 `report`에는 후속 리포트 계층이 API Report 형식으로 만든 공개 데이터만 전달한다. 저장 함수는 그 리포트를 계산하거나 Report 스키마 전체를 검증하지 않는다. 후속 계층에서 simulation_id, score, verdict_counts 등의 일치를 검증해야 한다.

### 재사용 · 상태 전이 · 순서

- API 4.8에 따라 **동일 persona_id + candidate_id + 실제 mode**의 running/completed를 재사용한다. 입력 해시·현재 SIM_MODE·수정된 선호·별칭을 재사용 키에 추가하지 않는다. completed도 원래 스냅샷을 유지한다. failed 이후에는 새로운 실행을 만들 수 있다.
- 이번 생성 함수는 API가 허용하는 `running` 상태로 실행을 원자적으로 예약한다. `started_at`은 이 예약 시각이며 첫 엔진 호출 시각이 아니다. `created=true`를 받은 호출자만 후속 작업을 등록한다. `created=false`면 재실행하지 않는다. 이 반환값은 작업 큐나 다중 worker lease를 대체하지 않는다.
- `BEGIN IMMEDIATE`와 `(persona_id,candidate_id,mode)`의 부분 UNIQUE 인덱스를 함께 사용한다. 인덱스는 queued/running/completed에 적용한다. queued는 이번 생성 함수가 만들지 않는다. 기존 queued가 발견되면 충돌 예외를 내고 추가 생성하지 않는다. **queued 재요청의 HTTP 처리·대기열 정책은 API 4.8에 없으므로 작업 2에서 결정해야 한다.** 이 구현은 queued를 running/completed와 같은 API 재사용 대상으로 임의 확장하지 않는다.
- 허용 전이: `queued → running/failed`, `running → completed/failed`. completed/failed는 종단 상태다. queued → running은 `start_simulation`이 처리한다. 동일 시작·완료·실패 요청은 내용이 같으면 기존 이벤트를 반환한다. 종료 후 새 장면·새 판정·반대 종료 상태는 거부한다. 상태 변경은 전용 함수를 거쳐야 한다.
- 장면은 1부터 시작하고 이전 판정 완료 후 다음 장면을 시작한다. 입력 스냅샷의 scene_id를 확인한다. 발화 turn은 1~4의 연속 정수다. 판정 보류 pending도 처리된 장면 1개로 계산한다. 판정 progress가 `{done: scene_index, total: 저장 total}`과 다르면 전체 저장을 거부한다.
- 재시도 키는 시작/완료/실패 각각 하나, 장면 시작·판정은 유형+scene_index, 발화는 유형+scene_index+turn이다. 같은 키·같은 정규화 입력은 기존 이벤트 반환, 내용이 다르면 충돌이다. 종료 후에도 이미 저장된 동일 장면 이벤트 재시도는 기존 값을 반환한다. 중복 판정이 진행률을 늘리지 않는다.
- 시작 ID는 `0-0`. 장면별 이벤트 ID는 `{scene_index}-{0부터의 순번}`, 별도 `sequence`는 실행 전체에서 1부터 증가한다. 완료 이벤트는 마지막 장면의 다음 순번이다. error는 명시된 오류 scene_index의 다음 순번을 쓰고, 장면 무관 오류는 마지막 시작 장면(없으면 0)을 사용한다. 문자열 ID의 사전순으로 정렬하지 않는다. ID는 실행 안에서만 유일하다.
- 저장에 성공한 반환 이벤트만 후속 SSE가 전송해야 한다. 재연결은 `list_events(after_event_id=Last-Event-ID)`를 사용한다. ping, 전송 속도, 연결 종료는 저장 함수의 책임이 아니다. 완료 후에도 모든 저장 이벤트를 읽을 수 있다.

### 후속 실행기 연결 순서와 제한

1. 사용자·후보 선정과 replay 파일 존재 여부를 확인하고 실제 모드를 결정한다. `create_or_reuse_simulation`을 호출한다. 신규일 때만 실행 작업을 예약한다.
2. `get_execution_inputs`로 고정 입력을 읽고 `start_simulation`을 저장한다. 이후 live 실행은 익명 입력과 고정 engine_mode로 어댑터를 호출하고 replay는 파일 이벤트를 읽는다. **작업 2에서 live 실행기를 연결했다. replay는 아래 데이터 계약 제한을 참고한다.**
3. 어댑터는 `scene_started`, `utterance`, `scene_judged`, `error`만 반환한다. 각 이벤트를 `save_event`에 전달하고 커밋된 공개 반환값을 사용한다. fake_engine의 판정은 scene_id가 없으므로 저장된 장면에서 보충한다. 실제 모델이 scene_id를 주면 일치 여부를 확인한다.
4. 판정 저장 시 장면·이벤트·진행률이 함께 커밋된다. 별도 진행률 확인이 필요하면 `get_simulation`, 재계산이 필요하면 `update_progress`를 사용한다. 별도로 done을 증가시키지 않는다.
5. 모든 장면이 끝나면 공개 `list_scenes`에서 판정을 읽어 후속 계층에서 점수·headline·리포트를 계산한다. 엔진 SceneJudgement가 필요하면 scene_index, `scene.scene_id`, verdict, reason, agreement, rule_candidate, unresolved를 구성한다. 결과를 `complete_simulation`에 전달한다. 오류는 `fail_simulation`에 전달한다. 예외를 공개 문구로 안전하게 변환하는 책임도 실행기에 있다.

현재 `EngineAdapter.simulate`는 장면 템플릿 목록을 인수로 받지 않고 엔진이 직접 읽는다. 저장된 scenes는 감사·순서 검증용이며, 향후 실행기가 원본 템플릿 변경 후 완전히 동일한 장면을 재현하려면 엔진 인터페이스 협의 또는 고정 replay가 필요하다. 이번에 공통 명세나 어댑터 계약을 변경하지 않았다.

작업 1 저장 계층 자체는 서버 재시작 시 queued/running을 자동 변경하지 않는다. 작업 2의 단일 프로세스 lifespan은 아래 운영 전제하에 미종료 실행을 실패 처리한다. 단순 시간 경과만으로 실패를 확정하면 살아 있는 다른 worker와 충돌할 수 있다. 운영자는 이전 worker가 종료되었음을 확인한 뒤 해당 실행을 `fail_simulation`으로 실패 처리하고, 사용자의 새 시작 요청으로 새 ID를 만들도록 한다. 오류 코드는 기존 `INTERNAL_ERROR`, 공개 문구는 예를 들어 `서버 재시작으로 실행이 중단되었습니다.`, retryable=false를 사용한다. 여기서 retryable은 SSE 재연결 여부이며 엔진 자동 재실행 권한이 아니다. 작업 큐·lease·자동 복구는 후속 범위다.

### 터미널에서 임시 DB 저장 · 조회

backend 디렉터리에서 실행한다. 실제 개발 DB나 API 서버를 사용하지 않는다.

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from app.personas import PersonaData, create_persona
from app.users import create_user
from app.simulations import (
    create_or_reuse_simulation, get_execution_inputs, get_simulation,
    start_simulation, save_event, list_events, list_scenes,
)

seeds = json.loads(Path('../data/seed/personas.json').read_text())['personas']
candidate = next(p for p in seeds if p['candidate_pool'])
scene = dict(scene_id='S01', day=1, weekday='월', time='06:30',
             category='수면·소음', title='이른 알람', situation='후보 A와 알람 시간 조율')
with TemporaryDirectory() as temp:
    db = Path(temp) / 'simulation.sqlite3'
    user = create_user(db, '테스터')
    data = {key: seeds[0][key] for key in PersonaData.model_fields}
    data['is_seed'] = False
    me = create_persona(db, user['user_id'], data)
    simulation, created = create_or_reuse_simulation(
        db, user_id=user['user_id'], persona_id=me['persona_id'],
        candidate=candidate, alias='후보 A', scenes=[scene], mode='live',
    )
    sid = simulation['simulation_id']
    print('새 실행:', created, '엔진 모드:', get_execution_inputs(db, sid)['engine_mode'])
    start_simulation(db, sid)
    save_event(db, sid, {'type': 'scene_started', 'data': {'scene_index': 1, 'scene': scene}})
    print(get_simulation(db, sid, user_id=user['user_id']))
    print(list_scenes(db, sid))
    print(list_events(db, sid, after_event_id='0-0', user_id=user['user_id']))
PY
```

검증 명령 (backend 디렉터리):

```bash
.venv/bin/python -m pytest tests/test_simulations.py tests/test_personas_database.py -q
.venv/bin/python -m pytest tests -q
```

새 저장 테스트는 임시 DB로 기존 행 보존·반복 초기화·스키마 충돌 보존, 입력 고정, JSON 시드와 DB 후보, 모드, 사용자 범위, 동시 실행 생성·동시 판정 재시도, DB 유일성, 상태 전이, 실제 가짜 엔진 20장면, 순서·익명화, 진행률·완료·실패 일관성, 이벤트 커서, 재연결, ID 충돌, 이벤트 INSERT 실패 시 장면/진행률/종료 상태 롤백을 검사한다. 실제 LLM·HTTP 시뮬레이션·SSE 전송 검사는 작업 1 범위에 포함하지 않는다.

## 시뮬레이션 시작 API · 실행기 (작업 2)

작업 1~4는 기존 범찬 담당 연결 부분까지 일준이 진행한다. 작업 2는 `POST /api/simulations`와 `app/simulation_runner.py`를 연결한다. 작업 2 자체는 시작·실행만 담당하며 상태 조회·SSE는 아래 작업 3에서 연결한다. 리포트·매칭·규칙 API와 프론트엔드는 후속 범위다. 후보 카드의 `simulation: null`도 유지한다.

- 요청: `X-User-Id` 헤더와 `{"persona_id":"...","candidate_id":"...","mode":"live"}`. mode 생략 시 live. 등록 사용자와 본인 페르소나를 확인하고 기존 `select_candidates` 상위 3명만 허용한다. 헤더 누락/미등록은 401 USER_REQUIRED, 비소유/없는 페르소나/선택 불가 후보는 404 PERSONA_NOT_FOUND, 잘못된 JSON·필드·mode는 422 VALIDATION_ERROR다.
- 신규는 202 + 공통 Simulation 모델, 동일 페르소나·후보·실제 모드의 running/completed는 200 + 기존 모델. `BEGIN IMMEDIATE`와 기존 부분 UNIQUE 인덱스가 중복 예약을 막고, created=true일 때만 task를 등록한다. 응답은 전체 엔진 실행을 기다리지 않는다. failed는 새 ID로 다시 요청할 수 있다.
- queued는 저장 계약 그대로 충돌이며 일반 500 INTERNAL_ERROR로 반환한다. 새 실행기는 queued를 생성하지 않는다. **queued 중복의 전용 HTTP 코드/재사용 정책은 공통 명세에 없어 협의가 필요하다.** 임의의 새 오류 코드를 공통 명세에 추가하지 않았다.
- 생성 시 엔진의 20개 장면을 고정하고 익명 입력을 저장한다. 실행기는 `get_execution_inputs` → `start_simulation` → 어댑터 `simulate` → 각 이벤트 `save_event` 순서로 진행한다. 장면은 순차 저장하며 후보별 작업은 병렬로 실행한다. 각 장면에 대화와 판정이 있고 20개 모두 처리된 뒤 정상 스트림 종료일 때만 기존 `score`/`headline`을 호출하고 `complete_simulation`으로 기록한다. report는 null이며 리포트 조립은 하지 않는다.
- 공개 이름은 저장 계약의 후보 A/B/C를 엔진 호출 전 적용한다. 공개 장면·대화·이벤트·최종 문구에도 알려진 후보 실명을 치환한다. 원본 `inputs`와 `internal_data`는 내부 자료이므로 공개하면 안 된다.
- `ENGINE_IMPL=fake`는 기존 가짜 엔진, `ENGINE_IMPL=real`은 기존 어댑터의 실제 엔진 경로다. 실제 엔진 실패를 가짜 성공으로 바꾸지 않는다. live 내부 모드는 `SIM_MODE=agents|single`을 생성 시 고정한다. `SIMULATION_TIMEOUT_SECONDS` 기본 180초(양수)는 전체 실행 제한이다. 예외/DB 저장 실패, 시간 초과, 취소, 불완전 이벤트 종료는 서로 다른 실패 문구와 error 이벤트로 남는다. 엔진 error 이벤트도 종단 실패다.
- 후보 3명의 task를 동시에 실행할 수 있고 장면 순서는 저장 계층에서 검증한다. `LLM_MAX_CONCURRENCY`(공통 기본 8)는 실제 엔진의 개별 LLM 요청 제한 계약이다. 현재 저장소의 `engine/`는 비어 있어 그 제한 구현/실제 성능은 검증하지 못했다. 백엔드에서 후보 전체를 직렬화하는 별도 제한은 추가하지 않았다.

### 생명주기와 운영 제한

**동일 DB당 서버 프로세스 1개, uvicorn workers=1만 지원한다.** 다중 worker/서버 중첩 실행은 지원하지 않는다. DB의 중복 예약 방지는 실행 lease가 아니며, 재시작 복구가 다른 worker의 실행을 실패 처리할 수 있다.

요청 내 DB 예약과 task 등록 사이에는 await가 없고 작업 참조를 서버가 보유한다. 클라이언트 연결이 끊겨도 등록된 실행은 계속된다. 작업 완료 콜백은 참조를 제거하고 예외를 회수한다. 서버 정상 종료 시 모든 작업을 취소·대기하고 실패를 저장한다. task가 첫 실행 전에 취소된 경우도 처리한다. 강제 종료로 남은 running/queued는 다음 lifespan 시작에서 기존 `fail_simulation`으로 실패 처리한다. 이는 이전 프로세스가 종료되었다는 단일 프로세스 운영 전제 아래 작업 1의 수동 중단 처리 절차를 자동화한 것이다. 복구 저장 실패 시 서버 시작을 중단한다. 자동 엔진 재실행은 없다.

DB 저장 후 task 등록 실패는 API 500과 실패 기록으로 처리한다. 실행 도중 DB 저장 실패도 실행을 중단하고 별도 실패 트랜잭션을 시도한다. DB가 계속 쓰기 불가능하면 실패 상태 자체를 보장할 수 없으므로 로그와 메모리에 미저장 실패를 남기고 정상 종료 때 재시도한다. 강제 종료 또는 지속 장애 후에는 DB 복구 후 서버를 재시작하여 미종료 실행을 실패 처리해야 한다. 장면/이벤트 저장은 기존 트랜잭션으로 롤백되며 성공으로 가장하지 않는다. SQLite 호출은 짧은 동기 구간으로 수행하므로 DB 잠금 대기 동안 이벤트 루프가 지연될 수 있다. 외부 큐나 새 서비스는 도입하지 않았다.

### replay의 현재 한계와 필요한 결정

현재 `data/replays/`와 실제 리플레이 자료·파일명·파일 스키마 계약이 없다. 공통 API 4.8대로 파일이 없으면 live를 실행하고 **응답과 DB mode도 live**로 기록한다. ENGINE_IMPL=fake라면 이 live는 개발용 가짜 엔진 실행이며 replay 성공이 아니다. 리플레이 디렉터리에 숨김 파일을 제외한 파일이 발견되면 임의로 읽거나 live로 숨기지 않고 500 INTERNAL_ERROR를 반환한다. 실제 재생은 데이터 제공자와 페르소나/후보별 파일 선택, 이벤트/최종 점수 스키마를 확정하고 실제 파일을 연결해야 한다. `REPLAY_DELAY_MS`는 재생 연결 전에는 적용되지 않는다. 공통 명세는 변경하지 않았다.

### IntelliJ 터미널과 /docs 확인

IntelliJ 터미널에서 backend 디렉터리 기준으로 실행한다. 아래 경로는 시연용 DB다. `DATABASE_URL`이 이미 설정되어 있으면 `DATABASE_PATH`보다 우선하므로, 별도 시연 DB를 사용하려면 먼저 해당 환경변수 설정을 해제한다. `.env`는 자동 로딩되지 않는다.

```bash
ENGINE_IMPL=fake SIM_MODE=agents DATABASE_PATH=/tmp/kkokkoroom-demo.sqlite3 .venv/bin/python -m uvicorn app.main:app --port 8000 --workers 1 --log-level info
```

1. `http://localhost:8000/docs`에서 POST `/api/users`에 `{"nickname":"하늘"}`을 보내고 user_id를 복사한다.
2. GET `/api/survey`로 문항을 확인한다. POST `/api/personas`의 X-User-Id에 user_id, body에 위 페르소나 실행 예시의 12문항 answers를 입력하고 persona_id를 복사한다.
3. GET `/api/personas/{persona_id}/candidates`에 같은 헤더를 보내 candidate_id를 선택한다.
4. POST `/api/simulations`에 같은 헤더와 persona_id/candidate_id/mode=live를 보내 202와 simulation_id를 확인한다. 같은 요청은 200으로 기존 실행을 반환한다.
5. GET `/api/simulations/{simulation_id}`에 같은 X-User-Id를 넣어 상태·진행률을 확인한다. 아래 SQLite 조회는 내부 진단용이며 failure 상세를 공개 응답으로 사용하지 않는다. 앱 로그의 `시뮬레이션 completed/failed`는 app 로거 INFO를 활성화한 경우 볼 수 있다(uvicorn log-level만으로 앱 INFO가 표시되는 것은 아니다).

```bash
sqlite3 -readonly /tmp/kkokkoroom-demo.sqlite3 'SELECT simulation_id,status,done,total,result,failure FROM simulations ORDER BY created_at;'
.venv/bin/python -m pytest tests/test_simulation_start.py tests/test_simulations.py -q
.venv/bin/python -m pytest tests -q
```

테스트는 임시 DB와 제어 가능한 가짜 엔진만 사용한다. 정상 백그라운드 20장면/점수 저장, 응답 시 미완료, 사용자/후보/요청 검증, 동시 중복과 완료 재사용, 후보 3명 격리, 실명 비노출, 예외/시간 초과/취소/불완전 종료, 시작/DB 실패, queued 충돌, 서버 종료·재시작, replay 부재 fallback과 데이터 존재 시 명시적 실패를 검증한다. 유료 LLM과 실제 사용자 DB는 사용하지 않는다.


## 상태 조회 · SSE 진행 상황 전달 (작업 3)

작업 1의 공개 Simulation·이벤트 저장과 작업 2의 실행기를 재사용한다. 두 GET API 모두 엔진 호출, 신규 실행, 이벤트 생성이나 진행률 갱신을 하지 않는다. **다음 작업 4인 완료 리포트 API는 아직 구현되지 않았다.** 프론트엔드·매칭·생활 규칙도 이번 범위에서 제외했다.

### 상태 조회와 수동 확인

`GET /api/simulations/{simulation_id}`는 공통 API 3장의 Simulation을 반환한다. `status`는 queued/running/completed/failed이며 `progress`는 `{ "done": 9, "total": 20 }` 형태다. done은 저장 계층에서 장면 판정과 같은 트랜잭션으로 기록한 완료 장면 수다(pending 판정도 완료 장면). 완료는 20/20과 점수·completed_at을 반환하고, 실패는 마지막 진행률과 null 점수·completed_at을 유지한다. 대화 전문이나 내부 실패 상세는 포함하지 않는다. SSE를 사용할 수 없으면 명세대로 2초 간격으로 조회하고 completed/failed에서 폴링을 멈춘다.

`/docs`에서 위 작업 2의 사용자→페르소나→후보→시작 순서로 ID를 얻은 뒤 GET `/api/simulations/{simulation_id}` → Try it out → simulation_id와 X-User-Id 입력 → Execute로 확인한다. `/docs`의 스트림 표시가 실시간 수신을 보장하지 않으므로 SSE는 터미널에서 확인한다. 아래 값은 같은 서버에서 발급한 실제 ID로 바꾼다. 사용 중인 서버나 개발 DB를 변경하지 않으려면 앞 절의 별도 시연 DB·빈 포트로 실행한다.

```bash
SIM_USER_ID=usr_abcdefgh
SIM_RUN_ID=sim_abcdefgh
SIM_BASE=http://localhost:8000
curl -sS -H "X-User-Id: $SIM_USER_ID" "$SIM_BASE/api/simulations/$SIM_RUN_ID"
curl -N -H 'Accept: text/event-stream' -H "X-User-Id: $SIM_USER_ID" \
  "$SIM_BASE/api/simulations/$SIM_RUN_ID/events"
# 실제로 마지막까지 처리한 이벤트 ID를 넣어 재연결한다.
curl -N -H 'Accept: text/event-stream' -H "X-User-Id: $SIM_USER_ID" \
  -H 'Last-Event-ID: 0-0' "$SIM_BASE/api/simulations/$SIM_RUN_ID/events"
```

### 이벤트와 재연결 계약

응답은 `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`다. UTF-8 JSON 한 줄과 빈 줄로 프레임을 구분한다. 아래는 형식 예시다.

```text
id: 0-0
event: simulation_started
data: {"simulation_id":"sim_abcdefgh","mode":"live","total_scenes":20,"me":{"name":"하늘","type_name":"아침형"},"candidate":{"alias":"후보 A","type_name":"조용한 유형"}}

: ping

```

- 실행기가 저장한 simulation_started → scene_started/utterance/scene_judged → simulation_completed 또는 error를 DB의 정수 sequence 순서로 전송한다. 시작 이벤트는 매 접속 시 새로 만들지 않는다. 공통 API 5.1의 “연결 직후 1회”는 저장된 시작 이벤트 재생을 뜻하며 5.3의 커서 이후 재전송 규칙을 우선한다.
- Last-Event-ID가 없으면 처음부터, 있으면 **해당 ID 다음**부터 보낸다. ID는 작업 1의 `{scene_index}-{장면 내 순번}`이며 실행 내에서만 유일하다. 문자열 사전순 비교나 장면 번호만으로 건너뛰지 않는다. 클라이언트는 `(simulation_id, id)`로 중복을 제거한다. 네트워크 재연결의 정확히 한 번 전달은 보장하지 않는다.
- 공통 명세에 잘못된 커서의 세부 HTTP 정책이 없어 기존 저장 함수의 ValueError와 공통 422 VALIDATION_ERROR를 연결했다. 빈 값, 잘못된 형식, 아직 저장되지 않은 미래/범위 밖 ID, 다른 실행에만 있는 ID는 스트림 시작 전에 422다. 다른 실행에서 얻은 ID라도 대상 실행에 같은 문자열이 존재하면 구분할 수 없으며 대상 실행의 커서로 해석한다. 전역 ID나 새 인증 규칙은 도입하지 않았다.
- 각 구독이 독립 커서를 가지며 읽어도 DB 이벤트를 삭제하지 않는다. 상태와 최대 64개 이벤트를 하나의 읽기 트랜잭션에서 조회하므로 과거 조회/대기 경계와 종료 상태 변경 사이의 이벤트도 다음 조회에서 받는다. 쌓인 페이지는 즉시 이어 읽고, 새 데이터가 없으면 0.5초마다 조회한다. DB 읽기는 스레드풀에서 수행하고 대기 전에 연결·트랜잭션을 닫는다. 실행기 변경이나 메모리 이벤트 큐 없이 영속 DB를 전달 근거로 사용한다.
- 업무 이벤트가 없는 동안 15초마다 `: ping` 주석을 보낸다. heartbeat에는 id가 없으며 DB 이벤트와 진행률에 포함하지 않는다. 연결 해제 시 Starlette가 구독 generator/대기를 취소하며 실행기 task는 계속된다. 진행 중 DB 호출은 짧은 조회가 끝나 연결을 닫은 뒤 정리된다(SQLite 잠금 대기는 기존 10초 제한).
- 완료·실패 이벤트까지 전송한 뒤 정상 EOF로 끝낸다. 이미 종료된 실행도 저장 이벤트를 재생한다. 마지막 종료 ID로 재접속하면 보낼 이벤트 없이 200 EOF다. 클라이언트는 simulation_completed 또는 retryable=false error에서 재접속을 멈춘다. retryable=true 재연결도 저장 이력만 재조회하며 엔진을 다시 실행하지 않는다.
- 공개 data만 읽으며 후보 실명은 기존 저장 계층의 별칭 치환을 재사용한다. error의 자유 메시지·알 수 없는 code는 내부 경로·비밀 유출 방지를 위해 공개 경계에서 고정 문구/INTERNAL_ERROR로 변환한다. 알려진 LLM 오류는 code·retryable을 보존하고 INTERNAL_ERROR는 retryable=false다. 내부 원본은 변경하지 않는다. 임의 생성 대화의 모든 개인정보를 판별하는 기능은 아니다.
- 브라우저 기본 EventSource는 X-User-Id를 설정할 수 없으므로 공통 API 5.4처럼 fetch 스트림과 헤더를 사용한다. 사용자 ID를 URL에 넣는 인증 방식은 제공하지 않는다.

### 오류 · 운영 · 현재 제한

스트림 시작 전 사용자 누락·빈 헤더·미등록은 401 USER_REQUIRED, 없는 실행/다른 소유자는 동일한 404 SIMULATION_NOT_FOUND, 잘못된 커서는 422 VALIDATION_ERROR, DB 처리 오류는 500 INTERNAL_ERROR다. 모두 `{ "error": { "code": "...", "message": "..." } }` JSON이다. 200 전송 후 DB 장애는 내부 상세나 임의 업무 이벤트를 보내지 않고 스트림을 닫고 서버에 기록한다. 클라이언트는 마지막 처리 ID로 재접속할 수 있다.

서버 재시작 시 작업 2의 단일 worker 복구가 미종료 실행을 실패 처리하고 error를 저장한다. 기존 이벤트와 이 error는 재접속 후 조회 가능하며 자동 재실행하지 않는다. 동일 DB당 workers=1 제약과 replay 파일 계약/실제 재생 미구현은 그대로다. 따라서 REPLAY_DELAY_MS 기반 재생도 아직 지원하지 않는다. 구독별 폴링이므로 대규모 동시 접속 성능은 검증하지 않았으며, 엔진의 기존 동기 SQLite 쓰기로 인한 이벤트 루프 지연도 남아 있다.

저장소의 실제 배포 구성 `deploy/docker-compose.yml`과 `frontend/nginx.conf`를 확인했다. `/api/`에 HTTP/1.1, Connection 제거, proxy_buffering off, proxy_cache off, proxy_read_timeout 1h가 있어 15초 heartbeat와 호환된다. 보호된 배포 파일은 수정하지 않았다. 실행 중 VM·외부 CDN/LB의 실제 적용 상태와 타임아웃은 접근하지 않아 검증하지 못했다.

### 테스트

backend 디렉터리에서:

```bash
.venv/bin/python -m pytest tests/test_simulation_progress.py -q
.venv/bin/python -m pytest tests -q
```

임시 DB와 가짜/제어 가능한 엔진으로 조회 상태·진행률·무변경, 접근 제어, 프레임·순서·ID·재연결·잘못된 커서, 페이지/대기 경계 누락, 완료/실패·종료 후 접속, 후보 실명·내부 오류 비노출, 앱 재시작·복구를 검사한다. 실제 HTTP 테스트는 OS가 할당한 루프백 임시 포트의 uvicorn과 httpx 스트림으로 **실행 종료 전에 첫 프레임 수신**, 새 이벤트 전달, 두 구독의 독립 수신, 연결 종료 후 generator 정리·실행기 유지, heartbeat 비저장을 확인한다. 비동기 테스트는 시간 제한과 finally 정리를 사용한다. 로컬 포트 바인딩이 차단된 환경에서는 권한 허용이 필요하며 이 검사를 생략한 채 실시간 전달 검증을 완료했다고 판단하면 안 된다. 유료 LLM과 실제 개발 DB는 사용하지 않는다.
