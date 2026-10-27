import type { Report, Verdict } from '../api/types';

export const verdictLabel: Record<Verdict, string> = {
  harmonious: '원만',
  negotiated: '조율',
  conflict: '충돌',
  pending: '판정 보류',
};

export function conflictsDisplay(report: Report): string {
  return report.expected_conflicts_per_month == null
    ? '아직 제공하지 않아요'
    : `월 ${report.expected_conflicts_per_month}회 예상`;
}
