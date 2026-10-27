# 프론트엔드 ↔ 백엔드 연동 인수인계

> **상태: 협의용, 미승인.** [API 명세서](API.md)는 v1.0 초안이며 백엔드 실행 코드와 확정 시드 데이터는 아직 저장소에 없다. 이 문서는 프론트엔드 mock을 실데이터로 교체할 때 필요한 계약·검증 자료를 요청한다. **새 엔드포인트나 응답 형식을 확정하지 않는다.** 계약이 합의되면 `docs/API.md`를 먼저 수정하고 동현과 백엔드 담당자의 리뷰를 받는다.

## 1. 전달 범위와 우선순위

| 우선 | 범위 | 현재 프론트엔드 처리 | 백엔드/데이터 인계물 |
| --- | --- | --- | --- |
| P0 | A1–A4, B1–B3, C1–C2 | 9개 화면과 명세 기반 mock 경로 구현. 실 API 미검증 | 아래 기존 P0 응답, SSE·오류 사례, 확정 설문/시드/장면 데이터 |
| P1 | B3 대화 다시 보기, B4 비교, C3 규칙 중재, D2 불편 전하기 | 추가 화면은 mock-first; 실 응답과 분리 | API 명세서 4.16의 5개 경로 확인, 누락된 전송/상태 계약 결정 |
| P2 | A4 5축 직접 수정, C3 시험 기간 자동 적용, D1 우리 방, D3 체크인, D4 관리자 | 시안 미리보기 데이터만 사용; 실 기능·관리자 권한으로 표시 금지 | 축 수정/재계산·학사 일정·화면별 조회/저장 스키마, 권한·개인정보 정책 합의 후 API 문서화 |

