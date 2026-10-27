import { ApiError, getUserId } from '../api/real';
import { areAnswersComplete } from '../lib/survey';
import { latestCandidateSimulation } from '../lib/simulation';
import { provisionalSurvey } from './survey';
import type {
  Answers, ApiClient, Axes, Candidate, Comparison, Match, Persona, RephraseResult,
  Report, Rule, RuleProposal, RuleSet, Scene, SceneResult, Simulation, SimulationEvent,
  SimulationMode, Verdict,
} from '../api/types';

const now = () => new Date().toISOString();
const clone = <T,>(value: T): T => structuredClone(value);
const uid = () => Math.random().toString(36).slice(2, 10).padEnd(8, '0');
const requireUser = () => {
  const id = getUserId();
  if (!id) throw new ApiError(401, 'USER_REQUIRED', '사용자 정보가 없어요. 처음부터 다시 시작해 주세요.');
  return id;
};

let persona: Persona | null = null;
let currentUserNickname = '나';
const simulations = new Map<string, Simulation>();
const matches = new Map<string, Match>();
const ruleSets = new Map<string, RuleSet>();
const proposals = new Map<string, { matchId: string; value: RuleProposal }>();
const cursors = new Map<string, number>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const observers = new Map<string, Set<(event: SimulationEvent) => void>>();
const sequences = new Map<string, SimulationEvent[]>();
const STORE_KEY = 'roommate.mock.state';
try {
  const raw = typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(STORE_KEY);
  if (raw) {
    const saved = JSON.parse(raw) as {
      persona: Persona | null; nickname: string;
      simulations: Simulation[]; matches: Match[]; ruleSets: RuleSet[];
      cursors?: Array<[string, number]>;
      proposals?: Array<[string, { matchId: string; value: RuleProposal }]>;
    };
    persona = saved.persona;
    currentUserNickname = saved.nickname;
    for (const item of saved.simulations) simulations.set(item.simulation_id, item);
    for (const item of saved.matches) matches.set(item.match_id, item);
    for (const item of saved.ruleSets) ruleSets.set(item.match_id, item);
    for (const [id, cursor] of saved.cursors ?? []) cursors.set(id, cursor);
    for (const [id, proposal] of saved.proposals ?? []) proposals.set(id, proposal);
  }
} catch { /* A corrupt demo session starts empty. */ }
function persist(): void {
  if (typeof sessionStorage === 'undefined') return;
  sessionStorage.setItem(STORE_KEY, JSON.stringify({
    persona, nickname: currentUserNickname,
    simulations: [...simulations.values()], matches: [...matches.values()], ruleSets: [...ruleSets.values()],
    cursors: [...cursors], proposals: [...proposals],
  }));
}
const candidateSeed: Candidate[] = [
  { candidate_id: 'per_daeun', alias: '후보 A', department: '간호학과', year: 1, type_name: '깔끔한 집순이', pre_score: 86, highlight: '청결 기준 비슷', simulation: null },
  { candidate_id: 'per_minseo', alias: '후보 B', department: '디자인학과', year: 2, type_name: '유연한 저녁형', pre_score: 78, highlight: '대화 방식 비슷', simulation: null },
  { candidate_id: 'per_jiyun', alias: '후보 C', department: '컴퓨터공학과', year: 1, type_name: '활발한 올빼미형', pre_score: 69, highlight: '서로의 생활 존중', simulation: null },
];
const partnerNames: Record<string, string> = { per_daeun: '다은', per_minseo: '민서', per_jiyun: '지윤' };

