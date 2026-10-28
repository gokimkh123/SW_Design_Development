"""임시 가짜 엔진: PRD 부록 C · 8.5 산식과 API.md 3 · 5장 형식 검증."""

import asyncio

import pytest

from app import fake_engine
from conftest import HANEUL_ANSWERS

# API.md 3장 Persona 중 엔진이 채우는 필드 (ID · is_seed · created_at 은 백엔드 부여)
ENGINE_PERSONA_KEYS = {
    "nickname", "type_name", "summary", "sleep", "axes", "axis_labels",
    "conflict_style", "preferences", "must_keep", "okay_with",
}


def _persona(answers=HANEUL_ANSWERS, nickname="하늘"):
    return asyncio.run(fake_engine.build_persona(nickname, answers))


def _collect(me, candidate):
    async def run():
        return [e async for e in fake_engine.simulate(me, candidate)]
    return asyncio.run(run())


def test_haneul_persona_matches_api_example():
    persona = _persona()
    assert set(persona) == ENGINE_PERSONA_KEYS
    assert persona["axes"] == {
        "sleep_rhythm": 33, "noise_sensitivity": 67, "cleanliness": 84,
        "sociability": 33, "sharing_tolerance": 0,
    }
    assert persona["axis_labels"] == {
        "sleep_rhythm": "아침형", "noise_sensitivity": "예민", "cleanliness": "높음",
        "sociability": "보통", "sharing_tolerance": "낮음",
    }
    assert persona["conflict_style"] == "direct"
    assert persona["sleep"] == {"bedtime": "23:00", "wake": "06:30", "exam_pattern": "earlier"}
    assert persona["preferences"] == {"temperature": "moderate"}
    assert len(persona["must_keep"]) <= 3 and len(persona["okay_with"]) <= 3


@pytest.mark.parametrize(
    "bedtime, expected",
    [("21:00", 0), ("00:00", 50), ("03:00", 100), ("04:00", 100), ("20:00", 0), ("23:00", 33), ("01:00", 67)],
)
def test_sleep_rhythm_linear_and_clamped(bedtime, expected):
    assert fake_engine.sleep_rhythm(bedtime) == expected


def test_round_half_up_not_bankers():
    assert fake_engine.round_half_up(86.5) == 87
    assert fake_engine.round_half_up(87.5) == 88
    assert fake_engine.round_half_up(83.5) == 84


def test_conflict_style_tie_uses_q09():
    answers = {**HANEUL_ANSWERS, "q09": "earplugs", "q10": "ask_now", "q11": "say_now", "q12": "let_stay"}
    assert fake_engine.conflict_style(answers) == "avoid"


def test_conflict_style_majority():
    answers = {**HANEUL_ANSWERS, "q09": "talk_tomorrow", "q10": "let_go", "q11": "do_it", "q12": "step_out"}
    assert fake_engine.conflict_style(answers) == "avoid"


def test_score_matches_prd_example():
    judgements = [{"verdict": "harmonious"}] * 16 + [{"verdict": "negotiated"}] * 3 + [{"verdict": "conflict"}]
    assert fake_engine.score(judgements) == 88


def test_score_excludes_pending():
    judgements = [{"verdict": "harmonious"}] * 16 + [{"verdict": "pending"}] * 4
    assert fake_engine.score(judgements) == 100
    assert fake_engine.score([{"verdict": "pending"}]) == 0


@pytest.mark.parametrize(
    "score, text",
    [(100, "함께 살기 무난한 조합이에요"), (85, "함께 살기 무난한 조합이에요"),
     (84, "몇 가지만 맞추면 잘 지낼 수 있어요"), (70, "몇 가지만 맞추면 잘 지낼 수 있어요"),
     (69, "미리 규칙을 꼭 정해 두는 게 좋아요"), (50, "미리 규칙을 꼭 정해 두는 게 좋아요"),
     (49, "생활 방식 차이가 커요"), (0, "생활 방식 차이가 커요")],
)
def test_headline_thresholds(score, text):
    assert fake_engine.headline(score) == text


def test_load_scenes_twenty_in_order():
    scenes = fake_engine.load_scenes()
    assert [s["scene_id"] for s in scenes] == [f"S{i:02d}" for i in range(1, 21)]
    assert {s["rule_area"] for s in scenes} == set(fake_engine.AREA_LABELS)


def test_simulate_event_shapes_match_api_section5():
    me = _persona()
    other = _persona({**HANEUL_ANSWERS, "q01": {"bedtime": "02:00", "wake": "10:00"}, "q02": "insensitive"}, "후보 C")
    events = _collect(me, other)

    judged = [e["data"] for e in events if e["type"] == "scene_judged"]
    assert len(judged) == 20
    assert judged[-1]["progress"] == {"done": 20, "total": 20}

    first_scene = events[:4]
    assert [e["type"] for e in first_scene] == ["scene_started", "utterance", "utterance", "scene_judged"]
    assert set(first_scene[0]["data"]) == {"scene_index", "scene"}
    assert set(first_scene[0]["data"]["scene"]) == {"scene_id", "day", "weekday", "time", "category", "title", "situation"}
    assert set(first_scene[1]["data"]) == {"scene_index", "turn", "speaker", "name", "text"}
    assert set(judged[0]) == {"scene_index", "verdict", "reason", "agreement", "rule_candidate", "unresolved", "progress"}

    # 축 차이가 큰 수면 장면(S09)은 충돌, 후보 이름 대신 넘겨받은 별칭 사용
    s09 = next(e["data"] for e in events if e["type"] == "scene_started" and e["data"]["scene"]["scene_id"] == "S09")
    assert "후보 C" in s09["scene"]["situation"] and "{" not in s09["scene"]["situation"]
    assert judged[8]["verdict"] == "conflict"
    assert judged[8]["agreement"] and judged[8]["unresolved"]  # 충돌도 합의안 제시, 미해결 항목 유지


def test_draft_rules_one_per_area_with_most_severe_source():
    me = _persona()
    events = _collect(me, me)
    judgements = [e["data"] for e in events if e["type"] == "scene_judged"]
    judgements[13] = {**judgements[13], "verdict": "conflict"}  # S14 냉장고

    rules = asyncio.run(fake_engine.draft_rules(me, me, judgements))
    assert [r["area"] for r in rules] == list(fake_engine.AREA_LABELS)
    assert all(set(r) == {"area", "area_label", "text", "source"} for r in rules)
    assert all(set(r["source"]) == {"scene_index", "day", "verdict"} for r in rules)
    fridge = next(r for r in rules if r["area"] == "fridge")
    assert fridge["source"] == {"scene_index": 14, "day": 5, "verdict": "conflict"}
