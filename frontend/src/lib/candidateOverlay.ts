import type { Candidate, Simulation } from '../api/types';

export function withSessionSimulation(
  candidates: Candidate[], simulation: Simulation | null,
  saved: { personaId?: string; simulationId?: string },
): Candidate[] {
  return candidates.map(candidate => {
    if (candidate.simulation || !simulation || simulation.simulation_id !== saved.simulationId
        || simulation.persona_id !== saved.personaId || simulation.candidate_id !== candidate.candidate_id) return candidate;
    return { ...candidate, simulation: {
      simulation_id: simulation.simulation_id, status: simulation.status,
      progress: simulation.progress, score: simulation.score,
    } };
  });
}
