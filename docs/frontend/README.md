# 프론트엔드 실행 안내 (`frontend/`)

- 모바일 웹 화면
- **담당: 동현** (흐름 C 화면은 범찬 지원)

## 기술

- React + TypeScript + Vite + Tailwind CSS (B4 레이더 차트는 SVG로 구현)

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

## 추가 화면 (mock-first)

| 우선순위 | 화면 | 현재 상태 |
| --- | --- | --- |
| P1 | B3 장면별 대화 다시 보기, B4 후보 비교, C3 규칙 수정, D2 불편 전하기 | [API 명세서 4.16](../common/API.md#416-p1-엔드포인트)의 경로는 프론트 클라이언트에 정의돼 있으나 백엔드에는 아직 없다. 실 모드에서는 진입을 제한하거나 준비 중으로 안내하고, mock 모드에서만 시안을 체험할 수 있다. |
| P2 | D1 우리 방, D3 월간 체크인, D4 관리자 | mock 모드의 **시안 미리보기 전용**. 실제 조회·저장 API와 관리자 인증/인가 없음 |

- P2의 페르소나 5축 직접 수정 · 시험 기간 자동 적용은 mock 화면 미리보기 전용, 서버 미반영
- D2는 요청형 문장 변환까지만 지원, **상대에게 보내기 버튼 비활성화** (전송 API 미정)

- 화면 디자인: [기획서 PDF](../common/룸메궁합_서비스기획서_v1.0.pdf) 4~8쪽 목업 준수
- P0 작업 순서·연동·완료 기준: [프론트엔드 구현 계획](PLAN.md)
- 실연동 데이터 · 미정 계약 · 검증 자료: [프론트엔드 ↔ 백엔드 인수인계](../backend/FRONTEND_HANDOFF.md)

## 개발 방법

- `/api` 요청은 Vite 프록시를 통해 `http://localhost:8000`으로 전달 ([API 명세서 8장](../common/API.md#8-로컬-개발-연결))
- 백엔드 준비 전에는 API 명세서 JSON 예시 기반 mock으로 개발 (`VITE_USE_MOCK=true`)
- 설문 문구 하드코딩 금지, `GET /api/survey` 응답 기반 렌더링

## 실행

- Node.js 20.19 이상(또는 22.12 이상) 필요
- 아래 명령은 프로젝트 루트 기준
- 팀원별 clone · Windows 명령 · 백엔드 연결: [로컬 개발 실행 가이드](../common/LOCAL_DEVELOPMENT.md)

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

- `VITE_USE_MOCK=true`: 임시 설문 · 후보 · 추가 화면 데이터 사용
- `false`: 실 API 호출. 현재 백엔드는 사용자·설문·페르소나·후보 추림과 시뮬레이션 시작/상태/SSE/완료 리포트, 매칭·생활 규칙 조회/동의 경로를 제공한다. 프론트엔드 A1→C2 실서버 완주는 아직 검증하지 않았다.
- 후보 조회 응답의 `simulation`은 아직 항상 `null`이다. 다른 세션·기기에서 실행 상태를 복원하려면 백엔드 연결이 추가로 필요하다.
- 실제 엔진은 미연결이며 기본 `ENGINE_IMPL=fake`는 개발용 결과를 만든다. `replay` 데이터·재생도 아직 준비되지 않았다.
- P2 미리보기 · 관리자 데모는 실제 모드에서 비활성
- 임시 설문 문구 · 선택지는 승인된 시드 데이터로 교체 필요

실연동 확인 시 백엔드를 `localhost:8000`에서 실행하고 `frontend/.env`의 `VITE_USE_MOCK=false`로 설정한 뒤 Vite를 재시작한다. 배포 환경의 API 버전은 별도로 확인해야 한다. 로컬 백엔드 테스트 통과나 mock 완주를 실서버 화면 완주로 간주하지 않는다.

```bash
npm run typecheck
npm test
npm run build
```

- mock 모드의 `우리 방` · `전체` 탭은 추가 화면 미리보기로 이동
- D4 관리자는 `전체`의 **데모 전용** 메뉴에서만 진입, 비식별 예시 집계만 표시
- 실제 인증 · 호실 배정 완료로 오인될 수 있는 문구 미표시
