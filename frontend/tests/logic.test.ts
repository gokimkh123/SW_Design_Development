import { test } from 'node:test';
import assert from 'node:assert/strict';
import { areAnswersComplete, isAnswerComplete } from '../src/lib/survey';
import { applySimulationEvent, initialStreamState, latestCandidateSimulation } from '../src/lib/simulation';
import { conflictsDisplay, verdictLabel } from '../src/lib/report';
import { ApiError, parseSseBlock, realApi, setUserId } from '../src/api/real';
import { simulationStartErrorText } from '../src/lib/simulationError';
import { withSessionSimulation } from '../src/lib/candidateOverlay';
import { mockApi } from '../src/mocks/client';
import { provisionalSurvey } from '../src/mocks/survey';
import { isCurrentSimulation, mergeSimulation } from '../src/features/flowState';
import { previewAdmin, previewCheckin, previewRoom } from '../src/mocks/preview';
import type { Answers, Candidate, Report, Simulation, SimulationEvent } from '../src/api/types';

test('후보 상태: 실패 후 새 완료 시뮬레이션이 이전 실패를 대체한다', () => {
  const base = {
    persona_id: 'per_me', candidate_id: 'per_a', mode: 'live', progress: { done: 0, total: 20 },
    verdict_counts: { harmonious: 0, negotiated: 0, conflict: 0, pending: 0 },
    score: null, started_at: '2026-11-03T10:00:00+09:00', completed_at: null,
  } satisfies Omit<Simulation, 'simulation_id' | 'status'>;
  const failed: Simulation = { ...base, simulation_id: 'sim_failed', status: 'failed' };
  const completed: Simulation = {
    ...base, simulation_id: 'sim_retry', status: 'completed',
    progress: { done: 20, total: 20 }, score: 88,
  };
  assert.equal(latestCandidateSimulation([failed, completed], 'per_me', 'per_a')?.simulation_id, 'sim_retry');
  assert.equal(latestCandidateSimulation([failed, completed], 'per_me', 'per_b'), undefined);
});

test('시뮬레이션 시작: 경로 404만 준비 중으로 안내하고 자원 오류는 보존한다', () => {
  const missingRoute = new ApiError(404, 'VALIDATION_ERROR', '요청 경로, 메서드 또는 형식을 확인해 주세요.');
  assert.match(simulationStartErrorText(missingRoute, false), /준비 중/);
  assert.equal(simulationStartErrorText(missingRoute, true), missingRoute.message);
  const missingPersona = new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
  assert.equal(simulationStartErrorText(missingPersona, false), missingPersona.message);
  const unavailable = new ApiError(503, 'LLM_UNAVAILABLE', 'AI 연결에 실패했어요.');
  assert.equal(simulationStartErrorText(unavailable, false), unavailable.message);
});

test('후보 카드: 확인된 세션 실행만 null 후보 상태에 덧씌운다', () => {
  const candidates: Candidate[] = ['per_a', 'per_b'].map(candidate_id => ({
    candidate_id, alias: '후보 A', department: '학과', year: 1, type_name: '유형',
    pre_score: 80, highlight: '특징', simulation: null,
  }));
  const simulation: Simulation = {
    simulation_id: 'sim_a', persona_id: 'per_me', candidate_id: 'per_a', mode: 'live',
    status: 'completed', progress: { done: 20, total: 20 },
    verdict_counts: { harmonious: 20, negotiated: 0, conflict: 0, pending: 0 },
    score: 88, started_at: '2026-11-03T10:00:00+09:00', completed_at: '2026-11-03T10:05:00+09:00',
  };
  const overlaid = withSessionSimulation(candidates, simulation, { personaId: 'per_me', simulationId: 'sim_a' });
  assert.equal(overlaid[0].simulation?.status, 'completed');
  assert.equal(overlaid[0].simulation?.score, 88);
  assert.strictEqual(overlaid[1], candidates[1]);
  assert.strictEqual(withSessionSimulation(candidates, simulation, { personaId: 'other', simulationId: 'sim_a' })[0], candidates[0]);
  assert.strictEqual(withSessionSimulation(candidates, simulation, { personaId: 'per_me' })[0], candidates[0]);
});

