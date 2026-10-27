import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import type { Candidate, Comparison, RephraseResult, Rule, RuleProposal, SceneResult } from '../api/types';

const axisKeys = ['sleep_rhythm', 'noise_sensitivity', 'cleanliness', 'sociability', 'sharing_tolerance'] as const;
const axisLabels = ['수면 리듬', '소음 민감', '청결', '사교성', '공유 관대'];

function ErrorMessage({ message }: { message: string }) {
  return <p className="extra-error" role="alert">{message}</p>;
}

function LoadingMessage() { return <p className="extra-muted" role="status">데이터를 불러오는 중이에요…</p>; }

function points(axes: Comparison['me']['axes'], scale = 1): string {
  return axisKeys.map((key, index) => {
    const angle = -Math.PI / 2 + index * (Math.PI * 2 / 5);
    const radius = (axes[key] / 100) * 91 * scale;
    return `${160 + Math.cos(angle) * radius},${132 + Math.sin(angle) * radius}`;
  }).join(' ');
}

const radarColors = ['#dc8050', '#6475d0', '#b35a91'];

function Radar({ me, candidates, selectedId }: { me: Comparison['me']['axes']; candidates: Comparison['candidates']; selectedId: string }) {
  const empty = Object.fromEntries(axisKeys.map(key => [key, 100])) as Comparison['me']['axes'];
  const axisDescription = (axes: Comparison['me']['axes']) => axisKeys.map((key, index) => `${axisLabels[index]} ${axes[key]}`).join(', ');
  return <div className="extra-radar-wrap">
    <svg className="extra-radar" viewBox="0 0 320 270" role="img" aria-labelledby="comparison-radar-title comparison-radar-desc">
      <title id="comparison-radar-title">나와 후보 3명의 생활 성향 5축 비교</title>
      <desc id="comparison-radar-desc">나: {axisDescription(me)}. {candidates.map(candidate => `${candidate.alias}${candidate.candidate_id === selectedId ? '(선택됨)' : ''}: ${axisDescription(candidate.axes)}.`).join(' ')}</desc>
      {[.25, .5, .75, 1].map(level => <polygon key={level} points={points(empty, level)} fill="none" stroke="#e2e9ea" strokeWidth="1" />)}
      {axisKeys.map((_, index) => {
        const angle = -Math.PI / 2 + index * (Math.PI * 2 / 5);
        const x = 160 + Math.cos(angle) * 91;
        const y = 132 + Math.sin(angle) * 91;
        return <line key={index} x1="160" y1="132" x2={x} y2={y} stroke="#e2e9ea" />;
      })}
      <polygon points={points(me)} fill="#10a092" fillOpacity=".1" stroke="#087f75" strokeWidth="2.5" />
      {candidates.map((candidate, index) => <polygon key={candidate.candidate_id} points={points(candidate.axes)} fill={radarColors[index % radarColors.length]} fillOpacity=".08" stroke={radarColors[index % radarColors.length]} strokeWidth={candidate.candidate_id === selectedId ? 3 : 2} strokeLinejoin="round" />)}
      {axisLabels.map((label, index) => {
        const angle = -Math.PI / 2 + index * (Math.PI * 2 / 5);
        return <text key={label} x={160 + Math.cos(angle) * 122} y={132 + Math.sin(angle) * 112} textAnchor="middle" dominantBaseline="middle" className="extra-radar-label">{label}</text>;
      })}
    </svg>
    <div className="extra-legend"><span><i style={{ backgroundColor: '#087f75' }} />나</span>{candidates.map((candidate, index) => <span key={candidate.candidate_id} className={candidate.candidate_id === selectedId ? 'is-selected' : ''}><i style={{ backgroundColor: radarColors[index % radarColors.length] }} />{candidate.alias}{candidate.candidate_id === selectedId ? ' · 선택' : ''}</span>)}</div>
  </div>;
}

