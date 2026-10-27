import { useState } from 'react';
import type { Axes } from '../api/types';
import { previewAdmin, previewCheckin, previewRoom } from '../mocks/preview';

function PreviewBanner({ admin = false }: { admin?: boolean }) {
  return <p className="extra-preview" role="status">{admin ? '관리자 시안 미리보기 · 권한 검증 및 실제 집계 API 미연동' : '함께 사는 동안의 시안 미리보기 · 아래 수치는 실제 호실 데이터가 아닙니다.'}</p>;
}

const axisNames: Record<keyof Axes, string> = { sleep_rhythm: '수면 리듬', noise_sensitivity: '소음 민감', cleanliness: '청결', sociability: '사교성', sharing_tolerance: '공유 관대' };

export function AxisPreviewEditor({ axes }: { axes: Axes }) {
  const [values, setValues] = useState<Axes>({ ...axes });
  return <section className="flow-card extra-axis-editor"><h2>5개 축 직접 조정 · 데모</h2><p className="extra-muted">슬라이더는 이 화면에서만 움직입니다. 실제 페르소나·후보 점수·시뮬레이션에는 반영되지 않아요.</p>
    {(Object.keys(axisNames) as Array<keyof Axes>).map(key => <label key={key}><span>{axisNames[key]}</span><input type="range" min="0" max="100" value={values[key]} onChange={event => setValues(current => ({ ...current, [key]: Number(event.target.value) }))} /><strong>{values[key]}</strong></label>)}
    <button className="flow-button flow-button--secondary" type="button" onClick={() => setValues({ ...axes })}>원래 값으로 되돌리기</button>
  </section>;
}

export function RoomScreen({ onMemo, onCheckin, onRules, memoEnabled }: { onMemo: () => void; onCheckin: () => void; onRules: () => void; memoEnabled: boolean }) {
  return <div className="flow-screen extra-screen">
    <div className="extra-room-heading"><div><small>함께 사는 우리 방</small><h2>{previewRoom.room}</h2></div><span>함께한 지 {previewRoom.daysTogether}일 예시</span></div>
    <PreviewBanner />
    <section className="extra-life-score"><small>생활 지수 · 예시</small><strong>{previewRoom.lifeScore}<span>점</span></strong><p>지난달보다 {previewRoom.delta >= 0 ? '+' : ''}{previewRoom.delta}점</p></section>
    <section className="flow-card extra-list-card"><h2>이번 주 할 일</h2>{previewRoom.tasks.map(task => <div className="extra-list-row" key={task.id}><span className={`extra-task-icon ${task.done ? 'is-done' : ''}`}>{task.done ? '✓' : '○'}</span><div><strong>{task.label}</strong><small>{task.due} · {task.assignee} 차례</small></div></div>)}</section>
    <section className="flow-card extra-list-card"><h2>공용품 구매 · 정산</h2>{previewRoom.supplies.map(item => <div className="extra-list-row" key={item.item}><span className="extra-task-icon">▣</span><div><strong>{item.item}</strong><small>{item.buyer} 구매 · {item.amount.toLocaleString('ko-KR')}원</small></div><span className="extra-row-state">{item.settled ? '정산 완료' : '정산 예정'}</span></div>)}</section>
    <section className="flow-card extra-quiet"><span>☾</span><div><small>오늘의 조용한 시간 · 예시</small><strong>{previewRoom.quietHours.start} – {previewRoom.quietHours.end}</strong><p>{previewRoom.quietHours.note}</p></div></section>
    <div className="extra-actions"><button className="flow-button flow-button--secondary" type="button" onClick={onRules} disabled={!memoEnabled}>생활 규칙 보기</button><button className="flow-button flow-button--secondary" type="button" onClick={onCheckin}>월간 체크인</button><button className="flow-button" type="button" onClick={onMemo} disabled={!memoEnabled}>{memoEnabled ? '불편 전하기' : '불편 전하기 · 매칭 후 이용'}</button></div>
  </div>;
}

