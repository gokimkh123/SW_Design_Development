# backend

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

- 요청 · 응답 형식은 [API 명세서](../docs/API.md) 준수, 변경 필요 시 명세서 PR 선행
- 엔진은 [API 명세서 7장](../docs/API.md#7-엔진-인터페이스) 함수만 호출, 엔진 완성 전에는 `engine/fake.py`(가짜 엔진) 사용
- 오류 형식 `{ "error": { "code", "message" } }` 통일
- 환경변수: [`.env.example`](.env.example)을 `backend/.env`로 복사하여 사용, `.env` 커밋 금지

## 실행

- 10/27 서버 세팅 후 작성 예정