const sceneTitles = [
  '첫날 짐 정리', '아침 알람', '책상 조명', '조용한 시간', '분리수거',
  '난방 온도', '친구 초대', '세탁 시간', '심야 게임', '아침 준비',
  '공용품 구매', '시험 공부', '식사 시간', '냉장고 반찬', '환기',
  '주말 늦잠', '청소 당번', '택배 보관', '전화 통화', '한 주 마무리',
];
const areas = ['quiet_hours', 'guests', 'cleaning', 'fridge', 'climate', 'supplies'] as const;
const areaLabels = ['조용한 시간', '친구 초대', '청소', '냉장고', '냉난방', '공용품'];
const ruleTexts = [
  '23:30 ~ 07:00', '하루 전 공지 · 주 1회 · 22시까지', '일요일 14시 · 격주 화장실 당번',
  '칸 나누기 · 공용 칸 주 1회 정리', '밤 23도 · 외출 시 끄기', '휴지·세제 번갈아 구매 · 앱 정산',
];
const ruleScenes = [4, 7, 16, 14, 6, 11];
const scoreByCandidate: Record<string, number> = { per_daeun: 88, per_minseo: 76, per_jiyun: 68 };
const candidateAxes: Record<string, Axes> = {
  per_daeun: { sleep_rhythm: 25, noise_sensitivity: 67, cleanliness: 100, sociability: 33, sharing_tolerance: 33 },
  per_minseo: { sleep_rhythm: 60, noise_sensitivity: 50, cleanliness: 68, sociability: 70, sharing_tolerance: 66 },
  per_jiyun: { sleep_rhythm: 86, noise_sensitivity: 28, cleanliness: 54, sociability: 91, sharing_tolerance: 82 },
};
/** Provisional visual values only; the monthly-conflicts formula is not approved. */
const previewMonthlyConflicts: Record<string, number> = { per_daeun: 0.5, per_minseo: 1.2, per_jiyun: 2.3 };

function findSimulation(id: string): Simulation {
  requireUser();
  const simulation = simulations.get(id);
  if (!simulation) throw new ApiError(404, 'SIMULATION_NOT_FOUND', '시뮬레이션을 찾을 수 없어요.');
  return simulation;
}

function sceneFor(index: number, alias: string): Scene {
  const day = Math.ceil(index / 3);
  return {
    scene_id: `S${String(index).padStart(2, '0')}`,
    day,
    weekday: ['월', '화', '수', '목', '금', '토', '일'][Math.min(day - 1, 6)],
    time: index === 9 ? '01:10' : index % 3 === 0 ? '22:00' : '18:30',
    category: index === 9 ? '수면·소음' : index === 14 ? '공용 공간' : '함께 사는 하루',
    title: sceneTitles[index - 1],
    situation: index === 9
      ? `${alias}가 친구와 음성 채팅으로 게임 중, 나는 내일 9시 수업이 있어요.`
      : `${alias}와 ${sceneTitles[index - 1]}에 대해 서로의 방식을 이야기해요.`,
  };
}

function verdictFor(index: number, candidateId: string): Verdict {
  if (index === 14) return 'conflict';
  if ([6, 7, 16].includes(index)) return 'negotiated';
  if (candidateId !== 'per_daeun' && index % 5 === 0) return 'negotiated';
  return 'harmonious';
}

function countsFor(candidateId: string) {
  const verdicts = Array.from({ length: 20 }, (_, i) => verdictFor(i + 1, candidateId));
  return {
    harmonious: verdicts.filter((v) => v === 'harmonious').length,
    negotiated: verdicts.filter((v) => v === 'negotiated').length,
    conflict: verdicts.filter((v) => v === 'conflict').length,
    pending: 0,
  };
}

function makeReport(simulation: Simulation): Report {
  const candidate = candidateSeed.find((item) => item.candidate_id === simulation.candidate_id)!;
  const scene_verdicts = Array.from({ length: 20 }, (_, i) => verdictFor(i + 1, simulation.candidate_id));
  return {
    simulation_id: simulation.simulation_id,
    candidate: { candidate_id: candidate.candidate_id, alias: candidate.alias, type_name: candidate.type_name },
    score: simulation.score ?? scoreByCandidate[simulation.candidate_id],
    headline: simulation.candidate_id === 'per_daeun' ? '함께 살기 무난한 조합이에요' : '대화하며 맞춰 갈 수 있어요',
    verdict_counts: countsFor(simulation.candidate_id),
    scene_verdicts,
    highlights: [14, 6, 7, 16].map((index) => ({
      scene_index: index,
      day: Math.ceil(index / 3),
      title: sceneTitles[index - 1],
      verdict: verdictFor(index, simulation.candidate_id),
      agreement: index === 14 ? '칸 나누기 + 공용 칸은 주 1회 정리' : index === 6 ? '밤 23도로 합의' : index === 7 ? '하루 전 공지, 주 1회, 22시까지' : '청소는 일요일 오후 2시',
    })),
    expected_conflicts_per_month: null,
  };
}

function rulesFor(matchId: string): RuleSet {
  const rules: Rule[] = areas.map((area, i) => ({
    rule_id: `rul_${matchId}_${i + 1}`,
    area,
    area_label: areaLabels[i],
    text: ruleTexts[i],
    source: { scene_index: ruleScenes[i], day: Math.ceil(ruleScenes[i] / 3), verdict: verdictFor(ruleScenes[i], 'per_daeun') },
  }));
  return { match_id: matchId, status: 'draft', rules, agreements: { me: false, partner: false } };
}

