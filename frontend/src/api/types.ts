export type Verdict = 'harmonious' | 'negotiated' | 'conflict' | 'pending';
export type SimulationStatus = 'queued' | 'running' | 'completed' | 'failed';
export type SimulationMode = 'live' | 'replay';
export type Answer = string | Record<string, string>;
export type Answers = Record<string, Answer>;

export interface SurveyField {
  key: string;
  label: string;
  min: string;
  max: string;
  step_minutes: number;
  default: string;
}

export interface SurveyOption {
  value: string;
  label: string;
  style?: 'direct' | 'avoid' | 'delay';
}

export interface SurveyQuestion {
  question_id: string;
  section: 'life' | 'situation';
  type: 'time_range' | 'choice';
  title: string;
  hint?: string;
  fields?: SurveyField[];
  options?: SurveyOption[];
}

export interface Survey { version: string; questions: SurveyQuestion[] }
export interface User { user_id: string; nickname: string; created_at: string }
export type Axes = Record<'sleep_rhythm' | 'noise_sensitivity' | 'cleanliness' | 'sociability' | 'sharing_tolerance', number>;

export interface Persona {
  persona_id: string;
  user_id: string;
  nickname: string;
  type_name: string;
  summary: string;
  sleep: { bedtime: string; wake: string; exam_pattern: string };
  axes: Axes;
  axis_labels: Record<keyof Axes, string>;
  conflict_style: 'direct' | 'avoid' | 'delay';
  preferences: { temperature: string };
  must_keep: string[];
  okay_with: string[];
  is_seed: boolean;
  created_at: string;
}

export interface Progress { done: number; total: number }
export interface VerdictCounts { harmonious: number; negotiated: number; conflict: number; pending: number }
export interface Candidate {
  candidate_id: string;
  alias: string;
  department: string;
  year: number;
  type_name: string;
  pre_score: number;
  highlight: string;
  simulation: null | { simulation_id: string; status: SimulationStatus; progress: Progress; score: number | null };
}
export interface Simulation {
  simulation_id: string;
  persona_id: string;
  candidate_id: string;
  mode: SimulationMode;
  status: SimulationStatus;
  progress: Progress;
  verdict_counts: VerdictCounts;
  score: number | null;
  started_at: string;
  completed_at: string | null;
}

export interface Scene {
  scene_id: string;
  day: number;
  weekday: string;
  time: string;
  category: string;
  title: string;
  situation: string;
}
export interface Utterance {
  turn: number;
  speaker: 'me' | 'candidate';
  name: string;
  text: string;
}
export interface RuleCandidate { area: string; text: string }
export interface SceneResult {
  scene_index: number;
  scene: Scene;
  dialogue: Utterance[];
  verdict: Verdict;
  reason: string;
  agreement: string | null;
  rule_candidate: RuleCandidate | null;
  unresolved: string | null;
}
export interface Report {
  simulation_id: string;
  candidate: { candidate_id: string; alias: string; type_name: string };
  score: number;
  headline: string;
  verdict_counts: VerdictCounts;
  scene_verdicts: Verdict[];
  highlights: Array<{ scene_index: number; day: number; title: string; verdict: Verdict; agreement: string | null }>;
  expected_conflicts_per_month: number | null;
}
export interface Match {
  match_id: string;
  simulation_id: string;
  status: 'pending' | 'accepted' | 'declined';
  partner: null | {
    persona_id: string;
    name: string;
    department: string;
    year: number;
    type_name: string;
    greeting: string;
  };
  room: string | null;
  rules_status: 'draft' | 'confirmed';
}
export interface Rule {
  rule_id: string;
  area: string;
  area_label: string;
  text: string;
  source: { scene_index: number; day: number; verdict: Verdict };
}
export interface RuleSet {
  match_id: string;
  status: 'draft' | 'confirmed';
  rules: Rule[];
  agreements: { me: boolean; partner: boolean };
}

/** P1 response shapes from docs/API.md 4.16. P2 has no API contract yet. */
export interface Comparison {
  me: { axes: Axes };
  candidates: Array<{
    candidate_id: string;
    alias: string;
    axes: Axes;
    score: number;
    expected_conflicts_per_month: number | null;
  }>;
  recommended_candidate_id: string;
}

export interface RuleProposal {
  proposal_id: string;
  rule_id: string;
  mediation: { text: string; rationale: string[] };
}

export interface RephraseResult {
  message: string;
  suggested_rule: { area: string; text: string };
}

export type SimulationEvent =
  | { id: string; type: 'simulation_started'; data: { simulation_id: string; mode: SimulationMode; total_scenes: number; me: { name: string; type_name: string }; candidate: { alias: string; type_name: string } } }
  | { id: string; type: 'scene_started'; data: { scene_index: number; scene: Scene } }
  | { id: string; type: 'utterance'; data: { scene_index: number } & Utterance }
  | { id: string; type: 'scene_judged'; data: { scene_index: number; verdict: Verdict; reason: string; agreement: string | null; rule_candidate: RuleCandidate | null; unresolved: string | null; progress: Progress } }
  | { id: string; type: 'simulation_completed'; data: { score: number; headline: string; verdict_counts: VerdictCounts } }
  | { id: string; type: 'error'; data: { code: string; message: string; scene_index?: number; retryable?: boolean } };

export interface ApiClient {
  createUser(nickname: string): Promise<User>;
  getSurvey(): Promise<Survey>;
  createPersona(answers: Answers): Promise<Persona>;
  getPersona(id: string): Promise<Persona>;
  patchPersona(id: string, changes: Pick<Persona, 'must_keep' | 'okay_with'>): Promise<Persona>;
  getCandidates(personaId: string): Promise<{ candidates: Candidate[] }>;
  startSimulation(personaId: string, candidateId: string, mode?: SimulationMode): Promise<Simulation>;
  getSimulation(id: string): Promise<Simulation>;
  getReport(id: string): Promise<Report>;
  getScenes(simulationId: string): Promise<{ scenes: SceneResult[] }>;
  getComparison(personaId: string): Promise<Comparison>;
  createMatch(simulationId: string): Promise<Match>;
  getMatch(id: string): Promise<Match>;
  getRules(matchId: string): Promise<RuleSet>;
  agreeRules(matchId: string): Promise<RuleSet>;
  proposeRule(ruleId: string, proposal: { text: string; reason: string }): Promise<RuleProposal>;
  acceptProposal(proposalId: string): Promise<Rule>;
  rephraseMemo(matchId: string, memo: string): Promise<RephraseResult>;
  subscribeSimulation(id: string, onEvent: (event: SimulationEvent) => void, onError: (error: Error) => void): () => void;
}
