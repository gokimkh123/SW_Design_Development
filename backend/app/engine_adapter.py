"""엔진 어댑터.

- 백엔드에서 엔진을 부르는 유일한 통로 (docs/API.md 7장 함수만 노출)
- 엔진 선택: 환경변수 ENGINE_IMPL = fake(기본, app.fake_engine) | real(engine 패키지)
- 입력: 백엔드 dict → 엔진 Pydantic 모델(engine.models 가 있을 때만)
- 출력: 엔진 모델 → JSON 직렬화 가능한 dict
- 오류: LLM 계열 예외 → EngineError (API.md 6장 코드)
- build_persona 의 LLM 실패 시 규칙 기반 페르소나로 대체 (API.md 4.4, 실패 응답 미반환)
"""

from __future__ import annotations

import importlib
import os
from functools import lru_cache
from types import ModuleType
from typing import Any, AsyncIterator

from app import fake_engine

# 엔진은 장면 이벤트만 반환 (API.md 7장 "이벤트 범위"). 시작 · 완료 이벤트는 백엔드 실행기가 생성
EVENT_TYPES = frozenset({"scene_started", "utterance", "scene_judged", "error"})
ENGINE_MODES = frozenset({"agents", "single"})


def resolve_mode(mode: str | None) -> str:
    """요청 mode(live) → 엔진 실행 방식(SIM_MODE: agents | single). replay는 엔진을 호출하지 않으므로 거부."""
    resolved = (os.getenv("SIM_MODE") or "agents").strip().lower() if mode in (None, "live") else mode
    if resolved not in ENGINE_MODES:
        raise EngineError("INTERNAL_ERROR", 500, f"엔진 실행 모드가 올바르지 않아요: {resolved!r}")
    return resolved

# anthropic SDK 를 직접 import 하지 않고 예외 클래스 이름으로 판별 (가짜 엔진 환경에 SDK 미설치 허용)
_RATE_LIMIT_ERRORS = frozenset({"RateLimitError"})
_UNAVAILABLE_ERRORS = frozenset(
    {"APIError", "APIConnectionError", "APITimeoutError", "APIStatusError", "InternalServerError", "TimeoutError"}
)


class EngineError(Exception):
    """엔진 호출 실패. 오류 응답 변환은 공통 오류 처리기에서 code · status · message 사용."""

    def __init__(self, code: str, status: int, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.message = message
        self.retryable = retryable


def _map_exception(exc: Exception) -> EngineError | None:
    names = {cls.__name__ for cls in type(exc).__mro__}
    if names & _RATE_LIMIT_ERRORS:
        return EngineError("LLM_RATE_LIMITED", 429, "AI 요청이 많아요. 잠시 후 다시 시도해 주세요.", retryable=True)
    if names & _UNAVAILABLE_ERRORS:
        return EngineError("LLM_UNAVAILABLE", 503, "AI 연결에 실패했어요.", retryable=True)
    return None


def _to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _to_dict(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dict(v) for v in value]
    return value


class EngineAdapter:
    def __init__(self, impl: Any, models: ModuleType | None = None, name: str = "custom"):
        self._impl = impl
        self._models = models
        self.name = name

    def _model(self, model_name: str, data: Any) -> Any:
        model = getattr(self._models, model_name, None) if self._models else None
        return model.model_validate(data) if model is not None else data

    async def _call(self, func: str, *args: Any, **kwargs: Any) -> Any:
        try:
            return await getattr(self._impl, func)(*args, **kwargs)
        except EngineError:
            raise
        except Exception as exc:
            mapped = _map_exception(exc)
            if mapped is None:
                raise
            raise mapped from exc

    def _call_sync(self, func: str, *args: Any) -> Any:
        try:
            return getattr(self._impl, func)(*args)
        except Exception as exc:
            mapped = _map_exception(exc)
            if mapped is None:
                raise
            raise mapped from exc

    async def build_persona(self, nickname: str, answers: dict) -> dict:
        """ID · is_seed · created_at 은 호출 측(페르소나 API)이 부여."""
        try:
            persona = await self._call("build_persona", nickname, answers)
        except EngineError:
            persona = await fake_engine.build_persona(nickname, answers)
        return _to_dict(persona)

    def load_scenes(self) -> list[dict]:
        return _to_dict(self._call_sync("load_scenes"))

    async def simulate(self, me: dict, candidate: dict, *, mode: str | None = "live") -> AsyncIterator[dict]:
        """이벤트를 {"type", "data"} dict 로 하나씩 반환. 형식이 틀린 이벤트는 INTERNAL_ERROR."""
        engine_mode = resolve_mode(mode)
        stream = self._impl.simulate(self._model("Persona", me), self._model("Persona", candidate), mode=engine_mode)
        try:
            async for raw in stream:
                event = _to_dict(raw)
                if not isinstance(event, dict) or event.get("type") not in EVENT_TYPES or not isinstance(event.get("data"), dict):
                    raise EngineError("INTERNAL_ERROR", 500, "시뮬레이션 이벤트 형식이 올바르지 않아요.")
                yield event
        except EngineError:
            raise
        except Exception as exc:
            mapped = _map_exception(exc)
            if mapped is None:
                raise
            raise mapped from exc

    def score(self, judgements: list[dict]) -> int:
        return int(self._call_sync("score", [self._model("SceneJudgement", j) for j in judgements]))

    def headline(self, score: int) -> str:
        return str(self._call_sync("headline", score))

    async def draft_rules(self, me: dict, candidate: dict, judgements: list[dict]) -> list[dict]:
        """rule_id 는 호출 측(매칭 서비스)이 부여."""
        rules = await self._call(
            "draft_rules",
            self._model("Persona", me),
            self._model("Persona", candidate),
            [self._model("SceneJudgement", j) for j in judgements],
        )
        return _to_dict(rules)

    async def mediate(self, rule: dict, proposal_text: str, reason: str, proposer: dict, other: dict) -> dict:
        result = await self._call(
            "mediate",
            self._model("RuleDraft", rule),
            proposal_text,
            reason,
            self._model("Persona", proposer),
            self._model("Persona", other),
        )
        return _to_dict(result)

    async def rephrase(self, memo: str, sender: dict, receiver: dict) -> dict:
        result = await self._call("rephrase", memo, self._model("Persona", sender), self._model("Persona", receiver))
        return _to_dict(result)


def load_engine(impl_name: str | None = None) -> EngineAdapter:
    name = (impl_name or os.getenv("ENGINE_IMPL") or "fake").strip().lower()
    if name == "fake":
        return EngineAdapter(fake_engine, name="fake")
    if name == "real":
        engine = importlib.import_module("engine")
        return EngineAdapter(engine, importlib.import_module("engine.models"), name="real")
    raise ValueError(f"ENGINE_IMPL 값이 올바르지 않음: {name!r} (fake | real)")


@lru_cache(maxsize=1)
def get_engine() -> EngineAdapter:
    """FastAPI 의존성용. 테스트에서는 dependency_overrides 또는 get_engine.cache_clear() 사용."""
    return load_engine()