test('B2 상태: 늦은 REST 응답이 SSE 완료·진행률을 되돌리지 않는다', () => {
  const base = {
    simulation_id: 'sim_a', persona_id: 'per_me', candidate_id: 'per_a', mode: 'live',
    verdict_counts: { harmonious: 0, negotiated: 0, conflict: 0, pending: 0 },
    score: null, started_at: '2026-11-03T10:00:00+09:00', completed_at: null,
  } satisfies Omit<Simulation, 'status' | 'progress'>;
  const running9: Simulation = { ...base, status: 'running', progress: { done: 9, total: 20 } };
  const running3: Simulation = { ...base, status: 'running', progress: { done: 3, total: 20 } };
  const completed: Simulation = {
    ...base, status: 'completed', progress: { done: 20, total: 20 },
    score: 88, completed_at: '2026-11-03T10:05:00+09:00',
  };
  assert.strictEqual(mergeSimulation(running9, running3), running9);
  assert.strictEqual(mergeSimulation(completed, running9), completed);
  assert.strictEqual(mergeSimulation(running9, completed), completed);
  assert.equal(isCurrentSimulation('sim_b', 'sim_a'), false);
  assert.equal(isCurrentSimulation('sim_b', 'sim_b'), true);
});

test('설문: 응답 값과 시간 범위를 검증하고 12문항을 요구한다', () => {
  const q01 = provisionalSurvey.questions[0];
  assert.equal(isAnswerComplete(q01, { bedtime: '23:00', wake: '07:00' }), true);
  assert.equal(isAnswerComplete(q01, { bedtime: '23:15', wake: '07:00' }), false);
  assert.equal(isAnswerComplete(q01, { bedtime: '12:00', wake: '07:00' }), false);
  const answers: Answers = Object.fromEntries(provisionalSurvey.questions.map((q) =>
    [q.question_id, q.type === 'time_range' ? { bedtime: '23:00', wake: '07:00' } : q.options![0].value]));
  assert.equal(areAnswersComplete(provisionalSurvey.questions, answers), true);
  answers.q09 = 'unknown';
  assert.equal(areAnswersComplete(provisionalSurvey.questions, answers), false);
});

test('SSE: id 중복은 무시하고 pending을 포함한 20장면 진행을 보존한다', () => {
  const event: SimulationEvent = {
    id: '9-4', type: 'scene_judged',
    data: { scene_index: 9, verdict: 'pending', reason: '재시도 중', agreement: null,
      rule_candidate: null, unresolved: '판정 보류', progress: { done: 9, total: 20 } },
  };
  const once = applySimulationEvent(initialStreamState(), event);
  assert.equal(once.progress.done, 9);
  assert.equal(once.sceneVerdicts[9], 'pending');
  assert.strictEqual(applySimulationEvent(once, event), once);
  assert.equal(verdictLabel.pending, '판정 보류');
});

test('SSE: 주석과 이벤트 블록을 파싱한다', () => {
  const event = parseSseBlock(': ping\nid: 1-0\nevent: scene_started\ndata: {"scene_index":1,"scene":{"scene_id":"S01"}}');
  assert.equal(event?.id, '1-0');
  assert.equal(event?.type, 'scene_started');
  assert.equal(parseSseBlock(': ping'), null);
  assert.equal(parseSseBlock(''), null);
  for (const block of [
    'event: scene_judged\ndata: {"scene_index":1}',
    'id: 1-3\ndata: {"scene_index":1}',
    'id: 1-3\nevent: scene_judged',
  ]) {
    assert.throws(() => parseSseBlock(block), { code: 'SSE_MALFORMED_EVENT' });
  }
  assert.throws(() => parseSseBlock('id: 2-0\nevent: scene_started\ndata: {잘못된 JSON'), {
    code: 'SSE_MALFORMED_EVENT',
  });
});

test('리포트: null P1 지표를 예측 수치로 꾸미지 않는다', () => {
  assert.equal(conflictsDisplay({ expected_conflicts_per_month: null } as Report), '아직 제공하지 않아요');
});

