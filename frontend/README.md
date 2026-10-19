# frontend

- 모바일 웹 화면
- **담당: 동현** (흐름 C 화면은 범찬 지원)

## 기술

- React + TypeScript + Vite, Tailwind CSS, Recharts (P1 레이더 차트)

## 구현 화면 (P0 9개)

| ID | 화면 | API |
| --- | --- | --- |
| A1 | 매칭 시작 (닉네임) | `POST /api/users` |
| A2 | 생활 설문 | `GET /api/survey` |
| A3 | 상황 질문 | `GET /api/survey` |
| A4 | 페르소나 카드 | `POST /api/personas` · `PATCH /api/personas/{id}` |
| B1 | 후보 목록 | `GET /api/personas/{id}/candidates` · `POST /api/simulations` |
| B2 | 시뮬레이션 | `GET /api/simulations/{id}/events` (SSE) |
| B3 | 리포트 | `GET /api/simulations/{id}/report` |
| C1 | 매칭 성사 | `POST /api/matches` · `GET /api/matches/{id}` |
| C2 | 생활 규칙 | `GET /api/matches/{id}/rules` · `POST .../rules/agree` |

- P1: B4 후보 비교, C3 규칙 수정, D2 불편 전하기
- 화면 디자인: [기획서 PDF](../룸메궁합_서비스기획서_v1.0.pdf) 4~8쪽 목업 준수

## 개발 방법

- `/api` 요청은 Vite 프록시를 통해 `http://localhost:8000`으로 전달 ([API 명세서 8장](../docs/API.md#8-로컬-개발-연결))
- 백엔드 준비 전에는 API 명세서 JSON 예시 기반 mock으로 개발 (`VITE_USE_MOCK=true`)
- 설문 문구 하드코딩 금지, `GET /api/survey` 응답 기반 렌더링

## 실행

- 10/27 프로젝트 세팅 후 작성 예정