function mockEvents(simulation: Simulation): SimulationEvent[] {
  const candidate = candidateSeed.find((item) => item.candidate_id === simulation.candidate_id)!;
  const events: SimulationEvent[] = [{
    id: '0-0', type: 'simulation_started', data: {
      simulation_id: simulation.simulation_id, mode: simulation.mode, total_scenes: 20,
      me: { name: `${persona?.nickname ?? '나'} AI`, type_name: persona?.type_name ?? '생활 페르소나' },
      candidate: { alias: candidate.alias, type_name: candidate.type_name },
    },
  }];
  for (let index = 1; index <= 20; index++) {
    const verdict = verdictFor(index, simulation.candidate_id);
    events.push({ id: `${index}-0`, type: 'scene_started', data: { scene_index: index, scene: sceneFor(index, candidate.alias) } });
    events.push({ id: `${index}-1`, type: 'utterance', data: {
      scene_index: index, turn: 1, speaker: 'me', name: `${persona?.nickname ?? '나'} AI`,
      text: index === 9 ? '내일 아침 수업이라 이제 자야 할 것 같아. 조금만 작게 해줄 수 있어?' : '우리 생활 방식은 어떻게 맞추면 좋을까?',
    } });
    events.push({ id: `${index}-2`, type: 'utterance', data: {
      scene_index: index, turn: 2, speaker: 'candidate', name: `${candidate.alias} AI`,
      text: index === 9 ? '미안해! 헤드셋을 쓰고 소리를 줄일게.' : '좋아. 서로 편한 방법을 찾아보자!',
    } });
    events.push({ id: `${index}-3`, type: 'scene_judged', data: {
      scene_index: index, verdict,
      reason: verdict === 'conflict' ? '생활 방식 차이가 남았어요.' : '서로의 방식을 확인했어요.',
      agreement: verdict === 'conflict' ? '각자 사용할 공간을 나눠요.' : '서로 미리 이야기하기로 해요.',
      rule_candidate: index === 9 ? { area: 'quiet_hours', text: '평일 24시 이후 헤드셋 사용' } : null,
      unresolved: null, progress: { done: index, total: 20 },
    } });
  }
  events.push({ id: '20-4', type: 'simulation_completed', data: {
    score: scoreByCandidate[simulation.candidate_id], headline: '함께 살기 무난한 조합이에요',
    verdict_counts: countsFor(simulation.candidate_id),
  } });
  return events;
}

function eventSequence(simulation: Simulation): SimulationEvent[] {
  let events = sequences.get(simulation.simulation_id);
  if (!events) {
    events = mockEvents(simulation);
    sequences.set(simulation.simulation_id, events);
  }
  return events;
}

function completedScenes(simulation: Simulation): SceneResult[] {
  const events = eventSequence(simulation);
  return Array.from({ length: 20 }, (_, offset) => {
    const scene_index = offset + 1;
    const started = events.find((event) => event.type === 'scene_started' && event.data.scene_index === scene_index);
    const judged = events.find((event) => event.type === 'scene_judged' && event.data.scene_index === scene_index);
    if (!started || started.type !== 'scene_started' || !judged || judged.type !== 'scene_judged') {
      throw new Error(`장면 ${scene_index}의 mock 이벤트가 누락됐어요.`);
    }
    const dialogue = events
      .filter((event) => event.type === 'utterance' && event.data.scene_index === scene_index)
      .map((event) => {
        if (event.type !== 'utterance') throw new Error('잘못된 mock 발화예요.');
        const { turn, speaker, name, text } = event.data;
        return { turn, speaker, name, text };
      });
    const { verdict, reason, agreement, rule_candidate, unresolved } = judged.data;
    return { scene_index, scene: started.data.scene, dialogue, verdict, reason, agreement, rule_candidate, unresolved };
  });
}

