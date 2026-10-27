import type { Simulation, SimulationEvent, Verdict } from '../api/types';

/** Newer retries supersede earlier failed candidate runs. */
export function latestCandidateSimulation(
  simulations: Iterable<Simulation>,
  personaId: string,
  candidateId: string,
): Simulation | undefined {
  let latest: Simulation | undefined;
  for (const simulation of simulations) {
    if (simulation.persona_id === personaId && simulation.candidate_id === candidateId) latest = simulation;
  }
  return latest;
}

export interface StreamState {
  seenIds: Set<string>;
  progress: { done: number; total: number };
  sceneVerdicts: Record<number, Verdict>;
  events: SimulationEvent[];
  completed: boolean;
}

export function initialStreamState(): StreamState {
  return { seenIds: new Set(), progress: { done: 0, total: 20 }, sceneVerdicts: {}, events: [], completed: false };
}

/** Idempotent reducer for SSE replay after Last-Event-ID reconnect. */
export function applySimulationEvent(state: StreamState, event: SimulationEvent): StreamState {
  if (state.seenIds.has(event.id)) return state;
  const sceneVerdicts = { ...state.sceneVerdicts };
  let progress = state.progress;
  if (event.type === 'scene_judged') {
    sceneVerdicts[event.data.scene_index] = event.data.verdict;
    progress = {
      done: Math.min(20, Math.max(state.progress.done, event.data.progress.done)),
      total: event.data.progress.total || 20,
    };
  }
  return {
    seenIds: new Set([...state.seenIds, event.id]),
    progress,
    sceneVerdicts,
    events: [...state.events, event],
    completed: state.completed || event.type === 'simulation_completed',
  };
}