export function ComparisonScreen({ personaId, onViewCandidate, onCandidateSelected, isMock, actionError, actionBusy }: {
  personaId: string;
  onViewCandidate: (candidateId: string) => void;
  onCandidateSelected: () => void;
  isMock: boolean;
  actionError: string;
  actionBusy: boolean;
}) {
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [candidateStatuses, setCandidateStatuses] = useState<Candidate[] | null>(null);
  const [candidateId, setCandidateId] = useState('');
  const [error, setError] = useState('');
  const [statusError, setStatusError] = useState(false);
  useEffect(() => {
    let active = true;
    setComparison(null); setCandidateStatuses(null); setCandidateId(''); setError(''); setStatusError(false);
    void api.getComparison(personaId).then(value => {
      if (!active) return;
      setComparison(value);
      setCandidateId(value.candidates.find(item => item.candidate_id === value.recommended_candidate_id)?.candidate_id ?? value.candidates[0]?.candidate_id ?? '');
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '비교 결과를 불러오지 못했어요.'); });
    void api.getCandidates(personaId).then(value => { if (active) setCandidateStatuses(value.candidates); }).catch(() => { if (active) setStatusError(true); });
    return () => { active = false; };
  }, [personaId]);
  const selected = comparison?.candidates.find(item => item.candidate_id === candidateId) ?? comparison?.candidates[0];
  return <div className="flow-screen extra-screen">
    <p className="flow-lead">누구와 함께 살까요?</p>
    <p className="extra-muted">세 후보의 생활 성향과 궁합 점수를 한눈에 살펴보세요.</p>
    {isMock && <p className="extra-preview">시안 미리보기 · 점수와 월 예상 갈등은 임시 데이터예요.</p>}
    {error && <ErrorMessage message={error} />}
    {actionError && <ErrorMessage message={actionError} />}
    {!comparison && !error && <LoadingMessage />}
    {comparison?.candidates.length === 0 && <ErrorMessage message="비교할 후보가 없어요. 후보 목록을 다시 확인해 주세요." />}
    {statusError && <p className="extra-muted" role="status">점수 출처 확인 실패 · 점수 종류를 확인할 수 없어 표기를 보류했어요.</p>}
    {comparison && selected && <>
      <section className="flow-card extra-radar-card"><h2>나와 후보 3명의 생활 성향</h2><Radar me={comparison.me.axes} candidates={comparison.candidates} selectedId={candidateId} /></section>
      <section className="flow-card extra-rank-card"><h2>후보별 궁합</h2>
        {comparison.candidates.map((candidate, index) => <button type="button" className={`extra-rank-row ${candidateId === candidate.candidate_id ? 'is-selected' : ''}`} key={candidate.candidate_id} disabled={actionBusy} onClick={() => { setCandidateId(candidate.candidate_id); onCandidateSelected(); }} aria-pressed={candidateId === candidate.candidate_id}>
          <span className={`flow-avatar flow-avatar--${index}`}>{candidate.alias.slice(-1)}</span>
          <span className="extra-rank-copy"><strong>{candidate.alias}</strong><small>월 예상 갈등 {candidate.expected_conflicts_per_month == null ? '산식 미확정' : `${candidate.expected_conflicts_per_month}회${isMock ? ' · 임시 예시' : ' · 추정치'}`}</small></span>
          <span className="extra-rank-score"><strong>{candidate.score}점</strong><small>{candidateStatuses?.find(item => item.candidate_id === candidate.candidate_id)?.simulation?.status === 'completed' ? '시뮬레이션' : candidateStatuses?.some(item => item.candidate_id === candidate.candidate_id) ? '1차 궁합' : statusError ? '출처 확인 실패' : '출처 확인 중'}</small></span>
        </button>)}
      </section>
      <p className="extra-muted">점수는 함께 사는 결과를 보장하지 않는 참고값입니다. 매칭 신청은 해당 후보의 완료된 리포트에서 할 수 있어요.</p>
      <div className="flow-footer"><button className="flow-button" type="button" disabled={actionBusy} onClick={() => onViewCandidate(selected.candidate_id)}>{actionBusy ? '리포트 확인 중…' : `${selected.alias} 리포트에서 신청하기`}</button></div>
    </>}
  </div>;
}

