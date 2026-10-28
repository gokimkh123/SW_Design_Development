"""임시 가짜 엔진.

- 실제 엔진(engine 패키지) 완성 전까지 쓰는 백엔드 내부 대체 구현 (LLM 호출 없음, ENGINE_IMPL=fake)
- 함수 이름 · 시그니처는 docs/common/API.md 7장과 동일
- 5개 축 · 대화 방식: PRD 부록 C, 점수 · 한 줄 판정: PRD 8.5
- 대화 · 판정 · 규칙 문구는 축 차이 기반 고정 문구 (실제 엔진 결과 아님)
- engine_adapter 의 build_persona 실패 대체(규칙 기반 문구)에도 사용
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"

AXES = ("sleep_rhythm", "noise_sensitivity", "cleanliness", "sociability", "sharing_tolerance")

# 선택지 값 → 축 점수 (PRD 부록 C). 선택지 값은 survey.json 확정 전 임시 값 (frontend/src/mocks/survey.ts 기준)
NOISE = {"insensitive": 0, "normal": 33, "sensitive": 67, "very_sensitive": 100}
NOISE_LABELS = {0: "둔감", 33: "보통", 67: "예민", 100: "아주 예민"}
TIDY = {"daily": 100, "every_2_3_days": 67, "weekly": 33, "when_needed": 0}
DISHES = {"right_away": 100, "same_day": 67, "batch": 33, "when_piled": 0}
SOCIAL = {"quietly_separate": 0, "when_needed": 33, "sometimes": 67, "often": 100}
SHARING = {"all_separate": 0, "supplies_only": 33, "ask_first": 67, "share_freely": 100}

# 상황 질문 선택지 → 대화 방식 (survey.json 이 있으면 그 파일의 style 우선)
DEFAULT_STYLES = {
    "q09": {"say_now": "direct", "earplugs": "avoid", "talk_tomorrow": "delay", "step_out": "avoid"},
    "q10": {"ask_now": "direct", "let_go": "avoid", "wait_and_talk": "delay", "label_food": "avoid"},
    "q11": {"say_now": "direct", "do_it": "avoid", "talk_next_time": "delay", "leave_note": "delay"},
    "q12": {"say_now": "direct", "let_stay": "avoid", "after_friend_leaves": "delay", "step_out": "avoid"},
}
SITUATION_QUESTIONS = ("q09", "q10", "q11", "q12")

AREA_LABELS = {
    "quiet_hours": "조용한 시간",
    "guests": "친구 초대",
    "cleaning": "청소",
    "fridge": "냉장고",
    "climate": "냉난방",
    "supplies": "공용품",
}

# PRD 부록 B. data/seed/scenes.json 이 생기면 그 파일 우선
# (scene_id, day, weekday, time, category, title, situation, rule_area, related_axes)
_DEFAULT_SCENES = [
    ("S01", 1, "월", "06:30", "수면·소음", "이른 알람", "{A}의 알람이 6시 반에 여러 번 울리고, {B}는 아직 자는 중", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
    ("S02", 1, "월", "07:30", "수면·소음", "드라이기 소음", "{B}가 방 안에서 드라이기를 쓰고, {A}는 1교시가 없어 더 자려는 중", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
    ("S03", 1, "월", "23:30", "환경", "조명", "{A}는 자려고 누웠는데 {B}의 책상 조명이 켜져 있음", "quiet_hours", ["sleep_rhythm"]),
    ("S04", 2, "화", "00:40", "수면·소음", "새벽 통화", "{B}가 친구와 통화 중, {A}는 내일 아침 수업", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
    ("S05", 2, "화", "19:30", "청결·청소", "설거지 미루기", "싱크대에 {B}의 그릇이 이틀째 쌓여 있음", "cleaning", ["cleanliness"]),
    ("S06", 2, "화", "22:00", "환경", "난방 온도", "{A}와 {B}가 원하는 방 온도가 다름", "climate", []),
    ("S07", 3, "수", "19:00", "방문객", "친구 초대", "{B}가 오늘 저녁 친구를 데려와도 되는지 물어봄", "guests", ["sociability"]),
    ("S08", 3, "수", "21:30", "환경", "환기", "방 공기가 답답한데 창문을 열지 의견이 갈림", "climate", []),
    ("S09", 3, "수", "01:10", "수면·소음", "심야 게임", "{B}가 친구와 음성 채팅으로 게임 중, {A}는 내일 9시 수업", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
    ("S10", 4, "목", "08:00", "청결·청소", "욕실 머리카락", "욕실 배수구에 머리카락이 쌓여 있음", "cleaning", ["cleanliness"]),
    ("S11", 4, "목", "18:00", "공용 물품", "휴지·세제 소진", "휴지와 세제가 동시에 떨어짐", "supplies", ["sharing_tolerance"]),
    ("S12", 4, "목", "01:30", "방문객", "늦은 귀가", "{B}가 새벽 1시 반에 귀가하며 문을 여는 소리가 남", "guests", ["sleep_rhythm", "noise_sensitivity"]),
    ("S13", 5, "금", "15:00", "공용 물품", "물건 무단 사용", "{B}가 {A}의 드라이기를 말없이 씀", "supplies", ["sharing_tolerance"]),
    ("S14", 5, "금", "18:30", "공용 물품", "냉장고 반찬", "냉장고에 둔 {A}의 반찬이 줄어 있음", "fridge", ["sharing_tolerance"]),
    ("S15", 5, "금", "21:00", "방문객", "연인 방문", "{B}가 주말에 연인을 방에 데려와도 되는지 물어봄", "guests", ["sociability"]),
    ("S16", 6, "토", "11:00", "특수 기간", "주말 늦잠", "{A}는 오전 청소를 원하고 {B}는 주말 늦잠 중", "cleaning", ["sleep_rhythm", "cleanliness"]),
    ("S17", 6, "토", "14:00", "청결·청소", "청소 당번", "이번 주 청소 당번을 정해야 함", "cleaning", ["cleanliness"]),
    ("S18", 6, "토", "16:00", "공용 물품", "공과금 분담", "공용품 · 공과금을 어떻게 나눌지 정해야 함", "supplies", ["sharing_tolerance"]),
    ("S19", 7, "일", "20:00", "특수 기간", "실습 주간", "{A}가 다음 주 실습이라 일찍 자야 함", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
    ("S20", 7, "일", "22:30", "특수 기간", "시험 기간", "시험 기간이라 둘 다 밤늦게까지 공부 중", "quiet_hours", ["sleep_rhythm", "noise_sensitivity"]),
]

# 판정별 고정 문구 (영역 → (합의안, 규칙 후보))
_AREA_AGREEMENTS = {
    "quiet_hours": ("23:30 이후 소리 줄이기, 늦게까지 깨어 있으면 헤드셋", "23:30 ~ 07:00 조용한 시간"),
    "guests": ("하루 전 미리 말하고 22시까지", "하루 전 공지 · 22시까지"),
    "cleaning": ("주말 오후에 같이 청소", "일요일 14시 청소 · 격주 화장실 당번"),
    "fridge": ("칸을 나누고 공용 칸은 주 1회 정리", "칸 나누기 · 공용 칸 주 1회 정리"),
    "climate": ("밤에는 23도로 맞추기", "밤 23도 · 외출 시 끄기"),
    "supplies": ("공용품은 번갈아 사기", "휴지·세제 번갈아 구매"),
}

_VERDICT_REASONS = {
    "harmonious": "생활 기준이 비슷해 쉽게 합의",
    "negotiated": "기준 차이가 있었으나 서로 양보해 합의",
    "conflict": "기준 차이가 커서 합의하지 못함",
}

HEADLINES = (
    (85, "함께 살기 무난한 조합이에요"),
    (70, "몇 가지만 맞추면 잘 지낼 수 있어요"),
    (50, "미리 규칙을 꼭 정해 두는 게 좋아요"),
    (0, "생활 방식 차이가 커요"),
)

SEVERITY = {"conflict": 0, "negotiated": 1, "harmonious": 2}


def round_half_up(value: float) -> int:
    """사사오입 반올림 (Python round 의 은행가 반올림 대신)."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def sleep_rhythm(bedtime: str) -> int:
    """취침 21:00 → 0, 03:00 → 100 선형. 범위 밖은 가까운 쪽 끝값."""
    offset = (_minutes(bedtime) - 21 * 60) % (24 * 60)
    if offset <= 6 * 60:
        return round_half_up(offset / 360 * 100)
    # 03:00 ~ 21:00 사이: 오전은 늦게 잔 쪽(100), 오후는 일찍 잔 쪽(0)
    return 100 if _minutes(bedtime) < 12 * 60 else 0


