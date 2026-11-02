# 기능: 궁합 진단 — 후보 풀 전체와의 사전 점수를 분석해 잘 맞는 후보가 적은 이유와 습관 조정 방안을 제시한다.
# 시스템 범위: 조회 전용이며 DB 변경 · 엔진 호출을 하지 않는다. 후보 개인 정보(이름 · 소개)는 응답에 포함하지 않는다.
# 결과: 잘 맞는 후보 수, 점수를 낮추는 생활 성향(원인), 성향을 조금 조정했을 때 늘어나는 후보 수를 반환한다.
import json
from pathlib import Path
from statistics import median

from app.candidates import HIGHLIGHT_NAMES, WEIGHTS, pre_score, validate_axes

GOOD_SCORE = 75     # 이 점수 이상을 '잘 맞는 후보'로 본다(시드 분포 기준 상위권)
ADJUST_STEP = 25    # '조금 조정'의 크기: 축 값(0~100)을 후보 풀 중앙값 쪽으로 최대 25만큼 이동

# 축 값이 후보 풀보다 높을 때(high) · 낮을 때(low)의 생활 습관 조정 제안
TIPS = {
    'sleep_rhythm': {
        'high': ('늦게 자는 편이에요', ['평일 취침 시간을 30분~1시간 앞당겨 보세요.',
                                     '늦게 깨어 있을 때는 개인 조명 · 이어폰을 사용해 주세요.']),
        'low': ('일찍 자는 편이에요', ['안대 · 귀마개를 준비해 상대의 늦은 귀가에 대비해 보세요.',
                                    '취침 시간을 미리 알려 소등 시각을 함께 정해 보세요.']),
    },
    'noise_sensitivity': {
        'high': ('소리에 예민한 편이에요', ['귀마개 · 백색소음으로 스스로 대비하는 방법을 먼저 마련해 보세요.',
                                       '허용할 수 있는 소음 시간대를 구체적으로 정해 두세요.']),
        'low': ('소리에 무던한 편이에요', ['통화 · 영상은 이어폰을 쓰거나 방 밖에서 해 주세요.',
                                      '밤 11시 이후에는 생활 소음을 줄여 주세요.']),
    },
    'cleanliness': {
        'high': ('청결 기준이 높은 편이에요', ['공용 공간만 기준을 맞추고 개인 공간은 각자 관리해 보세요.',
                                         '청소 당번표로 기준을 말 대신 규칙으로 나눠 보세요.']),
        'low': ('정리를 미루는 편이에요', ['설거지는 당일, 쓰레기는 주 2회 이상 비워 주세요.',
                                      '공용 공간 정리 시각을 하나 정해 지켜 보세요.']),
    },
    'sociability': {
        'high': ('사람을 자주 부르는 편이에요', ['친구 초대는 하루 전 알리고 한 달 횟수를 정해 보세요.',
                                          '룸메이트의 혼자 있는 시간도 일정으로 존중해 주세요.']),
        'low': ('혼자 있는 시간을 중시해요', ['가벼운 인사와 일정 공유 정도는 먼저 건네 보세요.',
                                         '혼자 있고 싶은 시간을 미리 말해 두면 오해가 줄어요.']),
    },
    'sharing_tolerance': {
        'high': ('물건을 함께 쓰는 데 익숙해요', ['상대 물건은 쓰기 전에 꼭 물어보세요.',
                                            '공용으로 둘 물건과 개인 물건을 처음에 나눠 두세요.']),
        'low': ('물건을 따로 쓰는 편이에요', ['휴지 · 세제 같은 소모품은 함께 사서 나눠 보세요.',
                                         '빌려줄 수 있는 물건 목록을 정해 두면 부딪힘이 줄어요.']),
    },
}


def _pool(me: dict, seed_path: Path) -> list[dict]:
    seeds = json.loads(seed_path.read_text(encoding='utf-8'))['personas']
    return [raw for raw in seeds if raw.get('candidate_pool') is True
            and raw['persona_id'] != me['persona_id'] and raw.get('user_id') != me['user_id']]


def _good_count(axes: dict, pool: list[dict]) -> int:
    return sum(1 for raw in pool if pre_score(axes, raw['axes']) >= GOOD_SCORE)


def _adjusted(axes: dict, centers: dict, targets) -> dict:
    """지정한 축들을 후보 풀 중앙값 쪽으로 최대 ADJUST_STEP만큼 옮긴 성향."""
    moved = dict(axes)
    for axis in targets:
        step = min(ADJUST_STEP, abs(axes[axis] - centers[axis]))
        moved[axis] = round(axes[axis] - step if axes[axis] > centers[axis] else axes[axis] + step)
    return moved


def diagnose(me: dict, seed_path: Path) -> dict:
    validate_axes(me['axes'])
    axes = me['axes']
    pool = _pool(me, seed_path)
    scores = sorted((pre_score(axes, raw['axes']) for raw in pool), reverse=True)
    good = _good_count(axes, pool)
    level = 'good' if good >= 3 else ('limited' if good >= 1 else 'hard')
    if not pool:
        return {'pool_size': 0, 'good_score': GOOD_SCORE, 'good_count': 0, 'level': 'hard',
                'best_score': None, 'factors': [], 'best_adjustment': None}
    centers = {axis: median(raw['axes'][axis] for raw in pool) for axis in WEIGHTS}
    factors = []
    for axis, weight in WEIGHTS.items():
        gaps = [abs(axes[axis] - raw['axes'][axis]) for raw in pool]
        # 점수 손실: 이 축 차이로 평균 몇 점이 깎이는지(가중치 반영)
        loss = round(weight * sum(gaps) / len(gaps) / 100, 1)
        offset = axes[axis] - centers[axis]
        if abs(offset) < 15:
            summary, tips = '후보들과 비슷한 편이에요', []
        else:
            summary, tips = TIPS[axis]['high' if offset > 0 else 'low']
        factors.append({
            'axis': axis, 'label': HIGHLIGHT_NAMES[axis], 'summary': summary,
            'my_value': axes[axis], 'pool_median': round(centers[axis]),
            'far_count': sum(1 for gap in gaps if gap >= 40), 'score_loss': loss, 'tips': tips,
            'good_after_adjust': _good_count(_adjusted(axes, centers, [axis]), pool),
        })
    factors.sort(key=lambda item: (-item['score_loss'], item['axis']))
    # 조정 제안: 한 가지 습관으로 늘어나면 그 축, 아니면 손실 상위 2~3개 축을 함께 조정
    adjustment = None
    single = max(factors, key=lambda item: (item['good_after_adjust'], item['score_loss']))
    if single['good_after_adjust'] > good:
        adjustment = [single]
    else:
        for size in (2, 3):
            chosen = [item for item in factors if item['tips']][:size]
            after = _good_count(_adjusted(axes, centers, [item['axis'] for item in chosen]), pool)
            if len(chosen) == size and after > good:
                adjustment = chosen
                single = {'good_after_adjust': after}
                break
    return {
        'pool_size': len(pool), 'good_score': GOOD_SCORE, 'good_count': good, 'level': level,
        'best_score': scores[0],
        'factors': factors[:3],
        'best_adjustment': ({'axes': [item['axis'] for item in adjustment],
                             'labels': [item['label'] for item in adjustment],
                             'good_before': good, 'good_after': single['good_after_adjust']}
                            if adjustment else None),
    }
