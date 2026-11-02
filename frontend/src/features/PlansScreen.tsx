import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { PassProduct, PassSummary, Subscription } from '../api/types';
import './plans.css';

// 룸메이트는 입사 신청 시기(학기 전)에 한 번 정하므로 월 구독 대신 횟수제 이용권으로 판매한다.
const PASSES: Record<PassProduct, { label: string; name: string; credits: number; price: string; note: string }> = {
  pass_5: { label: '5회권', name: '플러스 이용권 5회', credits: 5, price: '2,900원', note: '회당 580원 · 후보 6명을 모두 확인하기에 충분해요' },
  pass_15: { label: '15회권', name: '플러스 이용권 15회', credits: 15, price: '6,900원', note: '회당 460원 · 5회권 대비 21% 절약' },
};

const BASIC = ['생활 설문 · 생활 페르소나 생성', '익명 후보 6명 추천 · 궁합 진단', '가상 동거 3회 · 궁합 리포트', '생활 규칙 초안 · 양측 동의'];
const PLUS_FEATURES = ['구매 즉시 가상 동거 횟수 추가', '한 번 결제 · 자동 갱신 없음', '남은 횟수는 다음 학기에도 유지'];
const DORM_FEATURES = ['입사생 전원 가상 동거 횟수 제한 없음', '입사 전 룸메이트 매칭 · 생활 규칙 합의', '관리자 화면 · 갈등 영역 통계 (개인 대화 비공개)'];

function Features({ items }: { items: string[] }) {
  return <ul className="plans-features">{items.map(item => <li key={item}><span aria-hidden="true">✓</span><span>{item}</span></li>)}</ul>;
}

type Pending = { kind: 'pass'; product: PassProduct } | { kind: 'dorm' };

