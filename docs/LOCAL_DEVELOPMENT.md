# 로컬 개발 실행 가이드

> **현재 실행 가능:** 프론트엔드 mock 모드. 백엔드는 아직 서버 코드·의존성 명세·실행 진입점이 없어 실행할 수 없다. 프론트엔드·백엔드 명령은 clone 후 저장소 루트에서 시작한다.

## 1. 저장소 받기와 사전 준비

```bash
git clone https://github.com/gokimkh123/SW_Design_Development.git
cd SW_Design_Development
```

Git, Node.js 20.19 이상(또는 22.12 이상), npm을 준비한다. 백엔드 담당자는 Python 3와 `venv`도 준비한다. 프론트엔드 버전 조건은 [Vite 프로젝트 실행 안내](../frontend/README.md#실행)를 따른다.

**브랜치 안내:** 개발 기준 브랜치는 `develop`. clone 후 `git switch develop` → `git pull` 순으로 최신화하고, 작업 브랜치는 `develop`에서 분기한다. `main`은 배포 · 발표회 버전 전용([협업 가이드](../CONTRIBUTING.md#작업-흐름) 참고).

## 2. 프론트엔드만 실행 — 백엔드 불필요

macOS/Linux (저장소 루트에서):

```bash
cd frontend
npm ci
cp .env.example .env
npm run dev
```

Windows PowerShell (저장소 루트에서, 이 macOS 환경에서는 미검증):

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env
npm run dev
```

`.env.example`의 `VITE_USE_MOCK=true`가 적용된다. 터미널에 표시된 주소(기본 `http://localhost:5173`)를 열어 닉네임부터 시연한다. 이 모드의 설문·후보·시뮬레이션·P2 화면은 **임시 데이터**이며 실제 API나 AI 엔진을 호출하지 않는다. 이미 `.env`가 있으면 복사 명령을 반복하지 말고 값을 확인한다.

다른 터미널에서 `frontend/`로 이동한 뒤 품질 검사를 실행한다.

```bash
npm run typecheck
npm test
npm run build
```

## 3. 백엔드 개발 환경 준비 — 서버 실행은 아직 불가

macOS/Linux (저장소 루트에서):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
```

Windows PowerShell (저장소 루트에서, 이 macOS 환경에서는 미검증):

```powershell
Set-Location backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

`backend/.env`의 API 키는 비공개 채널로 받아야 하며 **커밋하지 않는다**. 현재 저장소에는 FastAPI ASGI 앱, `engine/fake.py`, 확정 설문 · 장면 데이터가 없다(시드 인물은 `data/seed/personas.json` 초안 존재, 백엔드 테스트는 `backend/requirements-dev.txt`로 실행 가능). 따라서 지금은 `pip install`이나 `uvicorn` 실행 명령을 제시할 수 없다. 백엔드 담당자가 의존성 명세와 앱 진입점을 추가한 뒤 **실제 설치·실행 명령을 [backend/README.md](../backend/README.md)에 기록하고 검증**해야 한다.

구현할 API 응답·SSE·검증 fixture는 [API 명세서](API.md)와 [프론트엔드 ↔ 백엔드 인수인계](FRONTEND_BACKEND_HANDOFF.md)를 기준으로 합의한다. 엔진·시드가 준비되지 않은 동안에는 실제 시뮬레이션 완료를 주장하지 않는다.

## 4. 실 API와 연결 — 백엔드 실행 명령이 생긴 뒤

1. 백엔드 담당자가 검증한 명령으로 서버를 `http://localhost:8000`에서 실행한다. 구현 후 `curl http://localhost:8000/api/health`와 `http://localhost:8000/docs`로 응답·문서를 확인한다. **현재는 이 명령/주소가 동작하지 않는다.**
2. `frontend/.env`의 값을 `VITE_USE_MOCK=false`로 바꾸고 프론트엔드 개발 서버를 **재시작**한다.
3. `frontend/`에서 `npm run dev`를 실행한다. Vite는 브라우저의 `/api` 요청을 `localhost:8000`으로 프록시한다. 실제 연결에서는 P0/P1 경로를 검증하고, P2·관리자 미리보기는 열리지 않는다.
4. [인수인계 문서의 검증 사례](FRONTEND_BACKEND_HANDOFF.md#5-백엔드-전달용-검증-fixture인수-조건)에 따라 정상 경로뿐 아니라 401/409/429/503, SSE 재연결·폴링, 미완료 후보를 확인한다.

실서버가 아직 없는데 `VITE_USE_MOCK=false`로 설정하면 API 요청이 실패한다. UI 확인만 할 때는 `true`로 되돌리고 Vite를 재시작한다.
