"""AI quá tải / hết hạn mức: chờ đúng thời gian nhà cung cấp yêu cầu, không thử lại vô ích,
và các lô chạy song song không đổi model dự phòng chồng lên nhau."""
import threading
from types import SimpleNamespace as Obj

import pytest

import feedlens.analyzer as an
from feedlens.ai.anthropic_provider import AnthropicProvider
from feedlens.ai.base import AIOutputTruncated
from feedlens.ai.gemini_provider import GeminiProvider
from feedlens.ai.openai_provider import OpenAIProvider
from feedlens.analyzer import LLMAnalyzer
from tests.test_core import SAMPLE, FakeProvider

PER_MINUTE = ("429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generate_content_free_tier_requests, "
              "limit: 15, quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier. Please retry in 37.4s.")
PER_DAY = ("429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generate_content_free_tier_requests, "
           "limit: 20, quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier. Please retry in 5h12m.")


@pytest.mark.parametrize("provider_class", [GeminiProvider, OpenAIProvider, AnthropicProvider])
@pytest.mark.parametrize("truncated", [True, False])
def test_providers_report_output_limit_and_invalid_json(provider_class, truncated):
    text = "{}" if truncated else '{"items": ['
    provider = object.__new__(provider_class)
    provider.model = "test-model"
    if provider_class is GeminiProvider:
        provider.genai = Obj(types=Obj(GenerateContentConfig=Obj))
        response = Obj(text=text, candidates=[Obj(finish_reason="MAX_TOKENS" if truncated else "STOP")])
        provider.client = Obj(models=Obj(generate_content=lambda **kwargs: response))
    elif provider_class is OpenAIProvider:
        response = Obj(output_text=text, status="incomplete" if truncated else "completed",
                       incomplete_details=Obj(reason="max_output_tokens") if truncated else None)
        provider.client = Obj(responses=Obj(create=lambda **kwargs: response))
    else:
        response = Obj(content=[Obj(type="text", text=text)], stop_reason="max_tokens" if truncated else "end_turn")
        provider.client = Obj(beta=Obj(messages=Obj(create=lambda **kwargs: response)))
    with pytest.raises(AIOutputTruncated):
        provider.complete_json("system", "prompt", {})


def test_waits_the_delay_the_provider_asks_for(monkeypatch):
    waits = []
    clock = [0.0]
    def wait(seconds):
        waits.append(seconds)
        clock[0] += seconds
    monkeypatch.setattr(an.time, "sleep", wait)
    monkeypatch.setattr(an.time, "monotonic", lambda: clock[0])
    calls = []

    class Limited(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError(PER_MINUTE)
            return super().complete_json(system, prompt, schema, effort)

    LLMAnalyzer(Limited())._json_call("<posts>", {"properties": {}}, "low")
    assert waits == [pytest.approx(37.4, abs=0.6)]


def test_suggested_delay_is_capped(monkeypatch):
    assert an._retry_after("Please retry in 5h12m.") is None  # quá xa: không chờ
    assert an._retry_after("retryDelay': '75s'") == pytest.approx(an.MAX_RETRY_WAIT)
    assert an._retry_after("503 UNAVAILABLE") is None


def test_daily_quota_switches_model_without_retrying(monkeypatch):
    monkeypatch.setattr(an.time, "sleep", lambda s: pytest.fail("không được chờ khi hết hạn mức ngày"))
    calls = []

    class Daily(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            calls.append(self.model)
            if self.model == "lite":
                raise RuntimeError(PER_DAY)
            return super().complete_json(system, prompt, schema, effort)

    a = LLMAnalyzer(Daily("lite"), fallback_models=["flash"])
    a._json_call("<posts>", {"properties": {}}, "low")
    assert calls == ["lite", "flash"]


def test_daily_quota_without_fallback_fails_fast_with_clear_message(monkeypatch):
    monkeypatch.setattr(an.time, "sleep", lambda s: pytest.fail("không được chờ"))

    class Daily(FakeProvider):
        def complete_json(self, *a, **k):
            raise RuntimeError(PER_DAY)

    with pytest.raises(RuntimeError, match="quota exhausted"):
        LLMAnalyzer(Daily("lite"))._json_call("<posts>", {"properties": {}}, "low")


def test_parallel_batches_switch_fallback_model_once(monkeypatch):
    monkeypatch.setattr(an, "RETRY_BASE_SECONDS", 0)
    monkeypatch.setattr(an, "BATCH_SIZE", 1)
    barrier = threading.Barrier(3, timeout=5)

    class Busy(FakeProvider):
        def complete_json(self, system, prompt, schema, effort="low"):
            model = self.model
            if model == "busy":
                try:
                    barrier.wait()  # cả 3 lô cùng thấy model chính quá tải
                except threading.BrokenBarrierError:
                    pass
                raise RuntimeError("503 UNAVAILABLE")
            return super().complete_json(system, prompt, schema, effort)

    a = LLMAnalyzer(Busy("busy"), fallback_models=["second", "third"])
    out = a.classify(SAMPLE, False, [], "", lambda *x: None)
    assert len(out) == len(SAMPLE)
    assert a.provider.model == "second"  # không nhảy qua "third" chỉ vì nhiều lô cùng lỗi