def compute_axes(answers: dict) -> dict[str, int]:
    return {
        "sleep_rhythm": sleep_rhythm(answers["q01"]["bedtime"]),
        "noise_sensitivity": NOISE[answers["q02"]],
        "cleanliness": round_half_up((TIDY[answers["q04"]] + DISHES[answers["q05"]]) / 2),
        "sociability": SOCIAL[answers["q07"]],
        "sharing_tolerance": SHARING[answers["q08"]],
    }


def _level(value: int) -> str:
    if value <= 24:
        return "낮음"
    return "보통" if value <= 74 else "높음"


def axis_labels(axes: dict[str, int]) -> dict[str, str]:
    sleep = axes["sleep_rhythm"]
    return {
        "sleep_rhythm": "아침형" if sleep <= 33 else ("중간형" if sleep <= 66 else "올빼미"),
        "noise_sensitivity": NOISE_LABELS.get(axes["noise_sensitivity"], _level(axes["noise_sensitivity"])),
        "cleanliness": _level(axes["cleanliness"]),
        "sociability": _level(axes["sociability"]),
        "sharing_tolerance": _level(axes["sharing_tolerance"]),
    }


def _situation_styles() -> dict[str, dict[str, str]]:
    path = SEED_DIR / "survey.json"
    if not path.exists():
        return DEFAULT_STYLES
    survey = json.loads(path.read_text(encoding="utf-8"))
    styles = {
        q["question_id"]: {o["value"]: o["style"] for o in q.get("options", []) if "style" in o}
        for q in survey["questions"]
        if q["question_id"] in SITUATION_QUESTIONS
    }
    return styles or DEFAULT_STYLES