근거: [P0 구현 계획](../frontend/FRONTEND_PLAN.md), [PRD 화면 범위](PRD.md#62-화면별-범위), [기획서 PDF](../룸메궁합_서비스기획서_v1.0.pdf) 5–8쪽. P1/P2 선행 UI는 P0 실연동 완료를 뜻하지 않는다.

## 2. 기존 문서 계약 — 실서버와 대조 필요

`/api` 기반 URL, UTF-8 JSON·`snake_case`, ISO 8601 KST 시각, `{ error: { code, message } }` 오류를 따른다. `POST /users`, `GET /survey`, `GET /health`를 제외한 REST 요청에는 `X-User-Id`가 필요하다. 프론트엔드는 Vite에서 `/api`를 `localhost:8000`으로 프록시한다. [공통 규칙](API.md#1-공통-규칙), [엔드포인트 목록](API.md#2-전체-구성).

### P0 응답·상태

| 화면 | 기존 경로 | 프론트엔드가 필요한 최소 데이터/동작 |
| --- | --- | --- |
| A1–A3 | `POST /api/users`, `GET /api/survey` | `user_id`; **q01–q12 전체**(`life` 8, `situation` 4), `question_id`·`type`·`section`·`title`, 시간 문항 `fields`, 선택 문항 `options[].value/label`. 화면은 서버 순서와 `value`를 그대로 사용. |
| A4 | `POST /api/personas`, `GET/PATCH /api/personas/{id}` | `persona_id`·`nickname`·`type_name`·`summary`·5개 `axes`와 `axis_labels`·`must_keep`·`okay_with`. 두 목록은 각 3개/항목 30자 이내. |
| B1–B2 | `GET /api/personas/{id}/candidates`, `POST /api/simulations`, `GET /api/simulations/{id}`, `GET /api/simulations/{id}/events` | 익명 후보 A/B/C 3명(`candidate_id`·`alias`·학과·학년·유형·1차 점수·후보별 `simulation`), 시뮬레이션 ID·`queued/running/completed/failed`·`progress.done/total`·점수·6종 SSE 이벤트. 매칭 전 실명·사진 금지. |
| B3 | `GET /api/simulations/{id}/report` | 완료 후 점수·한 줄 판정·20개 `scene_verdicts`·판정 수·충돌/조율 `highlights`와 합의안. 완료 전 `409`; P1 `expected_conflicts_per_month`는 산식 확정 전 `null`. |
| C1–C2 | `POST /api/matches`, `GET /api/matches/{id}`, `GET /api/matches/{id}/rules`, `POST /api/matches/{id}/rules/agree` | 완료된 `simulation_id`만 신청 가능. `accepted` 후에만 `partner.name` 공개. 규칙 6개 영역·각 `source`·양측 동의 상태, 최종 `confirmed`. |

데이터 모델과 요청/응답 예시는 [API 명세서 3–4장](API.md#3-데이터-모델)을 기준으로 확인한다. 프론트엔드가 점수·합의안·대화를 실 API 대신 생성하지 않는다.

### P1 기존 경로

| 경로 | 문서상 입력/출력 | 확인이 필요한 부분 |
| --- | --- | --- |
| `GET /api/simulations/{id}/scenes` | `{ scenes: SceneResult[] }` — 장면별 대화 전문 | 미완료/실패 시 응답, 20개 미만·`pending` 허용 범위 |
| `GET /api/personas/{id}/comparison` | `me.axes`, 후보별 `candidate_id`·`alias`·`axes`·`score`·`expected_conflicts_per_month`, `recommended_candidate_id` | 후보 3명 전부 포함 여부, 미완료 후보의 `score`/월 예상값 `null` 규칙, 월 예상 갈등 산식 |
| `POST /api/rules/{rule_id}/proposals` | `{ text, reason }` → `proposal_id`, `rule_id`, `mediation.text`, `mediation.rationale[]` | 중재 근거 **2개** 보장, 제안 후 상태·상대 동의/거절·재제안 가능 여부. **현재 경로는 `rule_id` 전역 고유성과 요청자의 해당 매칭 소유권 검증이 모두 필요.** ID를 매칭 간 재사용하려면 `match_id`를 포함하는 매칭 범위 API를 별도 합의해야 함. |
| `POST /api/proposals/{proposal_id}/accept` | 바뀐 `Rule` 반환 | RuleSet 버전·동의 재확인·충돌 응답·실제 적용 시점 |
| `POST /api/mediation/rephrase` | `{ match_id, memo }` → `message`, `suggested_rule` | 원문 **미저장·상대 미전달** 보장. 시안의 “보내기”를 수행할 **전송 API는 아직 없음**; 승인 전에는 전송 완료로 표시하지 않음. mock이 지원하지 않는 주제는 결과를 지어내지 않으며, 실서버는 주제 일반화 가능 범위와 지원 불가 시 오류 계약을 정해야 함. |

위 P1 경로와 필드는 [API 명세서 4.16](API.md#416-p1-엔드포인트)에 나온 **기존 초안**이다. B3의 대화 다시 보기는 FR-B8이며 위 `scenes` 경로를 사용한다. 규칙 자동 변경을 위한 학사 일정 API·시험 기간 감지 방식은 [PRD FR-C6](PRD.md#73-흐름-c--매칭--생활-규칙)의 P2 미정 항목이다.

## 3. P2 데이터 요구 — 신규 제안, 엔드포인트 미정

아래는 PDF/PRD 화면을 실제 데이터로 채우기 위한 **필드 후보**다. 경로·권한·계산법·갱신 주기는 백엔드와 PM이 결정해야 하며, 현재 코드나 API 계약으로 간주하지 않는다.

| 화면 | 필요한 읽기/쓰기 데이터 제안 | 결정·보안 경계 |
| --- | --- | --- |
| A4 5축 직접 수정 | 페르소나의 5개 축(`sleep_rhythm`·`noise_sensitivity`·`cleanliness`·`sociability`·`sharing_tolerance`) 0–100 편집값, 수정 전/후 버전, 서버 재계산 결과 | 기존 `PATCH /personas/{id}`는 `must_keep`/`okay_with`만 정의한다. 축 수정 API·허용 범위·후보 점수/기존 시뮬레이션 재계산 정책을 결정할 것. |
| C3 시험 기간 자동 적용 | 학사 일정의 시험 시작/종료일·적용 대상 생활 규칙·적용 상태/유효 기간 | 일정 출처, 사용자 동의·해제, 타 학교/비학생 처리, 기존 중재안과의 우선순위를 결정할 것. **토글만으로 서버 변경이 이뤄진 것처럼 표시하지 않음.** |
| D1 우리 방 | `match_id`/예정 호실·동거 시작일, 생활 지수 점수와 전월 대비, 이번 주 할 일(제목·담당·기한·완료), 공용품 구매 차례·영수증/정산 금액·상태, 오늘의 조용한 시간 | 생활 지수 산식, 할 일/정산 생성·수정 주체, 결제·영수증의 개인정보·보관 기간 결정. 시드 매칭과 실제 입주를 구분. |
| D3 월간 체크인 | 대상 월, 사용자 만족도 3단계, 규칙 영역별 이행률(0–100), 최근 월별 생활 지수, 제출 여부/시각 | 체크인 저장 경로·중복 제출/수정 정책, 이행률 출처, 상대에게 보이는 범위 결정. |
| D4 관리자 | 생활관·기간별 평균 생활 지수, 중재 진행 건수, 재배정 요청 수, 위험 호실 목록(호실 식별자·점수·**갈등 유형 요약만**) | **관리자 인증/인가가 선행 조건.** 일반 방문객 `X-User-Id`로 접근 금지. 대화 원문·개인 메모·개인별 답변/실명은 반환하지 말 것. 위험 기준·소수 집계 노출 기준·감사 로그 결정. |

P2의 실제 데이터·권한 정책은 [PRD FR-A6](PRD.md#71-흐름-a--생활-페르소나), [FR-C6](PRD.md#73-흐름-c--매칭--생활-규칙), [FR-D2–D4](PRD.md#74-흐름-d--함께-사는-동안)와 별도 합의가 필요하다. 합의 전에는 “시안 미리보기/임시 데이터”로만 제공한다.

## 4. 우선 결정을 요청하는 계약 충돌

| 결정 항목 | 현재 차이/공백 | 결정 담당(문서 제안) |
| --- | --- | --- |
| 설문·시드·장면 | `data/seed/survey.json` 및 시드 후보/20장면 확정 파일 없음. API 예시는 설문 3문항 발췌뿐 | 건한: q01–q12 문구·`value`, 후보 10명·리플레이 3건, 장면 20개 확정. 일준: 실제 `GET /survey` 반영 |
| SSE 사용자 식별 | 공통 `X-User-Id` 필수 vs `EventSource` 예시에는 헤더 없음. 프론트엔드는 현재 fetch 스트림에서 헤더를 보냄 | 일준: SSE 인증·재연결 시 `Last-Event-ID` 계약 확정 |
| 시뮬레이션 `mode` | 공통 값 `agents/single/replay` vs POST 예시 `live/replay`. 현재 프론트엔드는 POST 예시 기준 | 일준·건한: 요청값/응답값과 서버 내부 모드 분리 확정 |
| 후보 시작 시점 | PRD의 3명 병렬 자동 실행 vs API 예시의 후보별 POST. 현재 프론트엔드는 후보 선택 시 시작 | 일준·범찬·동현: 자동 시작 여부·동시 요청 수·idempotency 확정 |
| P1/P2 미정 항목 | 월 예상 갈등 산식, D2 실제 전송, C3 거절/재제안·시험 기간 자동 적용, A4 축 직접 수정, D1/D3 API, D4 권한 | 건한(제품/산식), 일준·범찬(계약/권한), 동현(UI 상태) 공동 합의 |

근거: [API 공통 규칙/목록](API.md#1-공통-규칙), [SSE](API.md#5-실시간-이벤트-sse), [PRD 오픈 이슈](PRD.md#15-오픈-이슈), [기존 프론트엔드 계획](../frontend/FRONTEND_PLAN.md#4-먼저-확인할-계약협업-항목).

## 5. 백엔드 전달용 검증 fixture·인수 조건

실 서버 준비 시 **민감한 실제 사용자 데이터 대신** 재현 가능한 시드 ID와 테스트 응답을 제공해 달라. 테스트 데이터는 다음 상태를 구분해야 한다.

1. **정상:** 설문 12문항(8+4), 1명 페르소나, 익명 후보 3명, 각 후보 20장면 SSE/완료 리포트, `accepted` 매칭, 출처 포함 규칙 6개, 동의 후 `confirmed`.
2. **진행/경계:** 후보별 `null`·`queued`·`running`·`completed`·`failed`, 미완료 리포트 `409`, 장면 `pending`, P1 월 예상값 `null`, 시드 리플레이 존재/부재.
3. **오류/복구:** 사용자 헤더 누락 `401`, 설문 누락 `400`, 형식 오류 `422`, LLM 한도 `429`, LLM 장애 `503`, SSE 중복 ID·연결 끊김·`Last-Event-ID` 재전송, 2초 상태 폴링 완료. 폴링 응답은 대화 전문이 아니라 상태·진행률만 포함.
4. **P1/P2 안전:** 동일 사용자가 속한 서로 다른 매칭 2건의 규칙에 서로 다른 전역 고유 `rule_id`를 부여하고, 제안·수락에서 대상 규칙만 변경되는지 확인. 다른 사용자의 매칭 규칙 접근은 소유권 검증으로 거부. ID 재사용이 필요하면 `match_id`를 포함하는 별도 매칭 범위 API 합의 후 재검증. 매칭 전 실명 없음, D2 원문 미저장/상대 미전달 및 지원하지 않는 주제의 명시적 오류, C3 중재 근거 2개, D4 일반 사용자 접근 거부 및 집계 응답에 대화·메모·실명 없음.

**인수 완료 기준:** 담당자가 위 충돌/공백을 결정해 `docs/API.md`와 시드 파일에 반영 → 프론트엔드 `VITE_USE_MOCK=false`에서 A1→C2 및 준비된 P1 경로 완주 → 오류/복구와 390×844 화면 확인 → 양쪽 담당자 리뷰. 백엔드가 없는 동안 mock 완주는 실연동 검증으로 기록하지 않는다.
