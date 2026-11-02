import { Fragment, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ApiError, api, getUserId, setUserId } from './api';
import type { Answers, Candidate, Diagnosis, Match, PassSummary, Persona, Report, RuleSet, Scene, Simulation, SurveyQuestion, Utterance, Verdict } from './api/types';
import { AppShell } from './components/Shell';
import { Icon } from './components/Icon';
import type { AppTab } from './components/Shell';
import { areAnswersComplete, isAnswerComplete } from './lib/survey';
import { isCurrentSimulation, mergeSimulation } from './features/flowState';
import { simulationStartErrorText } from './lib/simulationError';
import { withSessionSimulation } from './lib/candidateOverlay';
import { ComparisonScreen, MemoScreen, RuleProposalScreen, SceneReplayScreen } from './features/P1Screens';
import { PlansScreen } from './features/PlansScreen';
import { DiagnosisScreen } from './features/DiagnosisScreen';
import { CandidateCard, displayedScore } from './features/CandidateCard';
import { DayChips, TypingBubble, useChatPlayback } from './features/ChatPlayback';
import { AdminScreen, AxisPreviewEditor, CheckinScreen, DemoMenuScreen, RoomScreen } from './features/P2Screens';
import './features/flow.css';
import './features/extras.css';

type Step = 'start' | 'survey' | 'persona' | 'candidates' | 'simulation' | 'report' | 'match' | 'rules' | 'comparison' | 'sceneReplay' | 'ruleProposal' | 'room' | 'memo' | 'checkin' | 'admin' | 'more' | 'plans' | 'diagnosis';
type SceneView = { index: number; scene?: Scene; turns: Utterance[]; verdict?: Verdict; reason?: string; agreement?: string | null; rule?: string | null; unresolved?: string | null };
type Saved = { step: Step; nickname: string; personaId?: string; simulationId?: string; candidateId?: string; candidateAlias?: string; matchId?: string; ruleId?: string; questionIndex: number; answers: Answers };
const STORAGE_KEY = 'roommate:p0-flow';
const EMPTY: Saved = { step: 'start', nickname: '', questionIndex: 0, answers: {} };
const isMock = import.meta.env.VITE_USE_MOCK === 'true';
const allSteps: Step[] = ['start', 'survey', 'persona', 'candidates', 'simulation', 'report', 'match', 'rules', 'comparison', 'sceneReplay', 'ruleProposal', 'room', 'memo', 'checkin', 'admin', 'more', 'plans', 'diagnosis'];
// P2(우리 방 · 체크인 · 관리자)는 발표회 범위 밖: 실서버 모드에서는 숨김
const mockOnlySteps: Step[] = ['room', 'checkin', 'admin', 'more'];
const axisNames: Record<keyof Persona['axes'], string> = { sleep_rhythm: '수면 리듬', noise_sensitivity: '소음 민감', cleanliness: '청결', sociability: '사교성', sharing_tolerance: '공유 관대' };

function readSaved(): Saved {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    const saved = raw ? JSON.parse(raw) as Partial<Saved> : null;
    if (!saved || !getUserId()) return EMPTY;
    const restored = { ...EMPTY, ...saved, answers: saved.answers ?? {} };
    if (!allSteps.includes(restored.step)) restored.step = 'start';
    if (!isMock && mockOnlySteps.includes(restored.step)) restored.step = restored.matchId ? 'rules' : 'start';
    return restored;
  } catch { return EMPTY; }
}

function restartExperience() {
  sessionStorage.clear();
  window.location.reload();
}

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  return '요청에 실패했어요. 다시 시도해 주세요.';
}

function timeOptions(min: string, max: string, step: number): string[] {
  const toMinutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
  const start = toMinutes(min);
  let end = toMinutes(max);
  if (end < start) end += 1440;
  const result: string[] = [];
  for (let current = start; current <= end; current += Math.max(step, 1)) {
    const minute = current % 1440;
    result.push(`${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`);
  }
  return result;
}

function supportsReplay(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 429 || error.status === 503);
}

function completedWithReport(current: Simulation | null, result: Report): Simulation | null {
  return current?.simulation_id === result.simulation_id
    ? { ...current, status: 'completed', score: result.score, progress: { done: 20, total: 20 } }
    : current;
}

const verdictLabels: Record<Verdict, string> = { harmonious: '원만', negotiated: '조율', conflict: '충돌', pending: '판정 보류' };

function Button({ children, onClick, disabled, secondary = false, type = 'button' }: { children: React.ReactNode; onClick?: () => void; disabled?: boolean; secondary?: boolean; type?: 'button' | 'submit' }) {
  return <button type={type} className={`flow-button ${secondary ? 'flow-button--secondary' : ''}`} onClick={onClick} disabled={disabled}>{children}</button>;
}