test('실 API: health → 사용자 생성 → 설문 조회를 공개 경로로 호출한다', async () => {
  setUserId(null);
  const originalFetch = globalThis.fetch;
  const calls: Array<{ path: string; method: string; body: unknown; userId: string | null }> = [];
  globalThis.fetch = async (url, init) => {
    calls.push({
      path: String(url), method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      userId: new Headers(init?.headers).get('X-User-Id'),
    });
    const path = String(url);
    const payload = path === '/api/health' ? { status: 'ok' }
      : path === '/api/users' ? { user_id: 'usr_new', nickname: '하늘', created_at: '2026-10-29T00:00:00Z' }
        : provisionalSurvey;
    return Response.json(payload, { status: path === '/api/users' ? 201 : 200 });
  };
  try {
    assert.deepEqual(await realApi.getHealth(), { status: 'ok' });
    const user = await realApi.createUser('하늘');
    setUserId(user.user_id);
    const survey = await realApi.getSurvey();
    assert.equal(survey.questions.length, 12);
    assert.deepEqual(calls.map(({ method, path }) => [method, path]), [
      ['GET', '/api/health'], ['POST', '/api/users'], ['GET', '/api/survey'],
    ]);
    assert.deepEqual(calls[1].body, { nickname: '하늘' });
    assert.ok(calls.every(({ userId }) => userId === null));
  } finally {
    setUserId(null);
    globalThis.fetch = originalFetch;
  }
});