/** The demo engine runs independently of any B2 view/SSE observer. */
function ensureRunning(simulation: Simulation): void {
  const id = simulation.simulation_id;
  if (simulation.status === 'completed' || simulation.status === 'failed' || timers.has(id)) return;
  const events = eventSequence(simulation);
  if (!cursors.has(id)) cursors.set(id, simulation.progress.done === 0 ? 0 : 1 + simulation.progress.done * 4);
  const tick = () => {
    timers.delete(id);
    const cursor = cursors.get(id) ?? 0;
    const event = events[cursor];
    if (!event) return;
    if (simulation.status !== 'completed') simulation.status = 'running';
    if (event.type === 'scene_judged' && event.data.progress.done > simulation.progress.done) {
      simulation.progress = event.data.progress;
      simulation.verdict_counts[event.data.verdict]++;
    }
    if (event.type === 'simulation_completed') {
      simulation.status = 'completed';
      simulation.score = event.data.score;
      simulation.verdict_counts = event.data.verdict_counts;
      simulation.completed_at = now();
    }
    cursors.set(id, cursor + 1);
    persist();
    if (simulation.status !== 'completed') timers.set(id, setTimeout(tick, 55));
    for (const observer of observers.get(id) ?? []) observer(clone(event));
  };
  timers.set(id, setTimeout(tick, 70));
}

