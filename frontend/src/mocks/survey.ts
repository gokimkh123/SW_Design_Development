import type { Survey } from '../api/types';

/**
 * 임시 화면 검증용 fixture. q01/q02/q09는 docs/API.md 4.3 예시,
 * 나머지 질문/라벨은 docs/PRD.md 부록 A 초안에서 옮겼으며 option value는
 * 실제 data/seed/survey.json 승인 전까지 확정 계약이 아니다.
 */
export const provisionalSurvey: Survey = {
  version: 'provisional-prd-2026-10-26',
  questions: [
    { question_id: 'q01', section: 'life', type: 'time_range', title: '평일에는 보통 몇 시에 자고 일어나요?', fields: [
      { key: 'bedtime', label: '취침', min: '21:00', max: '03:00', step_minutes: 30, default: '23:00' },
      { key: 'wake', label: '기상', min: '05:00', max: '11:00', step_minutes: 30, default: '07:00' },
    ] },
    { question_id: 'q02', section: 'life', type: 'choice', title: '잠잘 때 소리에 얼마나 예민해요?', options: [
      { value: 'insensitive', label: '둔감' }, { value: 'normal', label: '보통' },
      { value: 'sensitive', label: '예민' }, { value: 'very_sensitive', label: '아주 예민' },
    ] },
    { question_id: 'q03', section: 'life', type: 'choice', title: '시험 기간에는 생활 리듬이 어떻게 달라져요?', options: [
      { value: 'same', label: '그대로예요' }, { value: 'earlier', label: '더 일찍 자요' },
      { value: 'later', label: '더 늦게 자요' }, { value: 'all_nighter', label: '밤새는 날이 많아요' },
    ] },
    { question_id: 'q04', section: 'life', type: 'choice', title: '내 자리는 얼마나 자주 정리해요?', options: [
      { value: 'daily', label: '매일' }, { value: 'every_2_3_days', label: '2~3일에 한 번' },
      { value: 'weekly', label: '일주일에 한 번' }, { value: 'when_needed', label: '생각날 때' },
    ] },
    { question_id: 'q05', section: 'life', type: 'choice', title: '설거지나 쓰레기는 언제 처리해요?', options: [
      { value: 'right_away', label: '바로' }, { value: 'same_day', label: '그날 안에' },
      { value: 'batch', label: '모아서 한 번에' }, { value: 'when_piled', label: '쌓이면' },
    ] },
    { question_id: 'q06', section: 'life', type: 'choice', title: '방 온도는 어떤 게 좋아요?', options: [
      { value: 'warm', label: '따뜻하게' }, { value: 'moderate', label: '적당히' },
      { value: 'cool', label: '시원하게' }, { value: 'any', label: '상관없어요' },
    ] },
    { question_id: 'q07', section: 'life', type: 'choice', title: '방에서 룸메이트와 어느 정도 어울리고 싶어요?', options: [
      { value: 'quietly_separate', label: '각자 조용히' }, { value: 'when_needed', label: '필요할 때만 대화' },
      { value: 'sometimes', label: '가끔 수다 · 같이 밥' }, { value: 'often', label: '친구처럼 자주' },
    ] },
    { question_id: 'q08', section: 'life', type: 'choice', title: '휴지 · 세제 같은 공용품과 음식은 어떻게 쓰는 게 좋아요?', options: [
      { value: 'all_separate', label: '전부 각자' }, { value: 'supplies_only', label: '공용품만 같이' },
      { value: 'ask_first', label: '물어보고 나눠 써요' }, { value: 'share_freely', label: '자유롭게 같이' },
    ] },
    { question_id: 'q09', section: 'situation', type: 'choice', title: '룸메이트가 새벽 1시에 친구와 통화하고 있어요', hint: '정답은 없어요. 내 AI가 시뮬레이션에서 나처럼 대화하도록 쓰여요.', options: [
      { value: 'say_now', label: '“조금만 작게 해줄래?” 바로 말한다', style: 'direct' },
      { value: 'earplugs', label: '이어폰을 끼고 그냥 잔다', style: 'avoid' },
      { value: 'talk_tomorrow', label: '참았다가 다음 날 이야기한다', style: 'delay' },
      { value: 'step_out', label: '잠깐 밖에 나가 있는다', style: 'avoid' },
    ] },
    { question_id: 'q10', section: 'situation', type: 'choice', title: '냉장고에 둔 내 반찬이 말없이 줄어 있어요', options: [
      { value: 'ask_now', label: '먹었는지 바로 물어본다', style: 'direct' },
      { value: 'let_go', label: '그냥 넘어간다', style: 'avoid' },
      { value: 'wait_and_talk', label: '몇 번 더 지켜보고 말한다', style: 'delay' },
      { value: 'label_food', label: '이름 스티커만 붙여 둔다', style: 'avoid' },
    ] },
    { question_id: 'q11', section: 'situation', type: 'choice', title: '룸메이트가 2주째 청소 당번을 안 했어요', options: [
      { value: 'say_now', label: '오늘 해 달라고 바로 말한다', style: 'direct' },
      { value: 'do_it', label: '내가 그냥 한다', style: 'avoid' },
      { value: 'talk_next_time', label: '다음 당번 정할 때 이야기한다', style: 'delay' },
      { value: 'leave_note', label: '메모를 남겨 둔다', style: 'delay' },
    ] },
    { question_id: 'q12', section: 'situation', type: 'choice', title: '룸메이트가 말없이 친구를 데려와 밤 11시까지 있어요', options: [
      { value: 'say_now', label: '미리 말해 달라고 바로 이야기한다', style: 'direct' },
      { value: 'let_stay', label: '불편해도 그냥 둔다', style: 'avoid' },
      { value: 'after_friend_leaves', label: '친구가 간 뒤에 이야기한다', style: 'delay' },
      { value: 'step_out', label: '밖에 나가 있다가 들어온다', style: 'avoid' },
    ] },
  ],
};