function Notice({ children, tone = 'info' }: { children: React.ReactNode; tone?: 'info' | 'error' | 'warm' }) {
  return <div className={`flow-notice flow-notice--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>{children}</div>;
}

function Footer({ children }: { children: React.ReactNode }) { return <div className="flow-footer">{children}</div>; }

function SurveyCard({ question, answer, onAnswer }: { question: SurveyQuestion; answer: Answers[string] | undefined; onAnswer: (value: Answers[string]) => void }) {
  return <section className="flow-card flow-question">
    <div className="flow-kicker">{question.section === 'life' ? '나의 생활 습관' : '이럴 땐 어떻게 할까요?'}</div>
    <h2>{question.title}</h2>
    {question.hint && <p className="flow-muted">{question.hint}</p>}
    {question.type === 'time_range' ? <div className="flow-time-fields">{(question.fields ?? []).map(field => {
      const selected = typeof answer === 'object' && answer ? answer[field.key] : field.default;
      return <label className="flow-time-field" key={field.key}><span>{field.label}</span><select value={selected} onChange={event => onAnswer({ ...(typeof answer === 'object' ? answer : {}), [field.key]: event.target.value })}>{timeOptions(field.min, field.max, field.step_minutes).map(value => <option key={value} value={value}>{value}</option>)}</select></label>;
    })}</div> : <div className="flow-options" role="radiogroup" aria-label={question.title}>{(question.options ?? []).map(option => <label className={`flow-option ${answer === option.value ? 'is-selected' : ''}`} key={option.value}><input type="radio" name={question.question_id} value={option.value} checked={answer === option.value} onChange={() => onAnswer(option.value)} /><span>{option.label}</span><span className="flow-option-check" aria-hidden="true">{answer === option.value ? '✓' : ''}</span></label>)}</div>}
  </section>;
}

function SceneBars({ values, done = 0 }: { values?: Array<Verdict | undefined>; done?: number }) {
  return <div className="flow-scene-bars" aria-label={`20개 장면 중 ${done}개 완료`}>{Array.from({ length: 20 }, (_, i) => <span key={i} className={`flow-scene-bar ${values?.[i] ? `is-${values[i]}` : i < done ? 'is-progress' : ''}`} />)}</div>;
}

function ScoreRing({ score }: { score: number }) {
  return <div className="flow-score-ring" style={{ '--score': `${score}%` } as React.CSSProperties}><strong>{score}<small>점</small></strong></div>;
}

function App() {
  const [saved, setSaved] = useState<Saved>(readSaved);
  const [questions, setQuestions] = useState<SurveyQuestion[]>([]);
  const [persona, setPersona] = useState<Persona | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [scenes, setScenes] = useState<SceneView[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [rules, setRules] = useState<RuleSet | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [mustText, setMustText] = useState('');
  const [okayText, setOkayText] = useState('');
  const [degraded, setDegraded] = useState(false);
  const [replayTargetId, setReplayTargetId] = useState<string | null>(null);
  const [axisPreviewOpen, setAxisPreviewOpen] = useState(false);
  const seenEvents = useRef(new Set<string>());
  const sceneEndRef = useRef<HTMLDivElement>(null);
  const activeSimulationId = useRef<string | null>(saved.simulationId ?? null);
  const activePersonaId = useRef<string | null>(saved.personaId ?? null);
  const simulationSnapshot = useRef<Simulation | null>(null);
  const candidateRequest = useRef(0);
  const comparisonRequest = useRef(0);
  const activeStep = useRef<Step>(saved.step);

  const step = saved.step;
  const update = useCallback((patch: Partial<Saved>) => {
    if (patch.step && patch.step !== activeStep.current) {
      if (activeStep.current === 'comparison') { comparisonRequest.current += 1; setBusy(false); }
      activeStep.current = patch.step;
    }
    if ('simulationId' in patch) activeSimulationId.current = patch.simulationId ?? null;
    if ('personaId' in patch) activePersonaId.current = patch.personaId ?? null;
    setSaved(current => ({ ...current, ...patch }));
  }, []);
  useEffect(() => { activeSimulationId.current = saved.simulationId ?? null; activePersonaId.current = saved.personaId ?? null; }, [saved.simulationId, saved.personaId]);
  useEffect(() => { simulationSnapshot.current = simulation; }, [simulation]);
  useLayoutEffect(() => {
    const content = document.querySelector<HTMLElement>('.app-content');
    // 진행 중인 부드러운 자동 스크롤까지 멈추고 새 화면은 맨 위에서 시작
    if (content) content.scrollTo({ top: 0, behavior: 'instant' });
  }, [step, saved.questionIndex]);
  useEffect(() => { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saved)); }, [saved]);
  useEffect(() => { setError(''); }, [step]);
  // B2: 받은 대화를 메신저처럼 천천히 표시. 이미 끝난 실행을 다시 열면 즉시 전부 표시
  const [replayInstant, setReplayInstant] = useState(false);
  useEffect(() => {
    if (step !== 'simulation') return;
    const snapshot = simulationSnapshot.current;
    setReplayInstant(Boolean(snapshot && snapshot.simulation_id === saved.simulationId && snapshot.status === 'completed'));
  }, [step, saved.simulationId]);
  const playback = useChatPlayback(scenes, { instant: replayInstant || step !== 'simulation', resetKey: `${saved.simulationId ?? ''}:${step === 'simulation'}` });
  // 새로고침 등으로 늦게 받은 실행이 이미 끝났다면(아직 아무것도 표시 전) 천천히 재생하지 않고 바로 전부 표시
  useEffect(() => {
    if (step === 'simulation' && simulation?.simulation_id === saved.simulationId && simulation?.status === 'completed' && playback.shownCount === 0) setReplayInstant(true);
  }, [step, simulation?.simulation_id, simulation?.status, saved.simulationId, playback.shownCount]);
  // 새 발화를 따라 내려가되, 사용자가 위로 올려 읽는 중이면 끌어내리지 않음
  const stickToBottom = useRef(true);
  const autoScrollUntil = useRef(0);
  const [following, setFollowing] = useState(true);
  useEffect(() => {
    if (step !== 'simulation') return;
    const content = document.querySelector<HTMLElement>('.app-content');
    if (!content) return;
    stickToBottom.current = true;
    setFollowing(true);
    const onScroll = () => {
      if (Date.now() < autoScrollUntil.current) return;
      stickToBottom.current = content.scrollHeight - content.scrollTop - content.clientHeight < 140;
      setFollowing(stickToBottom.current);
    };
    content.addEventListener('scroll', onScroll, { passive: true });
    return () => content.removeEventListener('scroll', onScroll);
  }, [step]);
  useEffect(() => {
    if (step !== 'simulation' || degraded || !stickToBottom.current) return;
    autoScrollUntil.current = Date.now() + 700;
    sceneEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [playback.shownCount, playback.typing, degraded, step]);
  function scrollToLatest() {
    stickToBottom.current = true;
    setFollowing(true);
    autoScrollUntil.current = Date.now() + 700;
    sceneEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }
  function jumpToDay(day: number) {
    stickToBottom.current = false;
    setFollowing(false);
    autoScrollUntil.current = 0;
    document.getElementById(`sim-day-${day}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  const candidatesFetchedAt = useRef(0);
  const [candidatesLoaded, setCandidatesLoaded] = useState(false);
  const [passes, setPasses] = useState<PassSummary | null>(null);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [passRequired, setPassRequired] = useState(false);
  const candidatesRef = useRef<Candidate[]>([]);
  useEffect(() => { candidatesRef.current = candidates; }, [candidates]);
  const refreshCandidates = useCallback(async (personaId: string) => {
    const request = ++candidateRequest.current;
    candidatesFetchedAt.current = Date.now();
    const response = await api.getCandidates(personaId);
    if (activePersonaId.current === personaId && request === candidateRequest.current) { setCandidates(response.candidates); setCandidatesLoaded(true); }
  }, []);

  useEffect(() => {
    let active = true;
    async function restore() {
      if (step === 'start') return;
      setLoading(true);
      try {
        // 화면 전환 시 이미 받은 데이터는 다시 요청하지 않음 (새로고침 복원 시에만 조회)
        if (step === 'survey' && questions.length === 0) { const data = await api.getSurvey(); if (active) setQuestions(data.questions); }
        if (saved.personaId && persona?.persona_id !== saved.personaId && ['persona', 'candidates', 'simulation', 'report', 'match', 'rules', 'comparison', 'sceneReplay', 'ruleProposal', 'room', 'memo', 'checkin'].includes(step)) {
          const data = await api.getPersona(saved.personaId); if (active) setPersona(data);
        }
        // 후보 목록(B1)은 아래 폴링 효과가 조회. 다른 화면은 후보 별칭 표시용으로 비어 있을 때만 조회
        if (saved.personaId && candidates.length === 0 && (step === 'simulation' || step === 'report' || step === 'comparison')) {
          try { await refreshCandidates(saved.personaId); }
          catch (cause) { if (active) setError(errorText(cause)); }
        }
        if ((step === 'candidates' || step === 'simulation' || step === 'report' || step === 'sceneReplay') && saved.simulationId && simulationSnapshot.current?.simulation_id !== saved.simulationId) {
          const data = await api.getSimulation(saved.simulationId);
          if (active && activeSimulationId.current === saved.simulationId) setSimulation(current => mergeSimulation(current, data));
        }
        if ((step === 'report' || step === 'sceneReplay') && saved.simulationId && report?.simulation_id !== saved.simulationId) {
          const data = await api.getReport(saved.simulationId);
          if (active && activeSimulationId.current === saved.simulationId) {
            setReport(data);
            setSimulation(current => completedWithReport(current, data));
          }
        }
        if (['match', 'rules', 'ruleProposal', 'room', 'memo', 'checkin'].includes(step) && saved.matchId && match?.match_id !== saved.matchId) { const data = await api.getMatch(saved.matchId); if (active) setMatch(data); }
        if ((step === 'rules' || step === 'ruleProposal') && saved.matchId && rules?.match_id !== saved.matchId) { const data = await api.getRules(saved.matchId); if (active) setRules(data); }
      } catch (cause) { if (active) setError(errorText(cause)); }
      finally { if (active) setLoading(false); }
    }
    void restore();
    return () => { active = false; };
  }, [step, saved.personaId, saved.simulationId, saved.matchId, refreshCandidates]);

  const orderedQuestions = useMemo(() => [...questions.filter(q => q.section === 'life'), ...questions.filter(q => q.section === 'situation')], [questions]);
  // Candidate cards currently return simulation:null; restore only the selected
  // run in this session after GET /simulations/{id} confirms its owner and IDs.
  const visibleCandidates = useMemo(() => withSessionSimulation(candidates, simulation, saved),
    [candidates, simulation, saved]);
  const question = orderedQuestions[saved.questionIndex];
  const allAnswered = areAnswersComplete(orderedQuestions, saved.answers);

  useEffect(() => {
    if (!question || question.type !== 'time_range' || saved.answers[question.question_id]) return;
    const defaults = Object.fromEntries((question.fields ?? []).map(field => [field.key, field.default]));
    update({ answers: { ...saved.answers, [question.question_id]: defaults } });
  }, [question, saved.answers, update]);

  async function start() {
    const nickname = saved.nickname.trim();
    if (nickname.length < 1 || nickname.length > 10 || busy) return;
    setBusy(true); setError('');
    try {
      const user = await api.createUser(nickname);
      setUserId(user.user_id);
      const survey = await api.getSurvey();
      setQuestions(survey.questions);
      update({ nickname: user.nickname, step: 'survey', questionIndex: 0, answers: {} });
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  function setAnswer(value: Answers[string]) {
    if (!question) return;
    update({ answers: { ...saved.answers, [question.question_id]: value } });
  }

  async function advanceSurvey() {
    if (!question || !isAnswerComplete(question, saved.answers[question.question_id]) || busy) return;
    if (saved.questionIndex < orderedQuestions.length - 1) { update({ questionIndex: saved.questionIndex + 1 }); return; }
    if (!allAnswered) { setError('모든 질문에 답한 뒤 페르소나를 만들 수 있어요.'); return; }
    setBusy(true); setError('');
    try {
      const result = await api.createPersona(saved.answers);
      setPersona(result);
      setMustText(result.must_keep.join('\n')); setOkayText(result.okay_with.join('\n'));
      update({ step: 'persona', personaId: result.persona_id });
    } catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function savePersona() {
    if (!persona || busy) return;
    const parse = (text: string) => text.split('\n').map(item => item.trim()).filter(Boolean);
    const must_keep = parse(mustText), okay_with = parse(okayText);
    if ([must_keep, okay_with].some(items => items.length > 3 || items.some(item => item.length > 30))) { setError('각 목록은 최대 3개, 항목당 30자 이내로 입력해 주세요.'); return; }
    setBusy(true); setError('');
    try { const result = await api.patchPersona(persona.persona_id, { must_keep, okay_with }); setPersona(result); setEditing(false); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function showCandidates() {
    if (!persona || busy) return;
    setBusy(true); setError('');
    try { await refreshCandidates(persona.persona_id); update({ step: 'candidates' }); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (step !== 'candidates' || !saved.personaId) return;
    let active = true;
    void api.getPasses().then(value => { if (active) setPasses(value); }).catch(() => undefined);
    void api.getDiagnosis(saved.personaId).then(value => { if (active) setDiagnosis(value); }).catch(() => undefined);
    return () => { active = false; };
  }, [step, saved.personaId]);

  async function selectCandidate(candidate: Candidate) {
    if (!persona || busy) return;
    const from = activeStep.current;
    setBusy(true); setError('');
    const hasActiveSimulation = !!candidate.simulation && candidate.simulation.status !== 'failed';
    setPassRequired(false);
    try {
      const result = hasActiveSimulation
        ? await api.getSimulation(candidate.simulation!.simulation_id)
        : await api.startSimulation(persona.persona_id, candidate.candidate_id);
      if (activeStep.current !== from) return;
      simulationSnapshot.current = result;
      setSimulation(result); setReport(null); setScenes([]); seenEvents.current.clear(); setDegraded(false); setReplayTargetId(null);
      update({ candidateId: candidate.candidate_id, candidateAlias: candidate.alias, simulationId: result.simulation_id, step: result.status === 'completed' ? 'report' : 'simulation' });
    } catch (cause) {
      if (cause instanceof ApiError && cause.code === 'PASS_REQUIRED') { setPassRequired(true); return; }
      setError(hasActiveSimulation ? errorText(cause) : simulationStartErrorText(cause, isMock));
      if (supportsReplay(cause)) setReplayTargetId(candidate.candidate_id);
    }
    finally { setBusy(false); }
  }

  async function retrySimulation(mode: 'live' | 'replay') {
    const candidateId = replayTargetId ?? saved.candidateId;
    if (!persona || !candidateId || busy) return;
    setBusy(true); setError('');
    try {
      const result = await api.startSimulation(persona.persona_id, candidateId, mode);
      simulationSnapshot.current = result;
      setSimulation(result); setReport(null); setScenes([]); seenEvents.current.clear(); setDegraded(false); setReplayTargetId(null);
      const alias = candidates.find(item => item.candidate_id === candidateId)?.alias ?? saved.candidateAlias;
      update({ candidateId, candidateAlias: alias, simulationId: result.simulation_id, step: result.status === 'completed' ? 'report' : 'simulation' });
    } catch (cause) { setError(simulationStartErrorText(cause, isMock)); if (supportsReplay(cause)) setReplayTargetId(candidateId); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (step !== 'candidates' || !saved.personaId) return;
    const personaId = saved.personaId;
    const id = saved.simulationId;
    const inProgress = (status?: Simulation['status']) => status === 'queued' || status === 'running';
    // 진입 시 1회 조회, 이후에는 진행 중인 시뮬레이션이 있을 때만 2초 간격 갱신
    const refresh = (initial: boolean) => {
      const sessionRunning = Boolean(id && (simulationSnapshot.current?.simulation_id !== id || inProgress(simulationSnapshot.current.status)));
      const anyRunning = sessionRunning || candidatesRef.current.some(candidate => inProgress(candidate.simulation?.status));
      const justFetched = Date.now() - candidatesFetchedAt.current < 1500;
      if (initial ? !justFetched : anyRunning) void refreshCandidates(personaId).catch(cause => setError(errorText(cause)));
      if (sessionRunning && id) {
        void api.getSimulation(id).then(result => {
          if (activeStep.current === 'candidates' && activeSimulationId.current === id) {
            setSimulation(current => mergeSimulation(current, result));
          }
        }).catch(cause => {
          if (activeStep.current !== 'candidates' || activeSimulationId.current !== id) return;
          if (cause instanceof ApiError && cause.status === 404) {
            setSimulation(current => current?.simulation_id === id ? null : current);
            simulationSnapshot.current = null;
            update({ simulationId: undefined, candidateId: undefined, candidateAlias: undefined });
            setError('이전 시뮬레이션을 찾을 수 없어 새로 시작할 수 있어요.');
          } else setError(errorText(cause));
        });
      }
    };
    refresh(true);
    const timer = window.setInterval(() => refresh(false), 2000);
    return () => window.clearInterval(timer);
  }, [step, saved.personaId, saved.simulationId, refreshCandidates, update]);

  // 완료된 실행도 구독: 서버가 저장된 이벤트 전체를 다시 보내므로 새로고침 후에도 대화를 다시 볼 수 있음
  const canSubscribe = Boolean(saved.simulationId && simulation?.simulation_id === saved.simulationId && simulation.status !== 'failed');
  useEffect(() => {
    if (step !== 'simulation' || !saved.simulationId || !canSubscribe || degraded) return;
    const id = saved.simulationId;
    let active = true;
    const stop = api.subscribeSimulation(id, event => {
      if (!active || !isCurrentSimulation(activeSimulationId.current, id)) return;
      if (seenEvents.current.has(event.id)) return;
      seenEvents.current.add(event.id);
      if (event.type === 'simulation_started') {
        if (event.data.simulation_id !== id) return;
        setSimulation(current => current && current.simulation_id === id && current.status !== 'completed'
          ? { ...current, status: 'running', progress: { done: current.progress.done, total: event.data.total_scenes || current.progress.total } }
          : current);
      } else if (event.type === 'scene_started') {
        const { scene_index, scene } = event.data;
        setScenes(current => [...current.filter(item => item.index !== scene_index), { index: scene_index, scene, turns: [] }].sort((a, b) => a.index - b.index));
      } else if (event.type === 'utterance') {
        const { scene_index, turn, speaker, name, text } = event.data;
        setScenes(current => current.map(item => item.index === scene_index && !item.turns.some(line => line.turn === turn) ? { ...item, turns: [...item.turns, { turn, speaker, name, text }] } : item));
      } else if (event.type === 'scene_judged') {
        const { scene_index, verdict, reason, agreement, rule_candidate, unresolved, progress } = event.data;
        setScenes(current => current.map(item => item.index === scene_index ? { ...item, verdict, reason, agreement, rule: rule_candidate?.text, unresolved } : item));
        setSimulation(current => current && current.simulation_id === id
          ? { ...current, progress: { ...progress, done: Math.max(current.progress.done, progress.done) } }
          : current);
      } else if (event.type === 'simulation_completed') {
        setSimulation(current => current && current.simulation_id === id
          ? { ...current, status: 'completed', score: event.data.score, verdict_counts: event.data.verdict_counts, progress: { done: 20, total: 20 } }
          : current);
      } else if (event.type === 'error') {
        // 오류 이벤트는 실행 종료(실패): 받은 대화는 그대로 두고 다시 시도 버튼 표시
        setError(event.data.message);
        setSimulation(current => current && current.simulation_id === id ? { ...current, status: 'failed' } : current);
        if (['LLM_RATE_LIMITED', 'LLM_UNAVAILABLE'].includes(event.data.code)) setReplayTargetId(saved.candidateId ?? null);
      }
    }, cause => {
      if (!active || !isCurrentSimulation(activeSimulationId.current, id)) return;
      setError(`실시간 연결이 끊겼어요. 진행 상황을 확인하며 완료되면 리포트로 이동해요. (${errorText(cause)})`);
      if (supportsReplay(cause)) setReplayTargetId(saved.candidateId ?? null);
      setDegraded(true);
    });
    return () => { active = false; stop(); };
  }, [step, saved.simulationId, saved.candidateId, canSubscribe, degraded]);

  useEffect(() => {
    if (step !== 'simulation' || !saved.simulationId || !degraded || simulation?.status === 'completed' || simulation?.status === 'failed') return;
    const id = saved.simulationId;
    let active = true;
    const poll = () => { void api.getSimulation(id).then(incoming => {
      if (active && isCurrentSimulation(activeSimulationId.current, id)) setSimulation(current => mergeSimulation(current, incoming));
    }).catch(cause => {
      if (active && isCurrentSimulation(activeSimulationId.current, id)) setError(errorText(cause));
    }); };
    poll(); const timer = window.setInterval(poll, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, [step, saved.simulationId, degraded, simulation?.status]);

  useEffect(() => {
    if (step !== 'simulation' || !degraded || simulation?.status !== 'completed' || !saved.simulationId) return;
    let active = true;
    const id = saved.simulationId;
    void api.getReport(id).then(result => {
      if (!active || !isCurrentSimulation(activeSimulationId.current, id)) return;
      setReport(result);
      setSimulation(current => completedWithReport(current, result));
      update({ step: 'report' });
    }).catch(cause => { if (active && isCurrentSimulation(activeSimulationId.current, id)) setError(errorText(cause)); });
    return () => { active = false; };
  }, [step, degraded, simulation?.status, saved.simulationId, update]);

  async function openReport() {
    if (!saved.simulationId || busy) return;
    const id = saved.simulationId;
    const from = activeStep.current;
    setBusy(true); setError('');
    try {
      const result = await api.getReport(id);
      if (!isCurrentSimulation(activeSimulationId.current, id) || activeStep.current !== from) return;
      if (simulationSnapshot.current?.simulation_id !== id) {
        const fetched = await api.getSimulation(id);
        if (!isCurrentSimulation(activeSimulationId.current, id) || activeStep.current !== from) return;
        simulationSnapshot.current = fetched;
        setSimulation(fetched);
      }
      setReport(result); setSimulation(current => completedWithReport(current, result)); update({ step: 'report' });
    } catch (cause) { if (isCurrentSimulation(activeSimulationId.current, id)) setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function requestMatch() {
    const id = saved.simulationId;
    if (!id || !simulation || simulation.simulation_id !== id || simulation.status !== 'completed' || report?.simulation_id !== id || busy) return;
    const from = activeStep.current;
    setBusy(true); setError('');
    try {
      const result = await api.createMatch(id);
      if (!isCurrentSimulation(activeSimulationId.current, id) || result.simulation_id !== id) return;
      setMatch(result);
      if (activeStep.current !== from) return;
      update({ step: 'match', matchId: result.match_id });
    } catch (cause) { if (isCurrentSimulation(activeSimulationId.current, id)) setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function refreshMatchStatus() {
    if (!match || busy) return;
    setBusy(true); setError('');
    try { setMatch(await api.getMatch(match.match_id)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function openRules() {
    if (!match || match.status !== 'accepted' || busy) return;
    setBusy(true); setError('');
    try { const result = await api.getRules(match.match_id); setRules(result); update({ step: 'rules' }); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function agree() {
    if (!match || busy) return;
    setBusy(true); setError('');
    try { setRules(await api.agreeRules(match.match_id)); }
    catch (cause) { setError(errorText(cause)); }
    finally { setBusy(false); }
  }

  async function viewComparedCandidate(candidateId: string) {
    if (!saved.personaId || busy || activeStep.current !== 'comparison') return;
    const personaId = saved.personaId;
    const request = ++comparisonRequest.current;
    const isCurrent = () => comparisonRequest.current === request && activeStep.current === 'comparison' && activePersonaId.current === personaId;
    setBusy(true); setError('');
    try {
      const response = await api.getCandidates(personaId);
      if (!isCurrent()) return;
      setCandidates(response.candidates); setCandidatesLoaded(true);
      const candidate = response.candidates.find(item => item.candidate_id === candidateId);
      if (!candidate) throw new Error('선택한 후보를 찾을 수 없어요.');
      if (!candidate.simulation || candidate.simulation.status !== 'completed') {
        // 아직 가상 동거 전이면 바로 시작하고, 진행 중이면 진행 화면으로 이동
        await selectCandidate(candidate);
        return;
      }
      const nextSimulation = await api.getSimulation(candidate.simulation.simulation_id);
      if (!isCurrent()) return;
      const nextReport = await api.getReport(candidate.simulation.simulation_id);
      if (!isCurrent()) return;
      setSimulation(nextSimulation);
      simulationSnapshot.current = nextSimulation;
      setReport(nextReport);
      update({ candidateId, candidateAlias: candidate.alias, simulationId: nextSimulation.simulation_id, step: 'report' });
    } catch (cause) { if (isCurrent()) setError(errorText(cause)); }
    finally { if (isCurrent()) setBusy(false); }
  }

  function changeTab(tab: AppTab) {
    if (tab === 'room' && isMock) update({ step: 'room' });
    if (tab === 'match' && saved.personaId) update({ step: 'candidates' });
    if (tab === 'persona' && saved.personaId) update({ step: 'persona' });
    if (tab === 'plans' && saved.personaId) update({ step: 'plans' });
    if (tab === 'all' && isMock) update({ step: 'more' });
  }

  function back() {
    const previous: Partial<Record<Step, Step>> = { survey: 'start', persona: 'survey', candidates: 'persona', simulation: 'candidates', report: 'candidates', rules: 'match', comparison: 'candidates', sceneReplay: 'report', ruleProposal: 'rules', room: 'rules', memo: isMock ? 'room' : 'rules', checkin: 'room', admin: 'more', more: 'candidates', diagnosis: 'candidates' };
    if (step === 'survey' && saved.questionIndex > 0) update({ questionIndex: saved.questionIndex - 1 });
    else if (step === 'room' && !saved.matchId) update({ step: 'more' });
    else if (previous[step]) update({ step: previous[step] });
  }

  const activeCandidate = candidates.find(item => item.candidate_id === saved.candidateId);
  const bestCandidateIndex = visibleCandidates.reduce((best, item, index, list) => displayedScore(item) > displayedScore(list[best]) ? index : best, 0);
  const selectedRule = rules?.rules.find(item => item.rule_id === saved.ruleId);
  const visibleScenes = [...scenes].sort((a, b) => a.index - b.index).filter(item => playback.visible.has(item.index));
  const shownVerdicts = Array.from({ length: 20 }, (_, index) => playback.visible.get(index + 1)?.verdict ? scenes.find(item => item.index === index + 1)?.verdict : undefined);
  const shownDays = new Set(visibleScenes.map(item => item.scene?.day).filter((day): day is number => day != null));
  const currentDay = visibleScenes[visibleScenes.length - 1]?.scene?.day ?? null;
  const simStatusText = !simulation ? '연결 중' : simulation.status === 'failed' ? '중단됨' : simulation.status === 'completed' && playback.caughtUp ? '완료' : scenes.length === 0 ? '준비 중' : '대화 진행 중';
  const title: Record<Step, string> = { start: '룸메궁합', survey: question?.section === 'situation' ? '상황 질문' : '생활 설문', persona: '내 생활 페르소나', candidates: '후보 룸메이트', simulation: activeCandidate?.alias ?? saved.candidateAlias ?? '룸메이트 시뮬레이션', report: '궁합 리포트', match: '매칭 성사', rules: '생활 규칙', comparison: '후보 비교', sceneReplay: '대화 다시 보기', ruleProposal: '규칙 수정 제안', room: '우리 방', memo: '불편 전하기', checkin: '월간 체크인', admin: '관리자 시안', more: '전체', plans: '이용권', diagnosis: '궁합 진단' };
  const activeTab: AppTab | undefined = ['room', 'memo', 'checkin'].includes(step) ? 'room' : ['more', 'admin'].includes(step) ? 'all' : step === 'persona' ? 'persona' : step === 'plans' ? 'plans' : ['candidates', 'simulation', 'report', 'comparison', 'sceneReplay', 'match', 'rules', 'ruleProposal', 'diagnosis'].includes(step) ? 'match' : undefined;
  const enabledTabs: AppTab[] = activeTab ? [...new Set<AppTab>([activeTab, ...(saved.personaId ? ['match', 'persona', 'plans'] as AppTab[] : []), ...(isMock ? ['room', 'all'] as AppTab[] : [])])] : [];

  const visibleTabs: AppTab[] | undefined = isMock ? undefined : ['match', 'persona', 'plans'];
  return <AppShell className={`step-${step}`} title={title[step]} visibleTabs={visibleTabs} showBack={['survey', 'simulation', 'report', 'rules', 'comparison', 'sceneReplay', 'ruleProposal', 'room', 'memo', 'checkin', 'admin', 'more', 'diagnosis'].includes(step)} onBack={back} activeTab={activeTab} enabledTabs={enabledTabs} onTabChange={changeTab}>
    {step === 'start' && <div className="flow-screen flow-start">
      <div className="flow-start-hero">
      <div className="flow-hero-icon" aria-hidden="true"><Icon name="bed" size={46} strokeWidth={1.8} /></div><p className="flow-kicker">우리 방의 시작</p><h1>나와 잘 맞는 룸메이트,<br /><em>미리 만나볼까요?</em></h1><p className="flow-muted">생활 습관을 알아보고 AI 시뮬레이션으로 함께 지낼 모습을 살펴봐요.</p>
      <div className="flow-card flow-info-list"><div><span>01</span><strong>생활 설문 12문항</strong><small>평소 습관과 상황별 선택</small></div><div><span>02</span><strong>후보 6명과 가상 생활</strong><small>20개 장면의 대화와 합의</small></div><div><span>03</span><strong>우리만의 생활 규칙</strong><small>매칭 후 함께 동의</small></div></div>
      </div>
      <div className="flow-start-form">
      <Notice>매칭 전에는 실명과 사진이 공개되지 않아요. 닉네임만으로 바로 시작할 수 있어요.</Notice>
      <label className="flow-input-label" htmlFor="nickname">어떻게 불러드릴까요?</label><input id="nickname" className="flow-input" maxLength={10} placeholder="닉네임을 입력해 주세요" value={saved.nickname} onChange={event => update({ nickname: event.target.value })} onKeyDown={event => { if (event.key === 'Enter') void start(); }} /><small className="flow-count">{saved.nickname.trim().length}/10자</small>
      {error && <Notice tone="error">{error}</Notice>}
      <Footer><Button disabled={busy || saved.nickname.trim().length < 1} onClick={() => void start()}>{busy ? '시작하는 중…' : '나의 룸메이트 찾기'}</Button></Footer>
      </div>
    </div>}

    {step === 'survey' && <div className="flow-screen">
      {loading && !question ? <Notice>설문을 불러오는 중이에요…</Notice> : question ? <>
        <div className="flow-progress-meta"><span>{question.section === 'life' ? '생활 습관' : '상황 질문'}</span><strong>{saved.questionIndex + 1} / {orderedQuestions.length}</strong></div><div className="flow-progress"><span style={{ width: `${(saved.questionIndex + 1) / orderedQuestions.length * 100}%` }} /></div>
        <SurveyCard question={question} answer={saved.answers[question.question_id]} onAnswer={setAnswer} />
        <Notice>{question.section === 'situation' ? '정답은 없어요. 내 AI가 나처럼 대화할 수 있도록 가장 가까운 답을 골라 주세요.' : '편안한 생활을 위해 실제 나와 가까운 답을 골라 주세요.'}</Notice>
        {error && <Notice tone="error">{error}</Notice>}
        <Footer><Button disabled={busy || !isAnswerComplete(question, saved.answers[question.question_id])} onClick={() => void advanceSurvey()}>{busy ? '페르소나 생성 중…' : saved.questionIndex === orderedQuestions.length - 1 ? '페르소나 만들기' : '다음 질문'}</Button></Footer>
      </> : <><Notice tone="error">설문을 불러오지 못했어요.</Notice><Button secondary onClick={() => window.location.reload()}>다시 시도</Button></>}
    </div>}

    {step === 'persona' && <div className="flow-screen">
      {loading && !persona ? <Notice>페르소나를 불러오는 중이에요…</Notice> : persona ? <>
        <div className="flow-persona-card"><div className="flow-persona-top"><span className="flow-persona-badge">MY LIFESTYLE</span><button className="flow-icon-button" type="button" onClick={() => { setMustText(persona.must_keep.join('\n')); setOkayText(persona.okay_with.join('\n')); setEditing(!editing); }} aria-label="페르소나 선호 수정">✎</button></div><div className="flow-persona-symbol" aria-hidden="true">✦</div><p>{persona.nickname}님의 생활 타입</p><h1>{persona.type_name}</h1><div className="flow-persona-summary">{persona.summary}</div><div className="flow-axes">{(Object.keys(persona.axes) as Array<keyof Persona['axes']>).map(key => <div className="flow-axis" key={key}><span>{axisNames[key]} · {persona.axis_labels[key]}</span><div><i style={{ width: `${Math.min(100, Math.max(0, persona.axes[key]))}%` }} /></div></div>)}</div></div>
        {editing ? <div className="flow-card flow-edit"><h2>생활 선호 수정</h2><p className="flow-muted">줄마다 하나씩, 각 목록 최대 3개 · 항목당 30자</p><label>꼭 지켜줘<textarea value={mustText} onChange={event => setMustText(event.target.value)} rows={3} /></label><label>괜찮아요<textarea value={okayText} onChange={event => setOkayText(event.target.value)} rows={3} /></label><Button disabled={busy} onClick={() => void savePersona()}>{busy ? '저장 중…' : '수정 저장'}</Button></div> : <div className="flow-card flow-preferences"><div><span>🔒</span><div><strong>꼭 지켜줘</strong>{persona.must_keep.length ? persona.must_keep.map(item => <p key={item}>{item}</p>) : <p>아직 없어요</p>}</div></div><div><span>☘</span><div><strong>괜찮아요</strong>{persona.okay_with.length ? persona.okay_with.map(item => <p key={item}>{item}</p>) : <p>아직 없어요</p>}</div></div></div>}
        {isMock && <Button secondary onClick={() => setAxisPreviewOpen(current => !current)}>{axisPreviewOpen ? '5개 축 미리보기 닫기' : '5개 축 직접 조정 미리보기'}</Button>}
        {isMock && axisPreviewOpen && <AxisPreviewEditor axes={persona.axes} />}
        {error && <Notice tone="error">{error}</Notice>}
        <Footer><Button disabled={busy || editing} onClick={() => void showCandidates()}>후보 룸메이트 만나기</Button></Footer>
      </> : <Notice tone="error">페르소나를 불러오지 못했어요.</Notice>}
    </div>}

    {step === 'candidates' && <div className="flow-screen flow-candidates"><div className="flow-candidates-intro"><p className="flow-lead">{visibleCandidates.length ? `나와 잘 맞을 것 같은 후보 ${visibleCandidates.length}명이에요` : '나와 잘 맞을 것 같은 후보를 찾고 있어요'}</p><p className="flow-muted">후보를 골라 7일 가상 동거를 해 보세요. 매칭 전에는 실명과 사진이 공개되지 않아요.</p>
      <ol className="flow-steps" aria-label="진행 순서"><li><b>1</b>후보 고르기</li><li><b>2</b>7일 가상 동거<small>메신저 대화 약 2~3분</small></li><li><b>3</b>궁합 리포트</li></ol>
      {passes && <button className={`pass-chip${passes.remaining === 0 ? ' is-empty' : ''}`} type="button" onClick={() => update({ step: 'plans' })}>가상 동거 {passes.remaining}회 남음 · 이용권 보기</button>}</div>
      {loading && !candidates.length && <Notice>후보를 불러오는 중이에요…</Notice>}
      {visibleCandidates.length > 0 && <div className="flow-candidate-list">{visibleCandidates.map((candidate, index) => <CandidateCard key={candidate.candidate_id} candidate={candidate} index={index} best={index === bestCandidateIndex} busy={busy} onSelect={() => void selectCandidate(candidate)} />)}</div>}
      <p className="flow-candidates-note">1차 궁합은 설문으로 계산한 예상 점수예요. 가상 동거를 마치면 실제 대화 결과로 다시 계산돼요.</p>
      {passRequired && <><Notice tone="warm">이용 가능한 가상 동거 횟수를 모두 사용했어요. 이용권을 구매하면 나머지 후보와도 가상 동거를 할 수 있어요.</Notice><Button onClick={() => update({ step: 'plans' })}>이용권 보러 가기</Button></>}
      {diagnosis && (() => {
        const done = visibleCandidates.filter(item => item.simulation?.status === 'completed');
        const warn = diagnosis.level !== 'good' || (done.length >= 3 && done.every(item => (item.simulation?.score ?? 0) < 60));
        return <button className={`flow-card diag-entry${warn ? ' is-warn' : ''}`} type="button" onClick={() => update({ step: 'diagnosis' })}><span><strong>{warn ? '잘 맞는 후보가 적은 이유' : '내 궁합 진단'}</strong><small>{warn ? '어떤 생활 습관이 점수를 낮추는지, 무엇을 바꾸면 좋을지 알려 드려요.' : `잘 맞는 후보 ${diagnosis.good_count}명 · 점수를 낮추는 성향과 조정 방법`}</small></span><span>진단 보기 →</span></button>;
      })()}
      {!loading && candidatesLoaded && candidates.length === 0 && <Notice tone="error">표시할 후보가 없어요. 잠시 후 다시 시도해 주세요.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {replayTargetId && <Notice tone="warm">요청 한도 또는 서버 장애가 발생했어요. 잠시 후 다시 시도하거나 서버 리플레이를 요청할 수 있어요. 리플레이 데이터가 없으면 서버가 실시간 모드로 처리할 수 있습니다.</Notice>}
      {replayTargetId && <Button secondary disabled={busy} onClick={() => void retrySimulation('live')}>시뮬레이션 다시 시도</Button>}
      {replayTargetId && <Button disabled={busy} onClick={() => void retrySimulation('replay')}>리플레이로 다시 시작</Button>}
      <Button secondary disabled={!saved.personaId} onClick={() => update({ step: 'comparison' })}>후보 6명 한눈에 비교하기</Button>
    </div>}

    {step === 'simulation' && <div className="flow-screen flow-chat"><p className="flow-lead">{activeCandidate?.alias ?? saved.candidateAlias ?? '후보'}와 7일간 함께 살아본다면?</p><p className="flow-muted">두 AI 분신이 메신저처럼 대화하며 생활 장면 20개를 함께 겪어요. 대화는 실제 생활을 예측하는 참고 자료예요.</p>
      <div className="flow-sim-progress"><SceneBars values={shownVerdicts} done={playback.judged} /><div className="flow-progress-meta"><span>{simStatusText}</span><strong>{playback.judged} / {simulation?.progress.total ?? 20}장면</strong></div>
        {visibleScenes.length > 0 && <DayChips days={[1, 2, 3, 4, 5, 6, 7]} active={currentDay} enabled={day => shownDays.has(day)} onSelect={day => { if (day) jumpToDay(day); }} />}
        {visibleScenes.length > 0 && !playback.skipped && !(playback.caughtUp && simulation?.status === 'completed') && <div className="flow-chat-controls"><button type="button" onClick={() => playback.setSpeed(playback.speed === 1 ? 2 : 1)}>{playback.speed === 1 ? '▶▶ 2배 빠르게' : '▶ 보통 속도'}</button><button type="button" onClick={playback.skip}>대화 모두 보기</button></div>}
      </div>
      {degraded && <Notice tone="warm">실시간 대화 연결이 불안정해요. 진행 상황을 확인하며, 완료되면 리포트로 이동해요.</Notice>}
      <div className="flow-scenes" aria-live="polite" aria-relevant="additions text">{scenes.length === 0 && !degraded && <Notice>{simulation?.status === 'failed' ? '시뮬레이션이 중단됐어요.' : '두 AI가 첫 장면을 준비하고 있어요…'}</Notice>}{visibleScenes.map((item, position) => { const view = playback.visible.get(item.index)!; const day = item.scene?.day; const newDay = day != null && day !== visibleScenes[position - 1]?.scene?.day; return <Fragment key={item.index}>{newDay && <div className="flow-day-divider" id={`sim-day-${day}`}><span>DAY {day}</span></div>}<article className="flow-scene"><div className="flow-scene-situation"><small>DAY {item.scene?.day ?? '–'} · {item.scene?.time ?? ''} · 장면 {item.index} · {item.scene?.category ?? ''}</small><h2>{item.scene?.title ?? '상황 진행 중'}</h2><p>{item.scene?.situation ?? ''}</p></div>{[...item.turns].sort((a, b) => a.turn - b.turn).slice(0, view.turns).map(turn => <div className={`flow-bubble ${turn.speaker === 'me' ? 'is-me' : ''}`} key={turn.turn}><span className="flow-bubble-avatar">{turn.speaker === 'me' ? '나' : activeCandidate?.alias.slice(-1) ?? '상'}</span><div><strong>{turn.name}</strong><p>{turn.text}</p></div></div>)}{view.verdict && item.verdict && <div className={`flow-verdict is-${item.verdict}`}><strong>{verdictLabels[item.verdict]}</strong><p>{item.reason}</p>{item.agreement && <small>합의안 · {item.agreement}</small>}{item.rule && item.verdict !== 'conflict' && <small className="flow-rule-saved">✓ 규칙 후보 저장 · {item.rule}</small>}{item.verdict === 'conflict' && item.unresolved && <small className="flow-rule-open">조율 필요 · {item.unresolved}</small>}</div>}</article></Fragment>; })}{playback.typing && <TypingBubble isMe={playback.typing.speaker === 'me'} avatar={playback.typing.speaker === 'me' ? '나' : activeCandidate?.alias.slice(-1) ?? '상'} name={playback.typing.name} />}<div ref={sceneEndRef} /></div>
      {!following && visibleScenes.length > 0 && <button type="button" className="flow-chat-latest" onClick={scrollToLatest}>최신 대화 보기 ↓</button>}
      {error && <Notice tone="error">{error}</Notice>}
      {replayTargetId && <Notice tone="warm">요청 한도 또는 서버 장애가 발생했어요. 잠시 후 재시도하거나 리플레이로 전환할 수 있어요. 리플레이가 없으면 서버 설정에 따라 실시간 모드로 진행될 수 있습니다.</Notice>}
      {(degraded || simulation?.status === 'failed') && <Button secondary disabled={busy} onClick={() => void retrySimulation('live')}>시뮬레이션 다시 시도</Button>}
      {replayTargetId && <Button secondary disabled={busy} onClick={() => void retrySimulation('replay')}>리플레이로 전환</Button>}
      {simulation?.status === 'failed' && <Button secondary onClick={() => update({ step: 'candidates' })}>후보로 돌아가기</Button>}
      {simulation?.status === 'completed' && (playback.caughtUp ? <Footer><Button disabled={busy} onClick={() => void openReport()}>궁합 리포트 보기</Button></Footer> : <Footer><Button secondary disabled={busy} onClick={() => void openReport()}>대화 건너뛰고 리포트 보기</Button></Footer>)}
    </div>}

    {step === 'report' && <div className="flow-screen"><p className="flow-lead">{report?.candidate.alias ?? activeCandidate?.alias ?? '후보'}와의 궁합 리포트</p><p className="flow-muted">7일 · 20개 장면에서 확인한 생활 궁합</p>
      {loading && !report && <Notice>리포트를 불러오는 중이에요…</Notice>}
      {report && <><div className="flow-card flow-report-score"><ScoreRing score={report.score} /><div><small>시뮬레이션 궁합 점수</small><h2>{report.headline}</h2><p>실제 생활 결과를 보장하지 않는 참고 점수예요.</p></div></div><div className="flow-card flow-distribution"><h2>7일간의 장면 판정</h2><SceneBars values={report.scene_verdicts} done={20} /><div className="flow-distribution-track">{(['harmonious', 'negotiated', 'conflict', 'pending'] as Verdict[]).map(verdict => <span key={verdict} className={`is-${verdict}`} style={{ width: `${report.verdict_counts[verdict] * 5}%` }} />)}</div><div className="flow-legend">{(['harmonious', 'negotiated', 'conflict', 'pending'] as Verdict[]).map(verdict => <span key={verdict}><i className={`is-${verdict}`} />{verdictLabels[verdict]} {report.verdict_counts[verdict]}</span>)}</div></div><h2 className="flow-section-title">부딪힌 장면과 합의안</h2>{report.highlights.length === 0 && <Notice>크게 부딪힌 장면 없이 7일을 보냈어요.</Notice>}{report.highlights.slice(0, 4).map(item => <div className="flow-card flow-highlight" key={item.scene_index}><span className={`flow-verdict-tag is-${item.verdict}`}>{verdictLabels[item.verdict]}</span><div><small>{item.day}일차 · 장면 {item.scene_index}</small><h3>{item.title}</h3><p>{item.agreement ?? '아직 합의안이 없어요'}</p></div></div>)}<Notice>{report.expected_conflicts_per_month != null ? `한 달 예상 갈등은 약 ${report.expected_conflicts_per_month}회예요. ` : ''}점수는 시뮬레이션 기반 참고값이에요.</Notice><div className="extra-actions"><Button secondary onClick={() => update({ step: 'sceneReplay' })}>장면별 대화 다시 보기</Button><Button secondary onClick={() => update({ step: 'comparison' })}>후보 6명 비교하기</Button></div>{report.score < 60 && <button className="extra-inline-link plans-cta" type="button" onClick={() => update({ step: 'diagnosis' })}>궁합 점수가 낮은 이유 확인하기 →</button>}<button className="extra-inline-link plans-cta" type="button" onClick={() => update({ step: 'plans' })}>다른 후보도 확인하려면 · 이용권 안내 →</button>{error && <Notice tone="error">{error}</Notice>}<Footer><Button secondary onClick={() => update({ step: 'candidates' })}>다른 후보 보기</Button><Button disabled={busy || simulation?.status !== 'completed'} onClick={() => void requestMatch()}>{busy ? '매칭 신청 중…' : '이 후보에게 매칭 신청'}</Button></Footer></>}
      {!report && !loading && <><Notice tone="warm">시뮬레이션이 아직 끝나지 않았거나 리포트를 가져오지 못했어요.</Notice><Button secondary onClick={() => void openReport()}>다시 확인</Button></>}
      {!report && error && <Notice tone="error">{error}</Notice>}
    </div>}

    {step === 'match' && <div className="flow-screen flow-match"><div className="flow-match-avatars" aria-hidden="true"><span>나</span><span>♥</span><span>{match?.status === 'accepted' ? (match.partner?.name.slice(0, 1) ?? '?') : '?'}</span></div><p className="flow-kicker">{match?.status === 'accepted' ? 'MATCHED!' : 'MATCHING'}</p><h1>{match?.status === 'accepted' ? '룸메이트가 됐어요!' : match?.status === 'declined' ? '매칭이 성사되지 않았어요' : '매칭 응답을 기다리는 중이에요'}</h1><p className="flow-muted">{match?.status === 'accepted' ? '함께 지낼 준비를 시작해 볼까요?' : '상대방의 응답을 확인해 주세요.'}</p>
      {match?.status === 'accepted' && match.partner && <><div className="flow-card flow-partner"><span className="flow-avatar flow-avatar--1">{match.partner.name.slice(0, 1)}</span><div><h2>{match.partner.name} 님</h2><p>{match.partner.department} · {match.partner.year}학년</p><small>{match.partner.type_name}</small></div></div><div className="flow-card flow-greeting"><small>룸메이트의 첫 인사</small><p>“{match.partner.greeting}”</p></div><Notice>호실: {match.room ?? '확인 중'} · 생활 규칙 초안을 함께 확인해 주세요.</Notice></>}
      {match?.status === 'declined' && <Notice tone="error">매칭이 성사되지 않았어요. 다른 후보를 살펴보세요.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      {match?.status === 'accepted' ? <Footer><Button disabled={busy} onClick={() => void openRules()}>우리 방 생활 규칙 보기</Button></Footer> : <Footer><Button secondary disabled={busy} onClick={() => void refreshMatchStatus()}>상태 다시 확인</Button></Footer>}
    </div>}

    {step === 'rules' && <div className="flow-screen"><p className="flow-lead">{match?.room ?? '우리 방'} 생활 규칙</p><p className="flow-muted">7일간의 대화에서 나온 약속을 정리했어요.</p>{loading && !rules && <Notice>생활 규칙을 불러오는 중이에요…</Notice>}
      {rules && <><div className="flow-card flow-rules">{rules.rules.map((rule, index) => <div className="flow-rule" key={rule.rule_id}><span className="flow-rule-icon">{['☾', '♧', '✦', '▤', '◉', '▣'][index] ?? '•'}</span><div><strong>{rule.area_label}</strong><p>{rule.text}</p><small>출처 · {rule.source.day}일차 장면 {rule.source.scene_index} · {verdictLabels[rule.source.verdict]}</small><button className="extra-inline-link" type="button" onClick={() => update({ ruleId: rule.rule_id, step: 'ruleProposal' })}>수정 제안</button></div></div>)}</div><div className="flow-card flow-agreements"><h2>서로의 동의</h2><div><span>나</span><strong>{rules.agreements.me ? '동의 완료 ✓' : '동의 전'}</strong></div><div><span>룸메이트</span><strong>{rules.agreements.partner ? '동의 완료 ✓' : '동의 전'}</strong></div></div>{rules.status === 'confirmed' ? <Notice>두 사람 모두 동의했어요. 우리 방 생활 규칙이 확정됐습니다.</Notice> : <Notice>규칙은 시뮬레이션을 바탕으로 만든 초안이에요. 내용을 확인한 뒤 동의해 주세요.</Notice>}{rules.status === 'confirmed' && <div className="extra-actions">{isMock && <Button secondary onClick={() => update({ step: 'room' })}>우리 방 시안 미리보기</Button>}<Button secondary onClick={() => update({ step: 'memo' })}>불편 전하기 (AI 문장 다듬기)</Button><Button secondary onClick={restartExperience}>처음부터 다시 시작하기</Button></div>}{error && <Notice tone="error">{error}</Notice>}<Footer><Button disabled={busy || rules.agreements.me || rules.rules.length !== 6} onClick={() => void agree()}>{rules.status === 'confirmed' ? '생활 규칙 확정 완료' : busy ? '동의 처리 중…' : '이 규칙에 동의하기'}</Button></Footer></>}
      {!rules && error && <Notice tone="error">{error}</Notice>}
    </div>}
    {step === 'comparison' && saved.personaId && <ComparisonScreen personaId={saved.personaId} onViewCandidate={candidateId => void viewComparedCandidate(candidateId)} onCandidateSelected={() => setError('')} isMock={isMock} actionError={error} actionBusy={busy} />}
    {step === 'sceneReplay' && saved.simulationId && <SceneReplayScreen simulationId={saved.simulationId} />}
    {step === 'ruleProposal' && (selectedRule ? <RuleProposalScreen rule={selectedRule} isMock={isMock} onAccepted={updatedRule => { setRules(current => current ? { ...current, rules: current.rules.map(item => item.rule_id === updatedRule.rule_id ? updatedRule : item) } : current); update({ step: 'rules' }); }} /> : <div className="flow-screen"><Notice tone="warm">규칙을 불러오는 중이거나 선택한 규칙을 찾을 수 없어요.</Notice>{error && <Notice tone="error">{error}</Notice>}</div>)}
    {step === 'room' && isMock && <RoomScreen memoEnabled={Boolean(saved.matchId)} onMemo={() => update({ step: 'memo' })} onCheckin={() => update({ step: 'checkin' })} onRules={() => update({ step: 'rules' })} />}
    {step === 'plans' && <PlansScreen />}
    {step === 'diagnosis' && saved.personaId && <DiagnosisScreen personaId={saved.personaId} onCandidates={() => update({ step: 'candidates' })} onEditPersona={() => update({ step: 'persona' })} />}
    {step === 'memo' && saved.matchId && <MemoScreen matchId={saved.matchId} isMock={isMock} onKeepPrivate={() => update({ step: isMock ? 'room' : 'rules' })} />}
    {step === 'checkin' && isMock && <CheckinScreen />}
    {step === 'more' && isMock && <DemoMenuScreen onRoom={() => update({ step: 'room' })} onAdmin={() => update({ step: 'admin' })} onComparison={() => update({ step: 'comparison' })} />}
    {step === 'admin' && isMock && <AdminScreen />}
  </AppShell>;
}

export default App;