def conflict_style(answers: dict) -> str:
    """q09 ~ q12 최빈 방식, 동점 시 q09 방식."""
    styles = _situation_styles()
    picked = [styles[q][answers[q]] for q in SITUATION_QUESTIONS]
    counts = Counter(picked)
    top = max(counts.values())
    if counts[picked[0]] == top:
        return picked[0]
    return next(style for style in picked if counts[style] == top)


def _type_name(labels: dict[str, str]) -> str:
    rhythm = {"아침형": "아침형", "중간형": "보통 리듬형", "올빼미": "올빼미형"}[labels["sleep_rhythm"]]
    trait = "깔끔한" if labels["cleanliness"] == "높음" else ("활발한" if labels["sociability"] == "높음" else "무난한")
    return f"{trait} {rhythm}"


_STYLE_PHRASES = {"direct": "불편하면 바로 말하는 편", "avoid": "웬만하면 넘어가는 편", "delay": "생각을 정리한 뒤 말하는 편"}


async def build_persona(nickname: str, answers: dict) -> dict:
    axes = compute_axes(answers)
    labels = axis_labels(axes)
    style = conflict_style(answers)
    bedtime, wake = answers["q01"]["bedtime"], answers["q01"]["wake"]
    must_keep = ["24시 이후 통화·게임 소리 X"] if axes["noise_sensitivity"] >= 67 else []
    if axes["cleanliness"] >= 75:
        must_keep.append("설거지는 그날 안에")
    okay_with = ["친구 초대 (미리 말하면)"] if axes["sociability"] >= 33 else []
    if axes["sharing_tolerance"] >= 67:
        okay_with.append("공용품 같이 쓰기")
    return {
        "nickname": nickname,
        "type_name": _type_name(labels),
        "summary": f"{bedtime} 취침 · {wake} 기상. {_STYLE_PHRASES[style]}.",
        "sleep": {"bedtime": bedtime, "wake": wake, "exam_pattern": answers["q03"]},
        "axes": axes,
        "axis_labels": labels,
        "conflict_style": style,
        "preferences": {"temperature": answers["q06"]},
        "must_keep": must_keep[:3],
        "okay_with": okay_with[:3],
    }


def load_scenes() -> list[dict]:
    path = SEED_DIR / "scenes.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    keys = ("scene_id", "day", "weekday", "time", "category", "title", "situation", "rule_area", "related_axes")
    return [dict(zip(keys, row)) for row in _DEFAULT_SCENES]


def _judge(scene: dict, me: dict, candidate: dict) -> str:
    if scene["rule_area"] == "climate":
        mine, theirs = me["preferences"]["temperature"], candidate["preferences"]["temperature"]
        return "harmonious" if mine == theirs or "any" in (mine, theirs) else "negotiated"
    gap = max((abs(me["axes"][a] - candidate["axes"][a]) for a in scene["related_axes"]), default=0)
    if gap <= 20:
        return "harmonious"
    return "negotiated" if gap <= 50 else "conflict"


