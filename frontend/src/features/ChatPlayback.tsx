import { useEffect, useMemo, useRef, useState } from 'react';
import type { Scene, Utterance, Verdict } from '../api/types';

/** 받은 장면 데이터 (App의 SceneView와 같은 모양) */
export type PlaybackScene = {
  index: number; scene?: Scene; turns: Utterance[]; verdict?: Verdict; reason?: string;
  agreement?: string | null; rule?: string | null; unresolved?: string | null;
};
type Item = { kind: 'scene'; scene: number } | { kind: 'turn'; scene: number; turn: Utterance } | { kind: 'verdict'; scene: number };
export type Speed = 1 | 2;

/** 장면 카드 → 발화 → 판정 순서의 표시 항목 (이벤트 도착 순서와 같음) */
function flatten(scenes: PlaybackScene[]): Item[] {
  const items: Item[] = [];
  for (const item of [...scenes].sort((a, b) => a.index - b.index)) {
    items.push({ kind: 'scene', scene: item.index });
    for (const turn of [...item.turns].sort((a, b) => a.turn - b.turn)) items.push({ kind: 'turn', scene: item.index, turn });
    if (item.verdict) items.push({ kind: 'verdict', scene: item.index });
  }
  return items;
}

/** 입력 중 표시 시간: 글자 수에 비례 (메신저처럼 짧은 말은 빨리, 긴 말은 천천히) */
const typingMs = (text: string) => Math.min(2000, Math.max(900, 600 + text.length * 25));

/**
 * 받은 대화를 메신저처럼 한 줄씩 보여 준다. 서버 진행과 별개로 화면 표시만 늦추며,
 * instant(이미 끝난 시뮬레이션을 다시 열 때)이거나 '모두 보기'를 누르면 즉시 전부 표시.
 */
export function useChatPlayback(scenes: PlaybackScene[], { instant, resetKey }: { instant: boolean; resetKey: string }) {
  const items = useMemo(() => flatten(scenes), [scenes]);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState<Utterance | null>(null);
  const [speed, setSpeed] = useState<Speed>(1);
  const [skipped, setSkipped] = useState(false);

  useEffect(() => { setShown(0); setTyping(null); setSkipped(false); }, [resetKey]);

  const immediate = instant || skipped;
  const hasNext = shown < items.length;
  useEffect(() => {
    if (immediate) {
      setTyping(null);
      if (shown !== itemsRef.current.length) setShown(itemsRef.current.length);
      return;
    }
    if (!hasNext) { setTyping(null); return; }
    const next = itemsRef.current[shown];
    const previous = shown > 0 ? itemsRef.current[shown - 1] : null;
    let timer: number;
    if (next.kind === 'turn') {
      if (!typing) timer = window.setTimeout(() => setTyping(next.turn), (previous?.kind === 'scene' ? 700 : 350) / speed);
      else timer = window.setTimeout(() => { setTyping(null); setShown(count => count + 1); }, typingMs(next.turn.text) / speed);
    } else {
      timer = window.setTimeout(() => setShown(count => count + 1), (next.kind === 'scene' ? (shown === 0 ? 150 : 600) : 700) / speed);
    }
    return () => window.clearTimeout(timer);
  }, [shown, typing, speed, immediate, hasNext, items.length === 0]);

  const visible = useMemo(() => {
    const map = new Map<number, { turns: number; verdict: boolean }>();
    for (let i = 0; i < Math.min(shown, items.length); i += 1) {
      const item = items[i];
      if (item.kind === 'scene') map.set(item.scene, { turns: 0, verdict: false });
      else {
        const entry = map.get(item.scene);
        if (entry && item.kind === 'turn') entry.turns += 1;
        if (entry && item.kind === 'verdict') entry.verdict = true;
      }
    }
    return map;
  }, [items, shown]);

  return {
    visible, typing, speed, setSpeed, caughtUp: shown >= items.length, skip: () => setSkipped(true), skipped: immediate,
    /** 화면에 판정까지 표시된 장면 수 */
    judged: [...visible.values()].filter(entry => entry.verdict).length,
    shownCount: shown,
  };
}

/** 대화 다시 보기 · 진행 화면 공용 DAY 선택 */
export function DayChips({ days, active, enabled, onSelect, allLabel }: {
  days: number[]; active: number | null; enabled: (day: number) => boolean; onSelect: (day: number | null) => void; allLabel?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // 현재 DAY 버튼이 가로 스크롤 밖에 있으면 가운데로 이동 (세로 스크롤은 건드리지 않음)
    const container = box.current;
    const button = container?.querySelector<HTMLElement>('button.is-active');
    if (container && button) container.scrollTo({ left: button.offsetLeft - container.clientWidth / 2 + button.clientWidth / 2, behavior: 'smooth' });
  }, [active]);
  return <div className="flow-day-chips" role="tablist" aria-label="일차 선택" ref={box}>
    {allLabel && <button type="button" role="tab" aria-selected={active === null} className={active === null ? 'is-active' : ''} onClick={() => onSelect(null)}>{allLabel}</button>}
    {days.map(day => <button key={day} type="button" role="tab" aria-selected={active === day} disabled={!enabled(day)} className={active === day ? 'is-active' : ''} onClick={() => onSelect(day)}>DAY {day}</button>)}
  </div>;
}

export function TypingBubble({ isMe, avatar, name }: { isMe: boolean; avatar: string; name: string }) {
  return <div className={`flow-bubble flow-typing ${isMe ? 'is-me' : ''}`} role="status" aria-label={`${name} 입력 중`}>
    <span className="flow-bubble-avatar" aria-hidden="true">{avatar}</span>
    <div><strong>{name}</strong><p><i /><i /><i /></p></div>
  </div>;
}