export function CheckinScreen() {
  const [satisfaction, setSatisfaction] = useState<'uncomfortable' | 'neutral' | 'good' | null>(null);
  return <div className="flow-screen extra-screen"><p className="flow-lead">{previewCheckin.month}의 우리 방은 어땠나요?</p><p className="extra-muted">서로의 생활을 돌아보는 월간 체크인이에요.</p><PreviewBanner />
    <section className="flow-card extra-checkin-card"><h2>이번 달 만족도</h2><div className="extra-satisfaction">{([
      ['uncomfortable', '불편했어요', '☹'], ['neutral', '보통이에요', '◡'], ['good', '좋았어요', '☺'],
    ] as const).map(([value, label, icon]) => <button key={value} className={satisfaction === value ? 'is-selected' : ''} type="button" aria-pressed={satisfaction === value} onClick={() => setSatisfaction(value)}><span aria-hidden="true">{icon}</span>{label}</button>)}</div></section>
    <section className="flow-card extra-checkin-card"><h2>규칙 이행률 · 예시</h2>{previewCheckin.ruleCompliance.map(item => <div className="extra-compliance" key={item.area}><div><span>{item.label}</span><strong>{item.percent}%</strong></div><div className="extra-compliance-track"><i style={{ width: `${item.percent}%` }} /></div></div>)}</section>
    <section className="flow-card extra-checkin-card"><h2>생활 지수 추이 · 예시</h2><div className="extra-trend">{previewCheckin.trend.map(item => <div key={item.month}><strong>{item.score}</strong><span style={{ height: `${item.score}%` }} /><small>{item.month}</small></div>)}</div></section>
    <p className="extra-muted">선택 내용은 화면 안에서만 유지됩니다. 체크인 저장 API가 확정되기 전에는 서버에 제출되지 않습니다.</p>
    <div className="flow-footer"><button className="flow-button" type="button" disabled title="체크인 저장 API 연동 대기">체크인 제출 · 연동 대기</button></div>
  </div>;
}

export function AdminScreen() {
  return <div className="flow-screen extra-screen"><div className="extra-admin-head"><span className="extra-admin-badge">B2B · DEMO ONLY</span><h2>{previewAdmin.residence}</h2><p>전체 {previewAdmin.roomCount}개 호실 · 비식별 집계 예시</p></div><PreviewBanner admin />
    <div className="extra-admin-metrics"><div className="flow-card"><small>평균 생활 지수</small><strong>{previewAdmin.avgScore}<em>점</em></strong></div><div className="flow-card"><small>진행 중 중재</small><strong>{previewAdmin.mediations}<em>건</em></strong></div><div className="flow-card"><small>재배정 요청</small><strong>{previewAdmin.reassignments}<em>건</em></strong></div></div>
    <section className="flow-card extra-risk-card"><h2>살펴볼 호실 · 예시</h2>{previewAdmin.riskRooms.map(room => <div className="extra-risk-row" key={room.room}><span>{room.room}</span><div><strong>생활 지수 {room.score}점</strong><small>{room.conflictTypes.join(' · ')}</small></div></div>)}</section>
    <p className="extra-preview">{previewAdmin.privacyNotice} 이 화면은 권한 없는 실제 사용자가 접근할 수 있는 관리자 기능이 아닙니다.</p>
  </div>;
}

export function DemoMenuScreen({ onRoom, onAdmin, onComparison }: { onRoom: () => void; onAdmin: () => void; onComparison: () => void }) {
  return <div className="flow-screen extra-screen"><p className="flow-lead">추가 화면 미리보기</p><p className="extra-muted">아래 항목은 백엔드 계약 또는 권한 검증 전 시안 확인용입니다.</p><PreviewBanner />
    <section className="flow-card extra-menu"><button type="button" onClick={onRoom}><span>⌂</span><div><strong>우리 방</strong><small>생활 지수 · 할 일 · 공용품 정산</small></div><b>→</b></button><button type="button" onClick={onComparison}><span>◇</span><div><strong>후보 비교</strong><small>5축 성향과 후보별 점수</small></div><b>→</b></button><button type="button" onClick={onAdmin}><span>▤</span><div><strong>관리자 화면 · 데모 전용</strong><small>비식별 집계 예시만 표시</small></div><b>→</b></button></section>
  </div>;
}
