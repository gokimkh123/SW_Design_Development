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
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
```

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

- `app/database.py`의 `initialize_database(path)`가 두 테이블을 준비한다. 반복 실행해도 기존 행을 보존하며, 기존 컬럼·외래키·UNIQUE 구조가 다르면 `SchemaConflictError`로 중단한다. 자동 삭제·재생성·이관은 하지 않는다.
- 사용자 저장과 페르소나 저장·조회가 지연 초기화를 호출한다. 앱 import, health, 설문 요청만으로 DB를 만들지 않는다. `config.py`의 경로 처리와 우선순위는 그대로 유지한다.
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
