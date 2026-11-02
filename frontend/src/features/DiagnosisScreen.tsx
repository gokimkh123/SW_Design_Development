import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Diagnosis } from '../api/types';
import './diagnosis.css';

/** 받침 유무에 맞춘 조사(을/를) */
function objectParticle(word: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  return code >= 0 && code <= 11171 && code % 28 !== 0 ? '을' : '를';
}

const LEVEL_TEXT: Record<Diagnosis['level'], { title: string; body: string }> = {
  good: { title: '잘 맞는 후보가 충분해요', body: '아래 성향만 미리 이야기해 두면 갈등을 더 줄일 수 있어요.' },
  limited: { title: '잘 맞는 후보가 많지 않아요', body: '몇 가지 생활 성향이 다른 학생들과 크게 달라 점수가 낮아지고 있어요.' },
  hard: { title: '지금은 잘 맞는 후보를 찾기 어려워요', body: '여러 생활 성향이 동시에 다른 학생들과 차이가 커요. 아래 습관부터 점검해 보세요.' },
};

/** 궁합 진단: 잘 맞는 후보가 적은 이유(점수를 깎는 성향)와 습관 조정 시 달라지는 후보 수 */
export function DiagnosisScreen({ personaId, onCandidates, onEditPersona }: { personaId: string; onCandidates: () => void; onEditPersona: () => void }) {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    void api.getDiagnosis(personaId).then(value => { if (active) setDiagnosis(value); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '진단을 불러오지 못했어요.'); });
    return () => { active = false; };
  }, [personaId]);

  if (error) return <div className="flow-screen"><p className="extra-error" role="alert">{error}</p></div>;
  if (!diagnosis) return <div className="flow-screen"><p className="flow-notice">진단하는 중이에요…</p></div>;

  const level = LEVEL_TEXT[diagnosis.level];
  const adjust = diagnosis.best_adjustment;
  return <div className="flow-screen diag-screen">
    <section className={`flow-card diag-summary is-${diagnosis.level}`}>
      <small>궁합 진단</small>
      <h2>{level.title}</h2>
      <p>{level.body}</p>
      <div className="diag-stat"><strong>{diagnosis.good_count}<span>명</span></strong><span>후보 {diagnosis.pool_size}명 중 {diagnosis.good_score}점 이상</span></div>
    </section>

    {adjust && <section className="flow-card diag-adjust">
      <h2>이 습관을 조금 바꾸면</h2>
      <p><b>{adjust.labels.join(' · ')}</b>{objectParticle(adjust.labels[adjust.labels.length - 1])} 다른 학생들 쪽으로 조금 맞추면 잘 맞는 후보가 <b>{adjust.good_before}명 → {adjust.good_after}명</b>으로 늘어요.</p>
    </section>}

    <h2 className="flow-section-title">점수를 낮추는 생활 성향</h2>
    {diagnosis.factors.map((factor, index) => <section className="flow-card diag-factor" key={factor.axis}>
      <div className="diag-factor-head">
        <span className="diag-rank">{index + 1}</span>
        <div><h3>{factor.label}</h3><p>{factor.summary}</p></div>
        <strong className="diag-loss">평균 −{factor.score_loss}점</strong>
      </div>
      <div className="diag-bar" aria-label={`내 위치 ${factor.my_value}, 후보 중앙값 ${factor.pool_median}`}>
        <i className="diag-bar-pool" style={{ left: `${factor.pool_median}%` }} />
        <i className="diag-bar-me" style={{ left: `${factor.my_value}%` }} />
      </div>
      <div className="diag-bar-legend"><span><i className="is-me" />나</span><span><i className="is-pool" />다른 학생들(중앙값)</span>{factor.far_count > 0 && <span>차이 큰 후보 {factor.far_count}명</span>}</div>
      {factor.tips.length > 0 && <ul className="diag-tips">{factor.tips.map(tip => <li key={tip}>{tip}</li>)}</ul>}
    </section>)}

    <p className="flow-notice">진단은 설문으로 계산한 생활 성향을 기준으로 해요. 습관이 실제로 달라졌다면 설문을 다시 하거나 생활 선호를 수정해 주세요.</p>
    <div className="extra-actions">
      <button className="flow-button flow-button--secondary" type="button" onClick={onEditPersona}>내 생활 페르소나 보기</button>
      <button className="flow-button" type="button" onClick={onCandidates}>후보 다시 보기</button>
    </div>
  </div>;
}
