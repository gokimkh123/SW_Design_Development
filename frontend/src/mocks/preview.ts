/**
 * P2 visual-only fixtures. No D1/D3/D4 HTTP contract exists in docs/API.md yet.
 * These values must never be presented as live room or administrator data.
 */
export interface PreviewRoom {
  previewOnly: true;
  room: string;
  daysTogether: number;
  lifeScore: number;
  delta: number;
  tasks: Array<{ id: string; label: string; due: string; assignee: string; done: boolean }>;
  supplies: Array<{ item: string; buyer: string; amount: number; settled: boolean }>;
  quietHours: { start: string; end: string; note: string };
}

export interface PreviewCheckin {
  previewOnly: true;
  month: string;
  ruleCompliance: Array<{ area: string; label: string; percent: number }>;
  trend: Array<{ month: string; score: number }>;
}

export interface PreviewAdmin {
  previewOnly: true;
  residence: string;
  roomCount: number;
  avgScore: number;
  mediations: number;
  reassignments: number;
  riskRooms: Array<{ room: string; score: number; conflictTypes: string[] }>;
  privacyNotice: string;
}

export const previewRoom: PreviewRoom = {
  previewOnly: true,
  room: '302호 (배정 예정)',
  daysTogether: 14,
  lifeScore: 82,
  delta: 5,
  tasks: [
    { id: 'task_clean', label: '공용 공간 청소', due: '일요일 14:00', assignee: '나', done: false },
    { id: 'task_sort', label: '분리수거', due: '수요일 19:00', assignee: '룸메이트', done: true },
  ],
  supplies: [
    { item: '휴지', buyer: '나', amount: 6800, settled: false },
    { item: '세제', buyer: '룸메이트', amount: 8900, settled: true },
  ],
  quietHours: { start: '23:30', end: '07:00', note: '평일 적용' },
};

export const previewCheckin: PreviewCheckin = {
  previewOnly: true,
  month: '11월',
  ruleCompliance: [
    { area: 'quiet_hours', label: '조용한 시간', percent: 92 },
    { area: 'cleaning', label: '청소', percent: 78 },
    { area: 'guests', label: '친구 초대', percent: 85 },
  ],
  trend: [
    { month: '9월', score: 72 },
    { month: '10월', score: 77 },
    { month: '11월', score: 82 },
  ],
};

export const previewAdmin: PreviewAdmin = {
  previewOnly: true,
  residence: '생활관 시안',
  roomCount: 120,
  avgScore: 78,
  mediations: 6,
  reassignments: 2,
  riskRooms: [
    { room: '214호', score: 43, conflictTypes: ['소음', '청소'] },
    { room: '507호', score: 51, conflictTypes: ['공용품', '친구 초대'] },
    { room: '108호', score: 57, conflictTypes: ['수면 리듬'] },
  ],
  privacyNotice: '관리자 화면에는 대화 원문이나 개인 메모를 표시하지 않습니다.',
};
