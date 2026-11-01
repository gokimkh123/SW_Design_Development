import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { Subscription, SubscriptionPlan } from '../api/types';
import './plans.css';

type PlusPlan = Extract<SubscriptionPlan, 'plus_semester' | 'plus_monthly'>;

const PLUS: Record<PlusPlan, { label: string; change: string; price: string; unit: string; note: string }> = {
  plus_semester: { label: '학기 패스', change: '학기 패스로 변경 신청', price: '9,900원', unit: '6개월', note: '월 1,650원꼴 · 월간 대비 43% 절약' },
  plus_monthly: { label: '월간', change: '월간으로 변경 신청', price: '2,900원', unit: '월', note: '입주 시즌에만 짧게 이용' },
};

const PLAN_TEXT: Record<SubscriptionPlan, { name: string; amount: string }> = {
  plus_semester: { name: '플러스 학기 패스', amount: '9,900원 / 6개월' },
  plus_monthly: { name: '플러스 월간', amount: '2,900원 / 월' },
  dorm: { name: '생활관 (기관)', amount: '입사생 1인당 학기 2,000원' },
};

const BASIC = ['생활 설문 · 생활 페르소나 생성', '익명 후보 3명 추천', '가상 동거 1회 · 궁합 리포트', '생활 규칙 초안 · 양측 동의'];
const PLUS_FEATURES: { text: string; soon?: boolean }[] = [
  { text: '후보 3명 모두 가상 동거 · 후보 비교 그래프' },
  { text: '한 달 예상 갈등 · 장면별 대화 다시 보기' },
  { text: '규칙 수정 AI 중재안 · 불편 전하기 문장 다듬기' },
  { text: 'AI(LLM) 실제 대화 가상 동거', soon: true },
];
const DORM_FEATURES: { text: string; soon?: boolean }[] = [
  { text: '입사생 전원 플러스 기능 제공' },
  { text: '입사 전 룸메이트 매칭 · 생활 규칙 합의' },
  { text: '관리자 화면 · 갈등 영역 통계 (개인 대화 비공개)', soon: true },
];

function Features({ items }: { items: { text: string; soon?: boolean }[] }) {
  return <ul className="plans-features">{items.map(item => <li key={item.text}><span aria-hidden="true">✓</span><span>{item.text}{item.soon && <em>정식 출시 예정</em>}</span></li>)}</ul>;
}

