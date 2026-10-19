# backend

FastAPI 서버. **담당: 일준 · 범찬**

## 기술

Python, FastAPI, SQLite, SSE

## 분담 (제안 · 둘이 조정)

| 담당 | 맡는 일 | API |
| --- | --- | --- |
| 일준 | 서버 세팅 · 공통 규칙, 사용자 · 설문 · 페르소나, 시뮬레이션 · SSE, 엔진 연결, 실행 환경 | `/health` `/users` `/survey` `/personas` `/simulations` |
| 범찬 | DB 스키마 · 시드 로더, 시드 후보 10명, 후보 추림, 리포트, 매칭 · 생활 규칙 | `/candidates` `/report` `/matches` `/rules` |

## 지켜야 할 것

- 요청 · 응답 형식은 [API 명세서](../docs/API.md)를 따른다. 바꿔야 하면 명세서 PR이 먼저다.
- 엔진은 [API 명세서 7장](../docs/API.md#7-엔진-인터페이스)의 함수만 호출한다. 엔진 완성 전에는 `engine/fake.py`(가짜 엔진)를 쓴다.
- 오류는 `{ "error": { "code", "message" } }` 형식으로 통일한다.
- 환경변수는 [`.env.example`](.env.example)을 `backend/.env`로 복사해서 쓴다. `.env`는 커밋 금지.

## 실행

10/27 서버 세팅 후 작성
