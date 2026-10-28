# engine

- AI 시뮬레이션 엔진
- **담당: 건한**

## 개요

- 담당 기능: 생활 페르소나 생성, 두 AI 분신의 가상 동거(장면 20개), 장면 판정, 궁합 점수, 생활 규칙 초안
- FastAPI · DB 비의존 순수 Python 패키지로 구현
- 백엔드는 [API 명세서 7장](API.md#7-엔진-인터페이스)의 함수만 호출

## 구성 (계획)

| 파일 | 내용 |
| --- | --- |
| `llm.py` | `LLMClient` — Claude Haiku 5.5 호출, 모델 교체 지점 |
| `persona.py` | 5개 축 계산(규칙 기반) + 유형명 · 요약 생성 |
| `simulate.py` | 진행자 · 에이전트 대화 루프 · 판정자 (`agents` · `single` 모드) |
| `rules.py` | 점수, 한 줄 판정, 생활 규칙 초안 |
| `fake.py` | 가짜 엔진 — `data/replays/` 재생 (백엔드 개발 · `replay` 모드) |
| `cli.py` | 터미널 단독 실행 · 리플레이 데이터 생성 |
| `prompts/` | 페르소나 · 발화 · 판정 · 중재 프롬프트 |

## LLM

- 모델: `claude-haiku-5-5` (Claude 중 최저가), 설정은 `backend/.env`의 `LLM_*` 값
- 발화는 effort `low`, 판정은 구조화 출력(JSON 스키마)
- 방문객 1명(후보 3명 × 20장면) 약 $0.08 ~ 0.10 예상, Console 사용 한도 설정
- 설계 근거 및 비용 계산: [PRD 8장](PRD.md#8-시뮬레이션-엔진-설계) 참고