export function PlansScreen() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [cycle, setCycle] = useState<PlusPlan>('plus_semester');
  const [pending, setPending] = useState<SubscriptionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    void api.getSubscription().then(value => {
      if (!active) return;
      setSubscription(value);
      if (value.plan === 'plus_monthly' || value.plan === 'plus_semester') setCycle(value.plan);
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '신청 상태를 불러오지 못했어요.'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!pending) return;
    confirmRef.current?.focus();
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) setPending(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [pending, busy]);

  async function confirm() {
    if (!pending || busy) return;
    setBusy(true); setError('');
    try { setSubscription(await api.saveSubscription(pending)); setPending(null); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '신청하지 못했어요. 잠시 후 다시 시도해 주세요.'); }
    finally { setBusy(false); }
  }

  async function cancel() {
    if (busy) return;
    setBusy(true); setError('');
    try { setSubscription(await api.cancelSubscription()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '취소하지 못했어요.'); }
    finally { setBusy(false); }
  }

  const current = subscription?.plan ?? null;
  const plusActive = current === 'plus_semester' || current === 'plus_monthly';
  const loading = subscription === null && !error;

  return <div className="flow-screen plans-screen">
    <div><p className="flow-lead">룸메궁합 멤버십</p><p className="flow-muted">입주 전 궁합 확인부터 입주 후 갈등 관리까지</p></div>

    <div className="plans-grid">
    <section className="flow-card plans-card">
      <div className="plans-head"><h2>베이직</h2><strong className="plans-price">무료</strong></div>
      <Features items={BASIC.map(text => ({ text }))} />
      <button className="flow-button flow-button--secondary" type="button" disabled>{current ? '기본 제공' : '이용 중'}</button>
    </section>

    <section className="flow-card plans-card is-featured" aria-labelledby="plans-plus">
      <span className="plans-badge">학생 추천</span>
      <div className="plans-head"><h2 id="plans-plus">플러스</h2><strong className="plans-price">{PLUS[cycle].price}<small> / {PLUS[cycle].unit}</small></strong></div>
      <div className="plans-cycle" role="radiogroup" aria-label="결제 주기">
        {(Object.keys(PLUS) as PlusPlan[]).map(plan => <button key={plan} type="button" role="radio" aria-checked={cycle === plan} className={cycle === plan ? 'is-active' : ''} onClick={() => setCycle(plan)}>{PLUS[plan].label}</button>)}
      </div>
      <p className="plans-note">{PLUS[cycle].note}</p>
      <Features items={PLUS_FEATURES} />
      {current === cycle
        ? <div className="plans-done" role="status"><strong>✓ 사전 구독 신청 완료</strong><button className="extra-inline-link" type="button" disabled={busy} onClick={() => void cancel()}>신청 취소</button></div>
        : <button className="flow-button" type="button" disabled={busy || loading} onClick={() => setPending(cycle)}>{plusActive ? PLUS[cycle].change : '플러스 구독하기'}</button>}
    </section>

    <section className="flow-card plans-card" aria-labelledby="plans-dorm">
      <span className="plans-badge is-org">기관용</span>
      <div className="plans-head"><h2 id="plans-dorm">생활관</h2><strong className="plans-price">2,000원<small> / 입사생 1인 · 학기</small></strong></div>
      <p className="plans-note">1,000명 생활관 기준 학기 200만원</p>
      <Features items={DORM_FEATURES} />
      {current === 'dorm'
        ? <div className="plans-done" role="status"><strong>✓ 도입 관심 등록 완료</strong><button className="extra-inline-link" type="button" disabled={busy} onClick={() => void cancel()}>등록 취소</button></div>
        : <button className="flow-button flow-button--secondary" type="button" disabled={busy || loading} onClick={() => setPending('dorm')}>생활관 도입 문의</button>}
    </section>
    </div>

    {error && <p className="extra-error" role="alert">{error}</p>}
    <p className="flow-notice">발표회 체험 기간에는 결제 없이 사전 신청만 받아요. 신청과 관계없이 모든 기능을 무료로 이용할 수 있어요.</p>

    {pending && <div className="plans-sheet-backdrop" onClick={() => { if (!busy) setPending(null); }}>
      <div className="plans-sheet" role="dialog" aria-modal="true" aria-labelledby="plans-sheet-title" onClick={event => event.stopPropagation()}>
        <h2 id="plans-sheet-title">{pending === 'dorm' ? '생활관 도입 관심 등록' : '플러스 사전 구독 신청'}</h2>
        <dl>
          <div><dt>플랜</dt><dd>{PLAN_TEXT[pending].name}</dd></div>
          <div><dt>금액</dt><dd>{PLAN_TEXT[pending].amount}</dd></div>
          <div><dt>결제</dt><dd>정식 출시 후 진행 · 지금은 결제되지 않아요</dd></div>
        </dl>
        <p>카드 · 계좌 · 연락처 등 개인정보는 받지 않아요. 신청 내용은 언제든 취소할 수 있어요.</p>
        <button ref={confirmRef} className="flow-button" type="button" disabled={busy} onClick={() => void confirm()}>{busy ? '신청 중…' : pending === 'dorm' ? '관심 등록하기' : '사전 구독 신청하기'}</button>
        <button className="flow-button flow-button--secondary" type="button" disabled={busy} onClick={() => setPending(null)}>닫기</button>
      </div>
    </div>}
  </div>;
}
