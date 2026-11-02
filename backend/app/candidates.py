# 기능: 시드 후보를 검증하고 생활 성향 사전 점수 상위 6명을 추린다.
# 시스템 범위: 후보 조회 전용이며 DB 변경·엔진 호출·시뮬레이션은 수행하지 않는다.
# 결과: 익명 후보 카드 또는 필수 데이터 오류를 반환한다.
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


# 백분율 정수 가중치로 부동소수점 오차와 Python round의 짝수 반올림을 피한다.
WEIGHTS = {'sleep_rhythm': 30, 'noise_sensitivity': 25, 'cleanliness': 20,
           'sociability': 15, 'sharing_tolerance': 10}
# 후보 카드 한 줄 요약용 축 이름 (예: "청결 기준 비슷")
HIGHLIGHT_NAMES = {'sleep_rhythm': '수면 리듬', 'noise_sensitivity': '소음 민감도',
                   'cleanliness': '청결 기준', 'sociability': '사교성', 'sharing_tolerance': '공유 성향'}
Nonempty = Annotated[str, Field(min_length=1, pattern=r'\S')]
# 추천 후보 수와 별칭(후보 A~F). 시뮬레이션 별칭 검증 · 리포트 응답도 이 목록을 사용한다.
MAX_CANDIDATES = 6
ALIASES = tuple(f'후보 {letter}' for letter in 'ABCDEF')


class SeedCandidate(BaseModel):
    model_config = ConfigDict(strict=True)
    persona_id: Nonempty
    user_id: Nonempty
    candidate_pool: bool
    is_seed: bool


class CandidateProgress(BaseModel):
    done: int = Field(ge=0)
    total: int = Field(ge=1)


class CandidateSimulation(BaseModel):
    simulation_id: str
    status: Literal['queued', 'running', 'completed', 'failed']
    progress: CandidateProgress
    score: int | None


class CandidateResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    candidate_id: Nonempty
    alias: str
    department: Nonempty
    year: int = Field(ge=1, le=4)
    type_name: Nonempty
    pre_score: int = Field(ge=0, le=100)
    highlight: str
    simulation: CandidateSimulation | None = None


class CandidatesResponse(BaseModel):
    candidates: list[CandidateResponse] = Field(max_length=MAX_CANDIDATES)


def validate_axes(axes: dict) -> None:
    if (not isinstance(axes, dict) or set(axes) != set(WEIGHTS)
            or any(type(value) is not int or not 0 <= value <= 100 for value in axes.values())):
        raise ValueError('후보 점수에는 0~100 정수인 5개 축이 모두 필요합니다.')


def pre_score(me: dict, other: dict) -> int:
    validate_axes(me)
    validate_axes(other)
    hundredths = 10000 - sum(weight * abs(me[axis] - other[axis])
                            for axis, weight in WEIGHTS.items())
    return (hundredths + 50) // 100


def highlight_text(axis: str, gap: int) -> str:
    """가장 가까운 축을 사람이 읽는 문구로: 10점 이하 '비슷', 25점 이하 '비교적 비슷', 그 이상은 차이 점수."""
    name = HIGHLIGHT_NAMES[axis]
    if gap <= 10:
        return f'{name} 비슷'
    if gap <= 25:
        return f'{name} 비교적 비슷'
    return f'{name} 차이 {gap}점'


def select_candidates(me: dict, seed_path: Path) -> CandidatesResponse:
    """반올림 점수 내림차순, 동점은 ID 오름차순. 부족하면 0~5명 반환.

    시드 손상은 전체 요청 실패로 처리하여 누락 후보를 조용히 제외하지 않는다.
    highlight는 원본 소개 대신 실제 축 차이를 표시하여 개인정보를 전달하지 않는다.
    """
    validate_axes(me['axes'])
    seeds = json.loads(seed_path.read_text(encoding='utf-8'))['personas']
    if not isinstance(seeds, list):
        raise ValueError('시드 personas는 목록이어야 합니다.')
    cards = []
    seen = set()
    nickname = me.get('nickname') or ''
    for raw in seeds:
        seed = SeedCandidate.model_validate(raw)
        if seed.persona_id in seen or not seed.is_seed:
            raise ValueError('시드 ID 중복 또는 시드 표시 오류입니다.')
        seen.add(seed.persona_id)
        # 닉네임에 후보 실명이 들어 있으면 익명 치환이 사용자 이름까지 바꾸므로(다은이 → 후보 A이) 후보에서 제외
        if (not seed.candidate_pool or seed.persona_id == me['persona_id']
                or seed.user_id == me['user_id']
                or any(name and name in nickname for name in (raw.get('name'), raw.get('nickname')))):
            continue
        score = pre_score(me['axes'], raw['axes'])
        closest = min(WEIGHTS, key=lambda axis: abs(me['axes'][axis] - raw['axes'][axis]))
        gap = abs(me['axes'][closest] - raw['axes'][closest])
        cards.append(CandidateResponse(
            candidate_id=seed.persona_id, alias='', department=raw['department'],
            year=raw['year'], type_name=raw['type_name'], pre_score=score,
            highlight=highlight_text(closest, gap), simulation=None))
    cards.sort(key=lambda card: (-card.pre_score, card.candidate_id))
    selected = cards[:MAX_CANDIDATES]
    for card, alias in zip(selected, ALIASES):
        card.alias = alias
    return CandidatesResponse(candidates=selected)
