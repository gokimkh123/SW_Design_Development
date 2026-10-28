"""시드 인물(data/seed/personas.json): API.md 3장 형식, PRD 부록 C 산식, PRD 4장 설계 조건 검증."""

import json

import pytest

from app import fake_engine
from conftest import HANEUL_ANSWERS

PERSONAS_PATH = fake_engine.SEED_DIR / "personas.json"

# API.md 3장 Persona 필드 중 시드 파일에 두는 것 (created_at 은 적재 시 부여)
PERSONA_KEYS = {
    "persona_id", "user_id", "nickname", "type_name", "summary", "sleep", "axes", "axis_labels",
    "conflict_style", "preferences", "must_keep", "okay_with", "is_seed",
}
# 시드 전용 필드: 매칭 후 공개 정보(name · greeting), 후보 카드(department · year), 후보 풀 포함 여부, 원본 응답
SEED_ONLY_KEYS = {"name", "department", "year", "greeting", "candidate_pool", "answers"}

WEIGHTS = {"sleep_rhythm": 0.3, "noise_sensitivity": 0.25, "cleanliness": 0.2, "sociability": 0.15, "sharing_tolerance": 0.1}


def _load():
    return json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))["personas"]


PERSONAS = _load()
BY_ID = {p["persona_id"]: p for p in PERSONAS}


def pre_score(me, other):
    """PRD 부록 C 후보 1차 점수 (설계 검증용. 실제 후보 추림 구현은 일준 담당)."""
    gap = sum(w * abs(me["axes"][a] - other["axes"][a]) for a, w in WEIGHTS.items())
    return fake_engine.round_half_up(100 - gap)


def test_eleven_personas_with_ten_candidates():
    assert len(PERSONAS) == 11
    assert len(BY_ID) == 11
    pool = [p for p in PERSONAS if p["candidate_pool"]]
    assert len(pool) == 10
    assert [p["persona_id"] for p in PERSONAS if not p["candidate_pool"]] == ["per_haneul"]


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p["persona_id"])
def test_fields_and_ids(persona):
    assert set(persona) == PERSONA_KEYS | SEED_ONLY_KEYS
    assert persona["persona_id"].startswith("per_") and persona["user_id"].startswith("usr_")
    assert persona["is_seed"] is True
    assert persona["nickname"] == persona["name"]
    assert 1 <= len(persona["must_keep"]) <= 3 and len(persona["okay_with"]) <= 3
    assert all(len(item) <= 30 for item in persona["must_keep"] + persona["okay_with"])
    if persona["candidate_pool"]:
        assert persona["department"] and persona["year"] in (1, 2, 3, 4) and persona["greeting"]


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p["persona_id"])
def test_derived_fields_match_answers(persona):
    answers = persona["answers"]
    assert set(answers) == {f"q{i:02d}" for i in range(1, 13)}
    assert persona["axes"] == fake_engine.compute_axes(answers)
    assert persona["axis_labels"] == fake_engine.axis_labels(persona["axes"])
    assert persona["conflict_style"] == fake_engine.conflict_style(answers)
    assert persona["sleep"] == {**answers["q01"], "exam_pattern": answers["q03"]}
    assert persona["preferences"] == {"temperature": answers["q06"]}


def test_haneul_matches_api_example():
    haneul = BY_ID["per_haneul"]
    assert haneul["answers"] == HANEUL_ANSWERS
    assert haneul["type_name"] == "규칙적인 아침형"
    assert haneul["summary"] == "23시 취침 · 6시 반 기상. 불편하면 바로, 부드럽게 말하는 편."
    assert haneul["must_keep"] == ["24시 이후 통화·게임 소리 X"]
    assert haneul["okay_with"] == ["친구 초대 (미리 말하면)"]


def test_daeun_axes_match_api_comparison_example():
    assert BY_ID["per_daeun"]["axes"] == {
        "sleep_rhythm": 25, "noise_sensitivity": 67, "cleanliness": 100, "sociability": 33, "sharing_tolerance": 33,
    }


def test_haneul_top3_are_subin_daeun_jiho():
    """PRD 4장: 하늘 기준 상위 3명이 수빈 · 다은 · 지호가 되도록 설계."""
    haneul = BY_ID["per_haneul"]
    ranked = sorted(
        (p for p in PERSONAS if p["candidate_pool"]),
        key=lambda p: (-pre_score(haneul, p), p["persona_id"]),
    )
    assert {p["persona_id"] for p in ranked[:3]} == {"per_subin", "per_daeun", "per_jiho"}
    assert pre_score(haneul, ranked[2]) > pre_score(haneul, ranked[3])


def test_golden_pair_characteristics():
    """PRD 8.7 골든 페어: 하늘-수빈 수면 차이 큼, 하늘-다은 원만."""
    haneul, subin, daeun = BY_ID["per_haneul"], BY_ID["per_subin"], BY_ID["per_daeun"]
    assert subin["axes"]["sleep_rhythm"] - haneul["axes"]["sleep_rhythm"] >= 50
    assert max(abs(daeun["axes"][a] - haneul["axes"][a]) for a in WEIGHTS) <= 33
