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
- `get_persona(path, persona_id)`는 닉네임 포함 dict 또는 미존재 시 None을 반환한다. DB·JSON 오류는 숨기지 않는다. 향후 API 계층이 이를 HTTP 응답으로 변환해야 한다. API 경로와 엔진 호출은 이번 구현에 포함하지 않는다.

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
