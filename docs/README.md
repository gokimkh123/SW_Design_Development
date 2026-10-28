# 문서 목록

- 저장소의 모든 문서를 본 폴더에 통합 (저장소 루트에는 `README.md`만 유지)

## 공통

| 문서 | 내용 |
| --- | --- |
| [PRD](PRD.md) | 요구사항, 범위, 시뮬레이션 엔진 설계, 발표회 운영, 역할 |
| [API 명세서](API.md) | 엔드포인트, 데이터 모델, SSE 이벤트, 엔진 인터페이스 |
| [일정 · 간트 차트](SCHEDULE.md) | 사람별 간트 차트, 마일스톤, 날짜별 할 일 |
| [협업 가이드](CONTRIBUTING.md) | 브랜치 · 커밋 · PR · 리뷰 규칙, CI/CD, 비밀 정보 관리 |
| [로컬 개발 실행 가이드](LOCAL_DEVELOPMENT.md) | clone · 프론트엔드 실행 · 백엔드 준비 및 실연동 절차 |
| [VM 배포 안내](DEPLOY.md) | Docker 이미지 · VM 준비 · 배포 Secrets · 운영 명령 |
| [서비스 기획서 v1.0 (PDF)](룸메궁합_서비스기획서_v1.0.pdf) | 제안 배경, 화면 설계, 수익 모델, 사업 확장 방안 |

## 영역별

| 폴더 | 문서 | 담당 |
| --- | --- | --- |
| [`frontend/`](frontend/) | [실행 안내](frontend/README.md) · [P0 구현 계획](frontend/PLAN.md) | 동현 |
| [`backend/`](backend/) | [백엔드 안내](backend/README.md) · [프론트엔드 ↔ 백엔드 인수인계](backend/FRONTEND_HANDOFF.md) | 일준 · 범찬 |
| [`engine/`](engine/) | [엔진 설계](engine/README.md) | 건한 |
| [`data/`](data/) | [시드 데이터 형식](data/SEED.md) | 건한 · 범찬 |

## 기타

- [`images/`](images/): README · PRD용 이미지, [`scripts/gantt.py`](scripts/gantt.py): 간트 차트 생성
