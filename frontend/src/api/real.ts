import type {
  Answers, ApiClient, Candidate, Comparison, Match, Persona, RephraseResult, Report,
  Health, Rule, RuleProposal, RuleSet, SceneResult, Simulation, SimulationEvent, SimulationMode, Survey, User,
} from './types';

const USER_KEY = 'roommate.user_id';
let memoryUserId: string | null = null;

export function setUserId(id: string | null): void {
  memoryUserId = id;
  if (typeof sessionStorage !== 'undefined') {
    if (id) sessionStorage.setItem(USER_KEY, id);
    else sessionStorage.removeItem(USER_KEY);
  }
}

export function getUserId(): string | null {
  if (memoryUserId) return memoryUserId;
  return typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(USER_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, method = 'GET', body?: unknown, publicRoute = false): Promise<T> {
  const headers = new Headers({ Accept: 'application/json' });
  if (body !== undefined) headers.set('Content-Type', 'application/json');
  if (!publicRoute && getUserId()) headers.set('X-User-Id', getUserId()!);
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK_ERROR', '백엔드에 연결할 수 없어요. 서버 실행 상태를 확인해 주세요.');
  }
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const error = payload && typeof payload === 'object' && 'error' in payload
      ? (payload as { error?: { code?: string; message?: string } }).error
      : undefined;
    throw new ApiError(response.status, error?.code ?? 'HTTP_ERROR', error?.message ?? `요청에 실패했어요. (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function parseSseBlock(block: string): SimulationEvent | null {
  let id = '';
  let type = '';
  const data: string[] = [];
  let hasField = false;
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    hasField = true;
    const colon = line.indexOf(':');
    if (colon < 0) continue;
    const field = line.slice(0, colon);
    const value = line.slice(colon + 1).replace(/^ /, '');
    if (field === 'id') id = value;
    if (field === 'event') type = value;
    if (field === 'data') data.push(value);
  }
  if (!hasField) return null;
  if (!id || !type || data.length === 0) {
    throw new ApiError(0, 'SSE_MALFORMED_EVENT', '실시간 이벤트 형식이 올바르지 않아요.');
  }
  try {
    return { id, type, data: JSON.parse(data.join('\n')) } as SimulationEvent;
  } catch {
    throw new ApiError(0, 'SSE_MALFORMED_EVENT', '실시간 이벤트 형식이 올바르지 않아요.');
  }
}

/** Fetch stream allows X-User-Id on SSE, unlike browser EventSource. */
function subscribeSimulation(
  id: string,
  onEvent: (event: SimulationEvent) => void,
  onError: (error: Error) => void,
): () => void {
  const controller = new AbortController();
  let stopped = false;
  let completed = false;
  let lastEventId = '';
  const seenIds = new Set<string>();

  const connect = async () => {
    for (let attempt = 0; attempt < 3 && !stopped && !completed; attempt++) {
      let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
      let failure: Error | null = null;
      try {
        const headers = new Headers({ Accept: 'text/event-stream' });
        const userId = getUserId();
        if (userId) headers.set('X-User-Id', userId);
        if (lastEventId) headers.set('Last-Event-ID', lastEventId);
        const response = await fetch(`/api/simulations/${encodeURIComponent(id)}/events`, {
          headers,
          signal: controller.signal,
        });
        if (!response.ok || !response.body) throw new ApiError(response.status, 'SSE_UNAVAILABLE', '실시간 연결을 사용할 수 없어요.');
        reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (!stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          // Normalize after concatenation so CRLF split across chunks is preserved.
          buffer += decoder.decode(value, { stream: true });
          buffer = buffer.replace(/\r\n/g, '\n');
          let boundary = buffer.indexOf('\n\n');
          while (boundary >= 0) {
            const event = parseSseBlock(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary + 2);
            if (event?.type === 'error') {
              if (!seenIds.has(event.id)) {
                seenIds.add(event.id);
                onEvent(event);
              }
              // Do not advance Last-Event-ID past an error event; each retry
              // must still fail fast if the server repeats the same error.
              throw new Error(event.data.message);
            }
            if (event && !seenIds.has(event.id)) {
              seenIds.add(event.id);
              lastEventId = event.id;
              onEvent(event);
              if (event.type === 'simulation_completed') { completed = true; controller.abort(); break; }
            }
            boundary = buffer.indexOf('\n\n');
          }
          if (completed) break;
        }
        if (completed || stopped) return;
        throw new Error('실시간 연결이 끊어졌어요.');
      } catch (error) {
        if (stopped || completed) return;
        failure = error instanceof Error ? error : new Error('실시간 연결에 실패했어요.');
      } finally {
        if (reader) {
          await reader.cancel().catch(() => {});
          reader.releaseLock();
        }
      }
      if (failure && attempt === 2) { onError(failure); return; }
      if (!stopped && !completed) await new Promise<void>((resolve) => setTimeout(resolve, 700 * (attempt + 1)));
    }
  };
  void connect();
  return () => { stopped = true; controller.abort(); };
}

export const realApi: ApiClient = {
  getHealth: () => request<Health>('/health', 'GET', undefined, true),
  createUser: (nickname: string) => request<User>('/users', 'POST', { nickname }, true),
  getSurvey: () => request<Survey>('/survey', 'GET', undefined, true),
  createPersona: (answers: Answers) => request<Persona>('/personas', 'POST', { answers }),
  getPersona: (id: string) => request<Persona>(`/personas/${encodeURIComponent(id)}`),
  patchPersona: (id: string, changes: Pick<Persona, 'must_keep' | 'okay_with'>) =>
    request<Persona>(`/personas/${encodeURIComponent(id)}`, 'PATCH', changes),
  getCandidates: (personaId: string) =>
    request<{ candidates: Candidate[] }>(`/personas/${encodeURIComponent(personaId)}/candidates`),
  startSimulation: (personaId: string, candidateId: string, mode: SimulationMode = 'live') =>
    request<Simulation>('/simulations', 'POST', { persona_id: personaId, candidate_id: candidateId, mode }),
  getSimulation: (id: string) => request<Simulation>(`/simulations/${encodeURIComponent(id)}`),
  getReport: (id: string) => request<Report>(`/simulations/${encodeURIComponent(id)}/report`),
  getScenes: (id: string) => request<{ scenes: SceneResult[] }>(`/simulations/${encodeURIComponent(id)}/scenes`),
  getComparison: (personaId: string) => request<Comparison>(`/personas/${encodeURIComponent(personaId)}/comparison`),
  createMatch: (simulationId: string) => request<Match>('/matches', 'POST', { simulation_id: simulationId }),
  getMatch: (id: string) => request<Match>(`/matches/${encodeURIComponent(id)}`),
  getRules: (matchId: string) => request<RuleSet>(`/matches/${encodeURIComponent(matchId)}/rules`),
  agreeRules: (matchId: string) => request<RuleSet>(`/matches/${encodeURIComponent(matchId)}/rules/agree`, 'POST'),
  proposeRule: (ruleId: string, proposal: { text: string; reason: string }) =>
    request<RuleProposal>(`/rules/${encodeURIComponent(ruleId)}/proposals`, 'POST', proposal),
  acceptProposal: (proposalId: string) =>
    request<Rule>(`/proposals/${encodeURIComponent(proposalId)}/accept`, 'POST'),
  rephraseMemo: (matchId: string, memo: string) =>
    request<RephraseResult>('/mediation/rephrase', 'POST', { match_id: matchId, memo }),
  subscribeSimulation,
};
