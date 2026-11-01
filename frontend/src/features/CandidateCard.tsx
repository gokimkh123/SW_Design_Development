import type { Candidate } from '../api/types';

/** 카드에 표시할 점수: 가상 동거를 마쳤으면 시뮬레이션 점수, 아니면 설문 기반 1차 궁합 */
export function displayedScore(candidate: Candidate): number {
  const sim = candidate.simulation;
  return sim?.status === 'completed' && sim.score != null ? sim.score : candidate.pre_score;
}

export function CandidateCard({ candidate, index, best, busy, onSelect }: {
  candidate: Candidate; index: number; best: boolean; busy: boolean; onSelect: () => void;
}) {
  const sim = candidate.simulation;
  const done = sim?.status === 'completed' && sim.score != null;
  const failed = sim?.status === 'failed';
  const running = Boolean(sim) && !done && !failed;
  const tone = done ? 'completed' : failed ? 'failed' : running ? 'running' : 'idle';
  const status = !sim ? '시작 전 · 약 2~3분'
    : done ? '가상 동거 완료'
    : failed ? '중단됨 · 다시 시작할 수 있어요'
    : sim.status === 'queued' ? '준비 중'
    : `진행 중 · ${sim.progress.done}/${sim.progress.total}장면`;
  const action = done ? '리포트 보기' : failed ? '다시 시작' : running ? '진행 보기' : '가상 동거 시작';
  const percent = sim ? Math.round(sim.progress.done / Math.max(sim.progress.total, 1) * 100) : 0;
  return <article className={`flow-card flow-candidate${best ? ' is-best' : ''}`} aria-label={`${candidate.alias}, ${done ? '가상 동거 궁합' : '1차 궁합'} ${displayedScore(candidate)}점, ${status}`}>
    {best && <span className="flow-candidate-badge">추천</span>}
    <div className="flow-candidate-head">
      <span className={`flow-avatar flow-avatar--${index}`} aria-hidden="true">{candidate.alias.slice(-1)}</span>
      <div><h2>{candidate.alias}</h2><p>{candidate.department} · {candidate.year}학년</p></div>
      <div className="flow-candidate-score"><strong>{displayedScore(candidate)}<small>점</small></strong><span>{done ? '가상 동거 궁합' : '1차 궁합'}</span></div>
    </div>
    <div className="flow-candidate-tags">
      <span className="flow-candidate-type">{candidate.type_name}</span>
      <span className="flow-candidate-highlight">✦ {candidate.highlight}</span>
    </div>
    {running && <div className="flow-candidate-progress" aria-hidden="true"><i style={{ width: `${percent}%` }} /></div>}
    <div className="flow-candidate-action">
      <span className={`flow-status is-${tone}`}><i aria-hidden="true" />{status}</span>
      <button type="button" className={done ? 'is-quiet' : ''} disabled={busy} onClick={onSelect}>{action} <span aria-hidden="true">→</span></button>
    </div>
  </article>;
}