export function SceneReplayScreen({ simulationId }: { simulationId: string }) {
  const [scenes, setScenes] = useState<SceneResult[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    void api.getScenes(simulationId).then(result => { if (active) setScenes(result.scenes); }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '대화를 불러오지 못했어요.'); });
    return () => { active = false; };
  }, [simulationId]);
  return <div className="flow-screen extra-screen"><p className="flow-lead">장면별 대화 다시 보기</p><p className="extra-muted">완료된 시뮬레이션의 장면과 합의 내용을 확인해요.</p>
    {error && <ErrorMessage message={error} />}{!scenes && !error && <LoadingMessage />}
    {scenes?.length === 0 && <p className="extra-muted">표시할 장면이 없어요.</p>}
    {scenes?.map(item => <details className="flow-card extra-scene" key={item.scene_index}><summary><span>{item.scene.day}일차 · 장면 {item.scene_index}</span><strong>{item.scene.title}</strong><small>{item.verdict === 'harmonious' ? '원만' : item.verdict === 'negotiated' ? '조율' : item.verdict === 'conflict' ? '충돌' : '판정 보류'}</small></summary><p>{item.scene.situation}</p>{item.dialogue.map(line => <div className="extra-dialogue" key={line.turn}><b>{line.name}</b><span>{line.text}</span></div>)}<div className="extra-scene-result"><strong>판정 이유</strong><p>{item.reason}</p>{item.agreement && <p>합의: {item.agreement}</p>}</div></details>)}
  </div>;
}

export function RuleProposalScreen({ rule, onAccepted, isMock }: { rule: Rule; onAccepted: (rule: Rule) => void; isMock: boolean }) {
  const [text, setText] = useState(rule.text);
  const [reason, setReason] = useState('');
  const [proposal, setProposal] = useState<RuleProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [examPreview, setExamPreview] = useState(false);
  const active = useRef(false);
  const request = useRef(0);
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; request.current += 1; };
  }, []);
  const canPropose = text.trim().length > 0 && reason.trim().length > 0;
  async function propose() {
    if (!canPropose || busy) return;
    const currentRequest = ++request.current;
    setBusy(true); setError(''); setProposal(null);
    try { const result = await api.proposeRule(rule.rule_id, { text: text.trim(), reason: reason.trim() }); if (active.current && request.current === currentRequest) setProposal(result); }
    catch (cause) { if (active.current && request.current === currentRequest) setError(cause instanceof Error ? cause.message : '중재안을 만들지 못했어요.'); }
    finally { if (active.current && request.current === currentRequest) setBusy(false); }
  }
  async function accept() {
    if (!proposal || busy) return;
    const currentRequest = ++request.current;
    setBusy(true); setError('');
    try { const accepted = await api.acceptProposal(proposal.proposal_id); if (active.current && request.current === currentRequest) onAccepted(accepted); }
    catch (cause) { if (active.current && request.current === currentRequest) setError(cause instanceof Error ? cause.message : '중재안 수락에 실패했어요.'); }
    finally { if (active.current && request.current === currentRequest) setBusy(false); }
  }
  return <div className="flow-screen extra-screen"><p className="flow-lead">규칙을 다시 맞춰 볼까요?</p><p className="extra-muted">서로의 생활 방식을 고려한 제안을 만들어요.</p>
    {isMock && <p className="extra-preview">시안 미리보기 · AI 중재 결과는 임시 예시예요.</p>}
    <section className="flow-card extra-rule-current"><small>현재 {rule.area_label}</small><del>{rule.text}</del><span>→ 변경할 규칙을 제안해 주세요.</span></section>
    <section className="flow-card extra-form"><h2>나의 수정 제안</h2><label htmlFor="rule-proposal-text">새 규칙</label><input id="rule-proposal-text" value={text} disabled={busy} onChange={event => { setText(event.target.value); setProposal(null); }} maxLength={100} /><label htmlFor="rule-proposal-reason">제안 이유</label><textarea id="rule-proposal-reason" value={reason} disabled={busy} onChange={event => { setReason(event.target.value); setProposal(null); }} maxLength={200} rows={3} placeholder="왜 변경하고 싶은지 적어 주세요" /><button className="flow-button" disabled={!canPropose || busy} type="button" onClick={() => void propose()}>{busy ? '검토 중…' : 'AI 중재안 보기'}</button></section>
    {proposal && <section className="flow-card extra-mediation"><small>AI 중재자의 제안</small><h2>{proposal.mediation.text}</h2><p>두 사람의 생활 페르소나를 바탕으로 검토했어요.</p><ul>{proposal.mediation.rationale.map((item, index) => <li key={index}>{item}</li>)}</ul></section>}
    {isMock && <label className="extra-disabled-row"><input type="checkbox" checked={examPreview} onChange={event => setExamPreview(event.target.checked)} />시험 기간 자동 반영 미리보기 <span>서버 미적용</span></label>}
    {examPreview && <p className="extra-preview">시험 기간 자동 감지 화면만 미리 봅니다. 학사 일정 API가 없어 기간 판단이나 실제 규칙 적용은 하지 않아요.</p>}
    {error && <ErrorMessage message={error} />}
    {proposal && <div className="flow-footer"><button className="flow-button flow-button--secondary" type="button" disabled={busy} onClick={() => setProposal(null)}>다르게 제안</button><button className="flow-button" type="button" disabled={busy} onClick={() => void accept()}>{busy ? '반영 중…' : '중재안 수락'}</button></div>}
  </div>;
}

