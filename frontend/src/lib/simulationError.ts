import { ApiError } from '../api/real';

export function simulationStartErrorText(error: unknown, isMock: boolean): string {
  if (!isMock && error instanceof ApiError && error.status === 404
      && (error.code === 'VALIDATION_ERROR' || error.message.includes('요청 경로, 메서드 또는 형식을 확인'))) {
    return '시뮬레이션 시작 API는 아직 준비 중이에요. 다시 시도해 주세요.';
  }
  return error instanceof Error ? error.message : '요청에 실패했어요. 다시 시도해 주세요.';
}
