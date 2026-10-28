"""엔진 어댑터: 엔진 선택, 모델 변환, 오류 변환, 이벤트 검증."""

import asyncio
from types import SimpleNamespace

import pytest

from app import engine_adapter
from app.engine_adapter import EngineAdapter, EngineError, load_engine
from conftest import HANEUL_ANSWERS


class RateLimitError(Exception):
    """anthropic.RateLimitError 와 이름이 같은 대역."""


class APIConnectionError(Exception):
    """anthropic.APIConnectionError 와 이름이 같은 대역."""


class FakeModel:
    """Pydantic 모델 대역: model_validate · model_dump 만 흉내."""

    validated = []

    def __init__(self, data):
        self.data = data

    @classmethod
    def model_validate(cls, data):
        cls.validated.append(data)
        return cls(data)

    def model_dump(self, mode="python"):
        return dict(self.data)


def _failing_impl(exc):
    async def fail(*args, **kwargs):
        raise exc
    return SimpleNamespace(build_persona=fail, draft_rules=fail, mediate=fail, rephrase=fail)


def test_default_engine_is_fake_without_api_key(monkeypatch):
    monkeypatch.delenv("ENGINE_IMPL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine = load_engine()
    assert engine.name == "fake"
    persona = asyncio.run(engine.build_persona("하늘", HANEUL_ANSWERS))
    assert persona["axes"]["cleanliness"] == 84


def test_unknown_engine_impl_rejected():
    with pytest.raises(ValueError):
        load_engine("openai")


def test_get_engine_reads_env(monkeypatch):
    monkeypatch.setenv("ENGINE_IMPL", "fake")
    engine_adapter.get_engine.cache_clear()
    try:
        assert engine_adapter.get_engine().name == "fake"
    finally:
        engine_adapter.get_engine.cache_clear()


@pytest.mark.parametrize(
    "exc, code, status",
    [(RateLimitError("429"), "LLM_RATE_LIMITED", 429), (APIConnectionError("down"), "LLM_UNAVAILABLE", 503)],
)
def test_llm_errors_mapped_to_api_codes(exc, code, status):
    engine = EngineAdapter(_failing_impl(exc))
    with pytest.raises(EngineError) as info:
        asyncio.run(engine.draft_rules({}, {}, []))
    assert (info.value.code, info.value.status, info.value.retryable) == (code, status, True)


def test_unrelated_errors_propagate():
    engine = EngineAdapter(_failing_impl(KeyError("bug")))
    with pytest.raises(KeyError):
        asyncio.run(engine.rephrase("메모", {}, {}))


def test_build_persona_falls_back_to_rule_based_on_llm_failure():
    engine = EngineAdapter(_failing_impl(APIConnectionError("down")))
    persona = asyncio.run(engine.build_persona("하늘", HANEUL_ANSWERS))
    assert persona["nickname"] == "하늘"
    assert persona["axes"]["noise_sensitivity"] == 67


def test_inputs_converted_to_engine_models_and_outputs_to_dicts():
    FakeModel.validated = []

    async def draft_rules(me, candidate, judgements):
        assert isinstance(me, FakeModel) and isinstance(judgements[0], FakeModel)
        return [FakeModel({"area": "fridge", "text": "칸 나누기"})]

    models = SimpleNamespace(Persona=FakeModel, SceneJudgement=FakeModel)
    engine = EngineAdapter(SimpleNamespace(draft_rules=draft_rules), models)
    rules = asyncio.run(engine.draft_rules({"nickname": "하늘"}, {"nickname": "후보 A"}, [{"verdict": "conflict"}]))
    assert rules == [{"area": "fridge", "text": "칸 나누기"}]
    assert {"verdict": "conflict"} in FakeModel.validated


def _stream(events):
    async def simulate(me, candidate, *, mode):
        for event in events:
            yield event
    return SimpleNamespace(simulate=simulate)


def _drain(engine):
    async def run():
        return [e async for e in engine.simulate({}, {}, mode="agents")]
    return asyncio.run(run())


def test_simulate_passes_valid_events_through():
    event = {"type": "utterance", "data": {"scene_index": 1, "turn": 1, "speaker": "me", "name": "하늘 AI", "text": "안녕"}}
    assert _drain(EngineAdapter(_stream([event]))) == [event]


def test_simulate_rejects_unknown_event_type():
    with pytest.raises(EngineError) as info:
        _drain(EngineAdapter(_stream([{"type": "chat", "data": {}}])))
    assert info.value.code == "INTERNAL_ERROR"


def test_simulate_maps_llm_error_mid_stream():
    async def simulate(me, candidate, *, mode):
        yield {"type": "scene_started", "data": {"scene_index": 1, "scene": {}}}
        raise RateLimitError("429")

    with pytest.raises(EngineError) as info:
        _drain(EngineAdapter(SimpleNamespace(simulate=simulate)))
    assert info.value.code == "LLM_RATE_LIMITED"


def test_fake_engine_full_simulation_through_adapter():
    engine = load_engine("fake")
    me = asyncio.run(engine.build_persona("하늘", HANEUL_ANSWERS))
    events = asyncio.run(_collect_all(engine, me))
    judgements = [e["data"] for e in events if e["type"] == "scene_judged"]
    score = engine.score(judgements)
    assert 0 <= score <= 100 and engine.headline(score)
    rules = asyncio.run(engine.draft_rules(me, me, judgements))
    assert len(rules) == 6


async def _collect_all(engine, me):
    return [e async for e in engine.simulate(me, {**me, "nickname": "후보 A"})]