async def simulate(me: dict, candidate: dict, *, mode: str = "agents") -> AsyncIterator[dict]:
    """장면마다 scene_started → utterance 2개 → scene_judged. mode 는 무시."""
    scenes = load_scenes()
    total = len(scenes)
    me_name, other_name = f"{me['nickname']} AI", f"{candidate['nickname']} AI"
    for index, scene in enumerate(scenes, start=1):
        situation = scene["situation"].replace("{A}", me["nickname"]).replace("{B}", candidate["nickname"])
        public_scene = {k: scene[k] for k in ("scene_id", "day", "weekday", "time", "category", "title")}
        public_scene["situation"] = situation
        yield {"type": "scene_started", "data": {"scene_index": index, "scene": public_scene}}

        verdict = _judge(scene, me, candidate)
        agreement, rule_text = _AREA_AGREEMENTS[scene["rule_area"]]
        lines = [
            ("me", me_name, f"{scene['title']} 얘기인데, 우리 기준을 한번 맞춰 볼까?"),
            ("candidate", other_name, "좋아. 나는 이렇게 하면 괜찮을 것 같아." if verdict != "conflict" else "음… 나는 지금 방식이 편한데."),
        ]
        for turn, (speaker, name, text) in enumerate(lines, start=1):
            yield {"type": "utterance", "data": {"scene_index": index, "turn": turn, "speaker": speaker, "name": name, "text": text}}
            await asyncio.sleep(0)

        settled = verdict != "conflict"
        yield {
            "type": "scene_judged",
            "data": {
                "scene_index": index,
                "verdict": verdict,
                "reason": _VERDICT_REASONS[verdict],
                "agreement": agreement,  # 충돌 장면도 판정자의 합의안 제시 (PRD 5장 판정 정의)
                "rule_candidate": {"area": scene["rule_area"], "text": rule_text},
                "unresolved": None if settled else f"{scene['title']} 기준 차이",
                "progress": {"done": index, "total": total},
            },
        }


def _verdict_of(judgement: Any) -> str:
    return judgement["verdict"] if isinstance(judgement, dict) else judgement.verdict


def score(judgements: Iterable[Any]) -> int:
    """round(100 × (원만 + 0.5 × 조율) / 판정된 장면 수). 판정 보류는 분모 제외, 판정 장면이 없으면 0."""
    verdicts = [_verdict_of(j) for j in judgements]
    judged = [v for v in verdicts if v != "pending"]
    if not judged:
        return 0
    points = judged.count("harmonious") + 0.5 * judged.count("negotiated")
    return round_half_up(100 * points / len(judged))


def headline(score: int) -> str:
    return next(text for floor, text in HEADLINES if score >= floor)


async def draft_rules(me: dict, candidate: dict, judgements: list[dict]) -> list[dict]:
    """6개 영역마다 규칙 1개. 근거 장면은 충돌 → 조율 → 원만, 같은 판정은 장면 순."""
    scenes = load_scenes()
    by_index = {i: s for i, s in enumerate(scenes, start=1)}
    rules = []
    for area, label in AREA_LABELS.items():
        related = [
            j for j in judgements
            if j.get("verdict") in SEVERITY and (j.get("rule_candidate") or {}).get("area", by_index[j["scene_index"]]["rule_area"]) == area
        ]
        if related:
            source = min(related, key=lambda j: (SEVERITY[j["verdict"]], j["scene_index"]))
            text = (source.get("rule_candidate") or {}).get("text") or _AREA_AGREEMENTS[area][1]
            src = {"scene_index": source["scene_index"], "day": by_index[source["scene_index"]]["day"], "verdict": source["verdict"]}
        else:
            index = next(i for i, s in by_index.items() if s["rule_area"] == area)
            text = _AREA_AGREEMENTS[area][1]
            src = {"scene_index": index, "day": by_index[index]["day"], "verdict": "pending"}
        rules.append({"area": area, "area_label": label, "text": text, "source": src})
    return rules


async def mediate(rule: dict, proposal_text: str, reason: str, proposer: dict, other: dict) -> dict:
    return {
        "text": f"{proposal_text}, 대신 상대가 불편한 시간대는 서로 미리 알리기",
        "rationale": [f"{proposer['nickname']}의 사유: {reason}", f"기존 규칙({rule['text']})의 취지 유지"],
    }


async def rephrase(memo: str, sender: dict, receiver: dict) -> dict:
    return {
        "message": "요즘 조금 신경 쓰이는 게 있어서 😅 같이 방법을 정해 볼 수 있을까?",
        "suggested_rule": {"area": "quiet_hours", "text": "서로 불편한 점은 그날 안에 부드럽게 말하기"},
    }
