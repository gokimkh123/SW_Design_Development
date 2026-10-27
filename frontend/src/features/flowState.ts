import type { Simulation } from '../api/types';

/** A late REST snapshot must not roll back progress already observed over SSE. */
export function mergeSimulation(current: Simulation | null, incoming: Simulation): Simulation {
  if (!current || current.simulation_id !== incoming.simulation_id) return incoming;
  if (current.status === 'completed') return current;
  if (incoming.progress.done < current.progress.done) return current;
  return incoming;
}

/** Ignore responses from a candidate that is no longer selected. */
export function isCurrentSimulation(activeId: string | null, responseId: string): boolean {
  return activeId === responseId;
}