test('실 API: 백엔드 연결 실패를 안내 가능한 오류로 반환한다', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError('fetch failed'); };
  try {
    await assert.rejects(realApi.getHealth(), {
      status: 0,
      code: 'NETWORK_ERROR',
      message: '백엔드에 연결할 수 없어요. 서버 실행 상태를 확인해 주세요.',
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('실 SSE: 인증 헤더·Last-Event-ID 재연결·중복 제거', async () => {
  setUserId('usr_test0001');
  const originalFetch = globalThis.fetch;
  const headers: Headers[] = [];
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    headers.push(new Headers(init?.headers));
    calls++;
    const payload = calls === 1
      ? 'id: 0-0\r\nevent: simulation_started\r\ndata: {"simulation_id":"sim_test","mode":"live","total_scenes":20,"me":{"name":"나","type_name":"유형"},"candidate":{"alias":"후보 A","type_name":"유형"}}\r\n\r\nid: 1-0\r\nevent: scene_started\r\ndata: {"scene_index":1,"scene":{"scene_id":"S01"}}\r\n\r\n'
      : 'id: 1-0\r\nevent: scene_started\r\ndata: {"scene_index":1,"scene":{"scene_id":"S01"}}\r\n\r\nid: 20-4\r\nevent: simulation_completed\r\ndata: {"score":88,"headline":"완료","verdict_counts":{"harmonious":20,"negotiated":0,"conflict":0,"pending":0}}\r\n\r\n';
    const bytes = new TextEncoder().encode(payload);
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 10));
        controller.enqueue(bytes.slice(10));
        controller.close();
      },
    });
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  };
  try {
    const events = await new Promise<SimulationEvent[]>((resolve, reject) => {
      const received: SimulationEvent[] = [];
      realApi.subscribeSimulation('sim_test', (event) => {
        received.push(event);
        if (event.type === 'simulation_completed') resolve(received);
      }, reject);
    });
    assert.equal(events.length, 3);
    assert.equal(headers[0].get('X-User-Id'), 'usr_test0001');
    assert.equal(headers[1].get('Last-Event-ID'), '1-0');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('실 SSE: 서버 오류 이벤트 뒤 리더를 취소하고 잠금을 해제한다', async () => {
  setUserId('usr_test0001');
  const originalFetch = globalThis.fetch;
  let canceled = 0;
  globalThis.fetch = async () => new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(
        'id: 1-0\nevent: error\ndata: {"code":"LLM_UNAVAILABLE","message":"다시 시도","retryable":true}\n\n',
      ));
    },
    cancel() { canceled++; },
  }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  try {
    await new Promise<void>((resolve) => {
      realApi.subscribeSimulation('sim_error', () => {}, () => resolve());
    });
    assert.equal(canceled, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('실 SSE: 잘못된 JSON 뒤 완료를 표시하지 않고 마지막 정상 ID로 재시도한다', async () => {
  setUserId('usr_test0001');
  const originalFetch = globalThis.fetch;
  const headers: Headers[] = [];
  let canceled = 0;
  globalThis.fetch = async (_url, init) => {
    headers.push(new Headers(init?.headers));
    return new Response(new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(
          'id: 1-0\nevent: scene_started\ndata: {"scene_index":1,"scene":{"scene_id":"S01"}}\n\n' +
          'id: 2-0\nevent: scene_started\ndata: {잘못된 JSON\n\n' +
          'id: 20-4\nevent: simulation_completed\ndata: {"score":88}\n\n',
        ));
      },
      cancel() { canceled++; },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  };
  try {
    const events: SimulationEvent[] = [];
    const failure = await new Promise<Error>((resolve) => {
      realApi.subscribeSimulation('sim_malformed', (event) => events.push(event), resolve);
    });
    assert.equal((failure as Error & { code?: string }).code, 'SSE_MALFORMED_EVENT');
    assert.deepEqual(events.map((event) => event.id), ['1-0']);
    assert.equal(headers.length, 3);
    assert.equal(headers[0].get('Last-Event-ID'), null);
    assert.equal(headers[1].get('Last-Event-ID'), '1-0');
    assert.equal(headers[2].get('Last-Event-ID'), '1-0');
    assert.equal(canceled, 3);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('P1 실 클라이언트: 문서 경로·본문과 X-User-Id 헤더를 사용한다', async () => {
  setUserId('usr_p1');
  const originalFetch = globalThis.fetch;
  const calls: Array<{ path: string; method: string; body: unknown; userId: string | null }> = [];
  globalThis.fetch = async (url, init) => {
    calls.push({
      path: String(url), method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
      userId: new Headers(init?.headers).get('X-User-Id'),
    });
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  };
  try {
    await realApi.getScenes('sim_a');
    await realApi.getComparison('per_a');
    await realApi.proposeRule('rul_a', { text: '22:30부터', reason: '시험 기간' });
    await realApi.acceptProposal('prp_a');
    await realApi.rephraseMemo('mat_a', '원문은 나만 보기');
    assert.deepEqual(calls.map(({ path, method }) => [method, path]), [
      ['GET', '/api/simulations/sim_a/scenes'],
      ['GET', '/api/personas/per_a/comparison'],
      ['POST', '/api/rules/rul_a/proposals'],
      ['POST', '/api/proposals/prp_a/accept'],
      ['POST', '/api/mediation/rephrase'],
    ]);
    assert.ok(calls.every((call) => call.userId === 'usr_p1'));
    assert.deepEqual(calls[2].body, { text: '22:30부터', reason: '시험 기간' });
    assert.deepEqual(calls[4].body, { match_id: 'mat_a', memo: '원문은 나만 보기' });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('P2 미리보기: 관리자 데이터에 대화·메모 원문 또는 실명은 없다', () => {
  assert.equal(previewRoom.previewOnly, true);
  assert.equal(previewCheckin.previewOnly, true);
  assert.equal(previewAdmin.previewOnly, true);
  assert.equal(previewAdmin.riskRooms.length, 3);
  for (const room of previewAdmin.riskRooms) {
    assert.deepEqual(Object.keys(room).sort(), ['conflictTypes', 'room', 'score']);
  }
  assert.ok(!/memo|dialogue|message|name|메모|대화 원문/i.test(JSON.stringify(previewAdmin.riskRooms)));
});

test('mock: A1→C2 계약 경로, 익명 후보, 20장면, 6개 규칙', async () => {
  const user = await mockApi.createUser('하늘');
  setUserId(user.user_id);
  const survey = await mockApi.getSurvey();
  const answers: Answers = Object.fromEntries(survey.questions.map((q) =>
    [q.question_id, q.type === 'time_range' ? { bedtime: '23:00', wake: '07:00' } : q.options![0].value]));
  const persona = await mockApi.createPersona(answers);
  const candidates = (await mockApi.getCandidates(persona.persona_id)).candidates;
  assert.equal(candidates.length, 3);
  assert.equal('name' in candidates[0], false);
  const simulation = await mockApi.startSimulation(persona.persona_id, candidates[0].candidate_id);
  assert.equal((await mockApi.startSimulation(persona.persona_id, candidates[0].candidate_id)).simulation_id, simulation.simulation_id);
  await assert.rejects(mockApi.getReport(simulation.simulation_id), { status: 409, code: 'SIMULATION_NOT_COMPLETED' });
  const seen = await new Promise<SimulationEvent[]>((resolve, reject) => {
    const events: SimulationEvent[] = [];
    mockApi.subscribeSimulation(simulation.simulation_id, (event) => {
      events.push(event);
      if (event.type === 'simulation_completed') resolve(events);
    }, reject);
  });
  assert.equal(seen.filter((event) => event.type === 'scene_judged').length, 20);
  const report = await mockApi.getReport(simulation.simulation_id);
  assert.equal(report.scene_verdicts.length, 20);
  const match = await mockApi.createMatch(simulation.simulation_id);
  assert.equal(match.status, 'accepted');
  assert.ok(match.partner?.name);
  const rules = await mockApi.getRules(match.match_id);
  assert.equal(rules.rules.length, 6);
  assert.equal((await mockApi.agreeRules(match.match_id)).status, 'confirmed');

  // B2 구독이 사라지거나 아예 열리지 않아도 mock 엔진과 B1 폴링은 끝나야 한다.
  const dropped = await mockApi.startSimulation(persona.persona_id, candidates[1].candidate_id);
  const neverSubscribed = await mockApi.startSimulation(persona.persona_id, candidates[2].candidate_id);
  await new Promise<void>((resolve, reject) => {
    const stop = mockApi.subscribeSimulation(dropped.simulation_id, (event) => {
      if (event.type === 'scene_judged') { stop(); resolve(); }
    }, reject);
  });
  let finalDropped = await mockApi.getSimulation(dropped.simulation_id);
  let finalNever = await mockApi.getSimulation(neverSubscribed.simulation_id);
  for (let retry = 0; retry < 70 && (finalDropped.status !== 'completed' || finalNever.status !== 'completed'); retry++) {
    await new Promise((resolve) => setTimeout(resolve, 100));
    finalDropped = await mockApi.getSimulation(dropped.simulation_id);
    finalNever = await mockApi.getSimulation(neverSubscribed.simulation_id);
  }
  assert.equal(finalDropped.status, 'completed');
  assert.equal(finalNever.status, 'completed');
  assert.equal(finalDropped.progress.done, 20);
  assert.equal((await mockApi.getReport(dropped.simulation_id)).score, finalDropped.score);
  const refreshed = (await mockApi.getCandidates(persona.persona_id)).candidates;
  assert.equal(refreshed[1].simulation?.status, 'completed');
  assert.equal(refreshed[2].simulation?.status, 'completed');
  const replayed = await new Promise<SimulationEvent[]>((resolve, reject) => {
    const events: SimulationEvent[] = [];
    mockApi.subscribeSimulation(dropped.simulation_id, (event) => {
      events.push(event);
      if (event.type === 'simulation_completed') resolve(events);
    }, reject);
  });
  assert.equal(replayed.filter((event) => event.type === 'scene_judged').length, 20);
});

test('P1 mock: 장면 다시 보기→후보 비교→규칙 중재→비공개 메모 초안', async () => {
  const originalStorage = globalThis.sessionStorage;
  const saved = new Map<string, string>();
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => saved.get(key) ?? null,
      setItem: (key: string, value: string) => { saved.set(key, value); },
      removeItem: (key: string) => { saved.delete(key); },
    },
  });
  try {
    const user = await mockApi.createUser('새봄');
    setUserId(user.user_id);
    const survey = await mockApi.getSurvey();
    const answers: Answers = Object.fromEntries(survey.questions.map((question) => [
      question.question_id,
      question.type === 'time_range' ? { bedtime: '23:00', wake: '07:00' } : question.options![0].value,
    ]));
    const persona = await mockApi.createPersona(answers);
    const candidates = (await mockApi.getCandidates(persona.persona_id)).candidates;
    const simulation = await mockApi.startSimulation(persona.persona_id, candidates[0].candidate_id);
    await new Promise<void>((resolve, reject) => {
      mockApi.subscribeSimulation(simulation.simulation_id, (event) => {
        if (event.type === 'simulation_completed') resolve();
      }, reject);
    });
    const scenes = await mockApi.getScenes(simulation.simulation_id);
    assert.equal(scenes.scenes.length, 20);
    assert.equal(scenes.scenes[0].dialogue.length, 2);
    const comparison = await mockApi.getComparison(persona.persona_id);
    assert.equal(comparison.candidates.length, 3);
    assert.equal(comparison.candidates[0].score, (await mockApi.getReport(simulation.simulation_id)).score);
    assert.equal(comparison.candidates[0].expected_conflicts_per_month, 0.5);
    assert.equal(comparison.candidates[1].expected_conflicts_per_month, null);

    const match = await mockApi.createMatch(simulation.simulation_id);
    const rules = await mockApi.getRules(match.match_id);
    const proposal = await mockApi.proposeRule(rules.rules[0].rule_id, {
      text: '시험 기간에는 22:30부터', reason: '실습 평가 주간',
    });
    assert.equal(proposal.mediation.rationale.length, 2);
    const changed = await mockApi.acceptProposal(proposal.proposal_id);
    assert.equal((await mockApi.getRules(match.match_id)).rules[0].text, changed.text);

    const privateMemo = '내 비밀 메모는 상대에게 전달하면 안 돼. 청소를 또 안 했어';
    const draft = await mockApi.rephraseMemo(match.match_id, privateMemo);
    assert.ok(draft.message && !draft.message.includes(privateMemo));
    assert.equal((await mockApi.rephraseMemo(match.match_id, '청소를 또 안 했어')).suggested_rule.area, 'cleaning');
    assert.equal((await mockApi.rephraseMemo(match.match_id, '아침 알람을 여러 번 꺼')).suggested_rule.area, 'quiet_hours');
    await assert.rejects(mockApi.rephraseMemo(match.match_id, '방이 너무 추워요'), {
      status: 422, code: 'MOCK_TOPIC_UNSUPPORTED',
    });
    const unsupportedMemo = '방이 너무 추워요';
    assert.ok(!JSON.stringify(await mockApi.getMatch(match.match_id)).includes(privateMemo));
    assert.ok(!JSON.stringify(await mockApi.getRules(match.match_id)).includes(privateMemo));
    assert.ok(!(saved.get('roommate.mock.state') ?? '').includes(privateMemo));
    assert.ok(!(saved.get('roommate.mock.state') ?? '').includes(unsupportedMemo));
    assert.equal('sendMemo' in mockApi, false);
  } finally {
    if (originalStorage === undefined) delete (globalThis as { sessionStorage?: Storage }).sessionStorage;
    else Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: originalStorage });
  }
});

test('P1 mock: 두 매치의 규칙 제안·수락은 다른 매치를 바꾸지 않는다', async () => {
  const user = await mockApi.createUser('서리');
  setUserId(user.user_id);
  const survey = await mockApi.getSurvey();
  const answers: Answers = Object.fromEntries(survey.questions.map((question) => [
    question.question_id,
    question.type === 'time_range' ? { bedtime: '23:00', wake: '07:00' } : question.options![0].value,
  ]));
  const persona = await mockApi.createPersona(answers);
  const candidates = (await mockApi.getCandidates(persona.persona_id)).candidates;
  const simulations = await Promise.all(candidates.slice(0, 2).map((candidate) =>
    mockApi.startSimulation(persona.persona_id, candidate.candidate_id)));
  await Promise.all(simulations.map((simulation) => new Promise<void>((resolve, reject) => {
    mockApi.subscribeSimulation(simulation.simulation_id, (event) => {
      if (event.type === 'simulation_completed') resolve();
    }, reject);
  })));
  const [first, second] = await Promise.all(simulations.map((simulation) => mockApi.createMatch(simulation.simulation_id)));
  const firstRules = await mockApi.getRules(first.match_id);
  const secondRules = await mockApi.getRules(second.match_id);
  assert.equal(firstRules.rules.length, 6);
  assert.equal(secondRules.rules.length, 6);
  assert.equal(new Set([...firstRules.rules, ...secondRules.rules].map((rule) => rule.rule_id)).size, 12);

  const proposal = await mockApi.proposeRule(secondRules.rules[0].rule_id, {
    text: '22:00부터 조용히', reason: '두 번째 매치의 시험 기간',
  });
  assert.equal(proposal.rule_id, secondRules.rules[0].rule_id);
  const accepted = await mockApi.acceptProposal(proposal.proposal_id);
  assert.equal((await mockApi.getRules(second.match_id)).rules[0].text, accepted.text);
  assert.equal((await mockApi.getRules(first.match_id)).rules[0].text, firstRules.rules[0].text);
});