export function MemoScreen({ matchId, onKeepPrivate, isMock }: { matchId: string; onKeepPrivate: () => void; isMock: boolean }) {
  const [memo, setMemo] = useState('');
  const [result, setResult] = useState<RephraseResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const remaining = useMemo(() => 500 - memo.length, [memo]);
  async function rephrase() {
    if (!memo.trim() || busy) return;
    setBusy(true); setError(''); setResult(null);
    try { setResult(await api.rephraseMemo(matchId, memo.trim())); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '메시지 변환에 실패했어요.'); }
    finally { setBusy(false); }
  }
  return <div className="flow-screen extra-screen"><p className="flow-lead">조심스럽게 말하고 싶은 게 있나요?</p><p className="extra-muted">메모 원문은 상대에게 전달되지 않아요. 이 화면을 떠나면 입력 내용도 지워집니다.</p>
    {isMock && <p className="extra-preview">시안 미리보기 · 변환 문장과 규칙 제안은 임시 예시예요.</p>}
    <section className="flow-card extra-form"><h2>나만 보이는 메모</h2><label htmlFor="private-memo">편하게 적어 주세요</label><textarea id="private-memo" value={memo} disabled={busy} onChange={event => { setMemo(event.target.value); setResult(null); }} maxLength={500} rows={5} placeholder="불편했던 일을 적어 주세요" /><small>{remaining}자 남음</small><button type="button" className="flow-button" disabled={!memo.trim() || busy} onClick={() => void rephrase()}>{busy ? '다듬는 중…' : '요청형 문장으로 다듬기'}</button></section>
    {result && <><section className="flow-card extra-message"><small>상대에게 보낼 메시지 미리보기</small><p>{result.message}</p></section><section className="flow-card extra-message"><small>함께 제안할 생활 규칙</small><p>{result.suggested_rule.text}</p></section><p className="extra-muted">현재 명세에는 메시지 전송 API가 없습니다. 아래 화면은 확인용이며, 상대에게 전송되지 않습니다.</p></>}
    {error && <ErrorMessage message={error} />}
    <div className="flow-footer"><button type="button" className="flow-button flow-button--secondary" onClick={onKeepPrivate}>그냥 둘게요</button><button type="button" className="flow-button" disabled title="전송 API가 정해진 뒤 사용할 수 있어요">보내기 · 연동 대기</button></div>
  </div>;
}