export function PlansScreen() {
  const [passes, setPasses] = useState<PassSummary | null>(null);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [product, setProduct] = useState<PassProduct>('pass_5');
  const [pending, setPending] = useState<Pending | null>(null);
  const [justBought, setJustBought] = useState<PassProduct | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([api.getPasses(), api.getSubscription()]).then(([passValue, subscriptionValue]) => {
      if (!active) return;
      setPasses(passValue); setSubscription(subscriptionValue);
    }).catch(cause => { if (active) setError(cause instanceof Error ? cause.message : '이용 현황을 불러오지 못했어요.'); });
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
    try {
      if (pending.kind === 'pass') { setPasses(await api.buyPass(pending.product)); setJustBought(pending.product); }
      else setSubscription(await api.saveSubscription('dorm'));
      setPending(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : '처리하지 못했어요. 잠시 후 다시 시도해 주세요.'); }
    finally { setBusy(false); }
  }

  async function cancelDorm() {
    if (busy) return;
    setBusy(true); setError('');
    try { setSubscription(await api.cancelSubscription()); }
    catch (cause) { setError(cause instanceof Error ? cause.message : '취소하지 못했어요.'); }
    finally { setBusy(false); }
  }

  const loading = passes === null && !error;
  const dormRequested = subscription?.plan === 'dorm';

  return <div className="flow-screen plans-screen">
    <div><p className="flow-lead">필요한 만큼만, 이용권으로</p><p className="flow-muted">룸메이트는 입사 신청 기간에 한 번 정하면 되므로 월 구독 없이 횟수 단위로 이용합니다.</p></div>

    {passes && <section className="flow-card plans-usage" aria-label="내 이용 현황">
      <div><small>남은 가상 동거</small><strong>{passes.remaining}<span>회</span></strong></div>
      <p>무료 {passes.free_quota}회{passes.purchased ? ` + 구매 ${passes.purchased}회` : ''} 중 {passes.used}회 사용</p>
    </section>}

    <div className="plans-grid">
    <section className="flow-card plans-card">
      <div className="plans-head"><h2>베이직</h2><strong className="plans-price">무료</strong></div>
      <p className="plans-note">가입만 하면 누구나</p>
      <Features items={BASIC} />
      <button className="flow-button flow-button--secondary" type="button" disabled>기본 제공</button>
    </section>

    <section className="flow-card plans-card is-featured" aria-labelledby="plans-plus">
      <span className="plans-badge">학생 추천</span>
      <div className="plans-head"><h2 id="plans-plus">플러스 이용권</h2><strong className="plans-price">{PASSES[product].price}<small> / {PASSES[product].credits}회</small></strong></div>
      <div className="plans-cycle" role="radiogroup" aria-label="이용권 종류">
        {(Object.keys(PASSES) as PassProduct[]).map(key => <button key={key} type="button" role="radio" aria-checked={product === key} className={product === key ? 'is-active' : ''} onClick={() => { setProduct(key); setJustBought(null); }}>{PASSES[key].label}</button>)}
      </div>
      <p className="plans-note">{PASSES[product].note}</p>
      <Features items={PLUS_FEATURES} />
      {justBought === product
        ? <div className="plans-done" role="status"><strong>✓ 구매 완료 · {PASSES[product].credits}회 추가</strong></div>
        : <button className="flow-button" type="button" disabled={busy || loading} onClick={() => setPending({ kind: 'pass', product })}>{PASSES[product].label} 구매하기</button>}
    </section>

    <section className="flow-card plans-card" aria-labelledby="plans-dorm">
      <span className="plans-badge is-org">기관용</span>
      <div className="plans-head"><h2 id="plans-dorm">생활관</h2><strong className="plans-price">2,000원<small> / 입사생 1인 · 학기</small></strong></div>
      <p className="plans-note">1,000명 생활관 기준 학기 200만원</p>
      <Features items={DORM_FEATURES} />
      {dormRequested
        ? <div className="plans-done" role="status"><strong>✓ 도입 요청 완료</strong><button className="extra-inline-link" type="button" disabled={busy} onClick={() => void cancelDorm()}>요청 취소</button></div>
        : <button className="flow-button flow-button--secondary" type="button" disabled={busy || loading} onClick={() => setPending({ kind: 'dorm' })}>우리 생활관에 도입 요청</button>}
    </section>
    </div>

    {passes && passes.purchases.length > 0 && <section className="flow-card plans-history" aria-label="구매 내역">
      <h2>구매 내역</h2>
      <ul>{passes.purchases.map(item => <li key={item.purchase_id}><span>{PASSES[item.product].name}</span><span>{item.price.toLocaleString('ko-KR')}원</span><time dateTime={item.created_at}>{item.created_at.slice(0, 10).replaceAll('-', '.')}</time></li>)}</ul>
    </section>}

    {error && !pending && <p className="extra-error" role="alert">{error}</p>}
    <p className="flow-notice">같은 후보의 가상 동거를 다시 열어 보거나, 오류로 끝나지 못한 가상 동거는 횟수가 차감되지 않아요.</p>

    {pending && <div className="plans-sheet-backdrop" onClick={() => { if (!busy) setPending(null); }}>
      <div className="plans-sheet" role="dialog" aria-modal="true" aria-labelledby="plans-sheet-title" onClick={event => event.stopPropagation()}>
        <h2 id="plans-sheet-title">{pending.kind === 'dorm' ? '생활관 도입 요청' : '이용권 구매'}</h2>
        {pending.kind === 'pass' ? <dl>
          <div><dt>상품</dt><dd>{PASSES[pending.product].name}</dd></div>
          <div><dt>금액</dt><dd>{PASSES[pending.product].price}</dd></div>
          <div><dt>적용</dt><dd>구매 즉시 가상 동거 {PASSES[pending.product].credits}회 추가</dd></div>
        </dl> : <dl>
          <div><dt>요금</dt><dd>입사생 1인당 학기 2,000원 (생활관 부담)</dd></div>
          <div><dt>처리</dt><dd>요청이 모이면 생활관 행정실에 도입을 제안해요</dd></div>
        </dl>}
        <p>{pending.kind === 'pass' ? '자동 갱신되지 않는 1회 구매 상품이에요.' : '학생 개인에게는 비용이 청구되지 않아요. 요청은 언제든 취소할 수 있어요.'}</p>
        {error && <p className="extra-error" role="alert">{error}</p>}
        <button ref={confirmRef} className="flow-button" type="button" disabled={busy} onClick={() => void confirm()}>{busy ? '처리 중…' : pending.kind === 'dorm' ? '도입 요청하기' : `${PASSES[pending.product].price} 구매하기`}</button>
        <button className="flow-button flow-button--secondary" type="button" disabled={busy} onClick={() => setPending(null)}>닫기</button>
      </div>
    </div>}
  </div>;
}
