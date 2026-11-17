import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from seller_agent.config import Config  # noqa: E402
from seller_agent.llm_client import GroqClient, LLMError, RateLimiter, load_env  # noqa: E402


def ok(text, p=10, c=5):
    return 200, {}, json.dumps({"choices": [{"message": {"content": text}}],
                                "usage": {"prompt_tokens": p, "completion_tokens": c}}).encode()


def client(responses, **cfgkw):
    seq = list(responses)
    calls, sleeps = [], []

    def transport(method, url, headers, body, timeout):
        calls.append((method, url))
        r = seq.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    cfg = Config(seller_model="m", max_calls_per_minute=1000, backoff_base_s=1.0, max_retries=3, **cfgkw)
    return GroqClient(cfg, api_key="k", transport=transport, sleep=sleeps.append), calls, sleeps


def test_success_counts_tokens():
    c, calls, _ = client([ok('{"a":1}')])
    assert c.chat_json([{"role": "user", "content": "x"}]) == {"a": 1}
    assert c.usage.calls == 1 and c.usage.prompt_tokens == 10 and c.usage.completion_tokens == 5


def test_429_backs_off_exponentially_then_succeeds():
    c, calls, sleeps = client([(429, {}, b""), (429, {}, b""), ok("{}")])
    c.chat_json([{"role": "user", "content": "x"}])
    assert sleeps == [1.0, 2.0] and c.usage.retries == 2 and len(calls) == 3


def test_retry_after_header_is_honoured():
    c, _, sleeps = client([(429, {"Retry-After": "7"}, b""), ok("{}")])
    c.chat_json([{"role": "user", "content": "x"}])
    assert sleeps == [7.0]


def test_gives_up_after_max_retries():
    c, calls, _ = client([(429, {}, b"")] * 4)
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "x"}])
    assert len(calls) == 4 and c.usage.errors == 1


def test_non_retryable_error_fails_fast():
    c, calls, _ = client([(401, {}, b"")])
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "x"}])
    assert len(calls) == 1


def test_network_error_is_retried():
    c, calls, _ = client([TimeoutError("slow"), ok("{}")])
    c.chat_json([{"role": "user", "content": "x"}])
    assert len(calls) == 2


def test_cache_hit_at_temperature_zero():
    c, calls, _ = client([ok("{}")])
    m = [{"role": "user", "content": "x"}]
    c.chat(m, temperature=0)
    c.chat(m, temperature=0)
    assert len(calls) == 1 and c.usage.cache_hits == 1


def test_non_json_reply_raises():
    c, _, _ = client([ok("not json")])
    with pytest.raises(LLMError):
        c.chat_json([{"role": "user", "content": "x"}])


def test_schema_falls_back_to_json_mode():
    c, calls, _ = client([(400, {}, b"no schema"), ok('{"a":1}')])
    assert c.chat_json([{"role": "user", "content": "x"}], schema={"type": "object"}, json_mode=False) == {"a": 1}


def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("seller_agent.llm_client.load_env", lambda *a, **k: None)
    c = GroqClient(Config(seller_model="m"), api_key=None)
    with pytest.raises(LLMError):
        c.chat([{"role": "user", "content": "x"}])


def test_rate_limiter_blocks_when_window_full():
    t = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s)
        t[0] += s

    rl = RateLimiter(2, clock=lambda: t[0], sleep=sleep)
    rl.wait(); rl.wait(); rl.wait()
    assert sleeps and sleeps[0] >= 59


def test_env_loader_does_not_override(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("FOO_X=1\nBAR_X='2'\n")
    monkeypatch.setenv("FOO_X", "keep")
    monkeypatch.delenv("BAR_X", raising=False)
    load_env(f)
    import os
    assert os.environ["FOO_X"] == "keep" and os.environ["BAR_X"] == "2"