export const mockApi: ApiClient = {
  async createUser(nickname) {
    if (nickname.trim().length < 1 || nickname.trim().length > 10) throw new ApiError(422, 'VALIDATION_ERROR', '닉네임은 1~10자로 입력해 주세요.');
    currentUserNickname = nickname.trim();
    for (const timer of timers.values()) clearTimeout(timer);
    timers.clear(); observers.clear(); sequences.clear(); cursors.clear();
    persona = null; simulations.clear(); matches.clear(); ruleSets.clear(); proposals.clear(); persist();
    return { user_id: `usr_${uid()}`, nickname: nickname.trim(), created_at: now() };
  },
  async getSurvey() { return clone(provisionalSurvey); },
  async createPersona(answers: Answers) {
    const userId = requireUser();
    if (!areAnswersComplete(provisionalSurvey.questions, answers)) throw new ApiError(400, 'SURVEY_INCOMPLETE', '12문항을 모두 답해 주세요.');
    persona = {
      persona_id: `per_${uid()}`, user_id: userId, nickname: currentUserNickname,
      type_name: '규칙적인 아침형', summary: '일찍 잠들고 생활 공간을 깔끔하게 유지해요. 불편하면 부드럽게 이야기하는 편이에요.',
      sleep: { bedtime: (answers.q01 as Record<string, string>).bedtime, wake: (answers.q01 as Record<string, string>).wake, exam_pattern: answers.q03 as string },
      axes: { sleep_rhythm: 33, noise_sensitivity: 67, cleanliness: 84, sociability: 33, sharing_tolerance: 0 },
      axis_labels: { sleep_rhythm: '아침형', noise_sensitivity: '예민', cleanliness: '높음', sociability: '보통', sharing_tolerance: '낮음' },
      conflict_style: 'direct', preferences: { temperature: answers.q06 as string },
      must_keep: ['24시 이후 통화·게임 소리 X'], okay_with: ['친구 초대 (미리 말하면)'],
      is_seed: false, created_at: now(),
    };
    persist();
    return clone(persona);
  },
  async getPersona(id) {
    requireUser();
    if (!persona || persona.persona_id !== id) throw new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
    return clone(persona);
  },
  async patchPersona(id, changes) {
    requireUser();
    if (!persona || persona.persona_id !== id) throw new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
    if ([...changes.must_keep, ...changes.okay_with].some((item) => item.length > 30) || changes.must_keep.length > 3 || changes.okay_with.length > 3)
      throw new ApiError(422, 'VALIDATION_ERROR', '각 목록은 최대 3개, 항목은 30자 이하로 입력해 주세요.');
    persona = { ...persona, ...changes };
    persist();
    return clone(persona);
  },
  async getCandidates(id) {
    requireUser();
    if (!persona || persona.persona_id !== id) throw new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
    for (const simulation of simulations.values()) ensureRunning(simulation);
    return { candidates: clone(candidateSeed.map((candidate) => {
      const simulation = latestCandidateSimulation(simulations.values(), id, candidate.candidate_id);
      return {
        ...candidate,
        simulation: simulation
          ? { simulation_id: simulation.simulation_id, status: simulation.status, progress: simulation.progress, score: simulation.score }
          : null,
      };
    })) };
  },
  async startSimulation(personaId, candidateId, mode: SimulationMode = 'live') {
    requireUser();
    if (!persona || persona.persona_id !== personaId) throw new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
    if (!candidateSeed.some((candidate) => candidate.candidate_id === candidateId)) throw new ApiError(404, 'PERSONA_NOT_FOUND', '후보를 찾을 수 없어요.');
    const existing = [...simulations.values()].find((item) =>
      item.persona_id === personaId && item.candidate_id === candidateId && item.mode === mode && item.status !== 'failed');
    if (existing) { ensureRunning(existing); return clone(existing); }
    const simulation: Simulation = {
      simulation_id: `sim_${uid()}`, persona_id: personaId, candidate_id: candidateId,
      mode, status: 'queued', progress: { done: 0, total: 20 },
      verdict_counts: { harmonious: 0, negotiated: 0, conflict: 0, pending: 0 },
      score: null, started_at: now(), completed_at: null,
    };
    simulations.set(simulation.simulation_id, simulation);
    cursors.set(simulation.simulation_id, 0);
    persist();
    ensureRunning(simulation);
    return clone(simulation);
  },
  async getSimulation(id) {
    const simulation = findSimulation(id);
    ensureRunning(simulation);
    return clone(simulation);
  },
  async getReport(id) {
    const simulation = findSimulation(id);
    if (simulation.status !== 'completed') throw new ApiError(409, 'SIMULATION_NOT_COMPLETED', '시뮬레이션이 아직 끝나지 않았어요.');
    return clone(makeReport(simulation));
  },
  async getScenes(id) {
    const simulation = findSimulation(id);
    if (simulation.status !== 'completed') throw new ApiError(409, 'SIMULATION_NOT_COMPLETED', '시뮬레이션이 아직 끝나지 않았어요.');
    return { scenes: clone(completedScenes(simulation)) };
  },
  async getComparison(personaId): Promise<Comparison> {
    requireUser();
    if (!persona || persona.persona_id !== personaId) throw new ApiError(404, 'PERSONA_NOT_FOUND', '페르소나를 찾을 수 없어요.');
    const candidates = candidateSeed.map((candidate) => {
      const simulation = latestCandidateSimulation(simulations.values(), personaId, candidate.candidate_id);
      return {
        candidate_id: candidate.candidate_id,
        alias: candidate.alias,
        axes: candidateAxes[candidate.candidate_id],
        score: simulation?.score ?? candidate.pre_score,
        // Keep the unapproved P1 metric unknown until the mock simulation completed.
        expected_conflicts_per_month: simulation?.status === 'completed'
          ? previewMonthlyConflicts[candidate.candidate_id]
          : null,
      };
    });
    return clone({ me: { axes: persona.axes }, candidates, recommended_candidate_id: candidates[0].candidate_id });
  },
  async createMatch(id) {
    const simulation = findSimulation(id);
    if (simulation.status !== 'completed') throw new ApiError(409, 'SIMULATION_NOT_COMPLETED', '시뮬레이션이 아직 끝나지 않았어요.');
    const existing = [...matches.values()].find((item) => item.simulation_id === id);
    if (existing) return clone(existing);
    const candidate = candidateSeed.find((item) => item.candidate_id === simulation.candidate_id)!;
    const match: Match = {
      match_id: `mat_${uid()}`, simulation_id: id, status: 'accepted',
      partner: {
        persona_id: candidate.candidate_id, name: partnerNames[candidate.candidate_id],
        department: candidate.department, year: candidate.year, type_name: candidate.type_name,
        greeting: '함께 지낼 수 있게 되어 반가워요! 서로 편한 방식을 찾아가요 🙂',
      },
      room: '302호 (배정 예정)', rules_status: 'draft',
    };
    matches.set(match.match_id, match);
    ruleSets.set(match.match_id, rulesFor(match.match_id));
    persist();
    return clone(match);
  },
  async getMatch(id) {
    requireUser();
    const match = matches.get(id);
    if (!match) throw new ApiError(404, 'MATCH_NOT_FOUND', '매칭을 찾을 수 없어요.');
    return clone(match);
  },
  async getRules(id) {
    requireUser();
    const rules = ruleSets.get(id);
    if (!rules) throw new ApiError(404, 'MATCH_NOT_FOUND', '생활 규칙을 찾을 수 없어요.');
    return clone(rules);
  },
  async agreeRules(id) {
    requireUser();
    const rules = ruleSets.get(id);
    if (!rules) throw new ApiError(404, 'MATCH_NOT_FOUND', '생활 규칙을 찾을 수 없어요.');
    rules.agreements = { me: true, partner: true };
    rules.status = 'confirmed';
    const match = matches.get(id);
    if (match) match.rules_status = 'confirmed';
    persist();
    return clone(rules);
  },
  async proposeRule(ruleId, proposal) {
    requireUser();
    const entry = [...ruleSets.entries()].find(([, set]) => set.rules.some((rule) => rule.rule_id === ruleId));
    if (!entry) throw new ApiError(404, 'RULE_NOT_FOUND', '생활 규칙을 찾을 수 없어요.');
    if (!proposal.text.trim() || !proposal.reason.trim()) throw new ApiError(422, 'VALIDATION_ERROR', '변경할 규칙과 이유를 입력해 주세요.');
    const value: RuleProposal = {
      proposal_id: `prp_${uid()}`,
      rule_id: ruleId,
      mediation: {
        text: `${proposal.text.trim()}, 대신 서로 미리 알려 주기`,
        rationale: [proposal.reason.trim(), '서로의 수면·생활 패턴을 함께 고려했어요.'],
      },
    };
    proposals.set(value.proposal_id, { matchId: entry[0], value });
    persist();
    return clone(value);
  },
  async acceptProposal(proposalId) {
    requireUser();
    const entry = proposals.get(proposalId);
    if (!entry) throw new ApiError(404, 'RULE_NOT_FOUND', '수정 제안을 찾을 수 없어요.');
    const set = ruleSets.get(entry.matchId);
    const rule = set?.rules.find((item) => item.rule_id === entry.value.rule_id);
    if (!set || !rule) throw new ApiError(404, 'RULE_NOT_FOUND', '생활 규칙을 찾을 수 없어요.');
    rule.text = entry.value.mediation.text;
    proposals.delete(proposalId);
    persist();
    return clone(rule);
  },
  async rephraseMemo(matchId, memo): Promise<RephraseResult> {
    requireUser();
    if (!matches.has(matchId)) throw new ApiError(404, 'MATCH_NOT_FOUND', '매칭을 찾을 수 없어요.');
    if (!memo.trim()) throw new ApiError(422, 'VALIDATION_ERROR', '불편한 점을 적어 주세요.');
    // Never store or echo the private raw memo. The P1 API only returns a draft,
    // and has no send-to-partner endpoint.
    let draft: RephraseResult;
    if (/청소|분리수거|쓰레기/.test(memo)) {
      draft = {
        message: '공용 공간을 함께 정리하면 좋겠어. 정해 둔 청소 시간에 같이 확인해 줄 수 있을까?',
        suggested_rule: { area: 'cleaning', text: '일요일마다 공용 공간 청소 상태 확인' },
      };
    } else if (/친구|초대|손님/.test(memo)) {
      draft = {
        message: '친구가 방문할 때 미리 알려 주면 준비하기 좋을 것 같아. 하루 전에 이야기해 줄 수 있을까?',
        suggested_rule: { area: 'guests', text: '친구 방문은 하루 전 공유' },
      };
    } else if (/알람|다시\s*알림|기상음/.test(memo)) {
      draft = {
        message: '요즘 아침 알람 소리에 같이 깨더라. 진동으로 바꾸거나 다시 알림을 한 번만 사용할 수 있을까?',
        suggested_rule: { area: 'quiet_hours', text: '평일 알람은 진동 · 다시 알림 1회까지' },
      };
    } else {
      throw new ApiError(422, 'MOCK_TOPIC_UNSUPPORTED', '이 주제는 아직 mock 문장 변환을 지원하지 않아요.');
    }
    return clone(draft);
  },
  subscribeSimulation(id, onEvent, onError) {
    let stopped = false;
    let simulation: Simulation;
    try { simulation = findSimulation(id); } catch (error) {
      queueMicrotask(() => onError(error instanceof Error ? error : new Error('시뮬레이션을 찾을 수 없어요.')));
      return () => { stopped = true; };
    }
    ensureRunning(simulation);
    queueMicrotask(() => {
      if (stopped) return;
      for (const event of eventSequence(simulation).slice(0, cursors.get(id) ?? 0)) {
        if (stopped) break;
        onEvent(clone(event));
      }
      if (!stopped && simulation.status !== 'completed') {
        const set = observers.get(id) ?? new Set();
        set.add(onEvent);
        observers.set(id, set);
      }
    });
    return () => {
      stopped = true;
      const set = observers.get(id);
      set?.delete(onEvent);
      if (set?.size === 0) observers.delete(id);
    };
  },
};
