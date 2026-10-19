# backend

- FastAPI 서버
- **담당: 일준 · 범찬**

## 기술

- Python, FastAPI, SQLite, SSE

## 분담 (제안 · 일준 · 범찬 협의)

| 담당 | 담당 업무 | API |
| --- | --- | --- |
| 일준 | 서버 세팅 · 공통 규칙, 사용자 · 설문 · 페르소나, 시뮬레이션 · SSE, 엔진 연결, 실행 환경 | `/health` `/users` `/survey` `/personas` `/simulations` |
| 범찬 | DB 스키마 · 시드 로더, 시드 후보 10명, 후보 추림, 리포트, 매칭 · 생활 규칙 | `/candidates` `/report` `/matches` `/rules` |

## 준수 사항

- 요청 · 응답 형식은 [API 명세서](../docs/API.md) 준수, 변경 필요 시 명세서 PR 선행
- 엔진은 [API 명세서 7장](../docs/API.md#7-엔진-인터페이스) 함수만 호출, 엔진 완성 전에는 `engine/fake.py`(가짜 엔진) 사용
- 오류 형식 `{ "error": { "code", "message" } }` 통일
- 환경변수: [`.env.example`](.env.example)을 `backend/.env`로 복사하여 사용, `.env` 커밋 금지

## 실행

- 10/27 서버 세팅 후 작성 예정
