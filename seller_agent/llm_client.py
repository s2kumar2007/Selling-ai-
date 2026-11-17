"""Groq client (OpenAI-compatible endpoint), stdlib only.

Handles: key from .env, model listing, strict-JSON requests with local validation, exponential backoff on 429/5xx,
a per-minute request limiter, response caching, per-run call/token counters. Transport is injectable for tests.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .config import Config

BASE_URL = "https://api.groq.com/openai/v1"
ROOT = Path(__file__).resolve().parent.parent

Transport = Callable[[str, str, dict, bytes | None, float], tuple[int, dict, bytes]]


def load_env(path: Path | str | None = None) -> None:
    """Minimal .env loader. Existing environment variables win. Never prints values."""
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    retries: int = 0
    errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0

    def cost(self, price_in_per_mtok: float | None, price_out_per_mtok: float | None) -> float | None:
        if price_in_per_mtok is None or price_out_per_mtok is None:
            return None
        return (self.prompt_tokens * price_in_per_mtok + self.completion_tokens * price_out_per_mtok) / 1e6


class RateLimiter:
    """Allow at most `per_minute` requests in any 60 s window (thread-safe)."""

    def __init__(self, per_minute: int, clock=time.monotonic, sleep=time.sleep):
        self.per_minute, self.clock, self.sleep = max(1, per_minute), clock, sleep
        self.stamps: list[float] = []
        self.lock = threading.Lock()

    def wait(self) -> None:
        while True:
            with self.lock:
                now = self.clock()
                self.stamps = [t for t in self.stamps if now - t < 60.0]
                if len(self.stamps) < self.per_minute:
                    self.stamps.append(now)
                    return
                delay = 60.0 - (now - self.stamps[0])
            self.sleep(max(0.01, delay))


@dataclass
class GroqClient:
    cfg: Config
    api_key: str | None = None
    base_url: str = BASE_URL
    transport: Transport = urllib_transport
    sleep: Callable[[float], None] = time.sleep
    usage: Usage = field(default_factory=Usage)
    cache: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        load_env()
        self.api_key = self.api_key or os.environ.get("GROQ_API_KEY")
        self.limiter = RateLimiter(self.cfg.max_calls_per_minute, sleep=self.sleep)
        self.lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def list_models(self) -> list[str]:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set (put it in .env)")
        status, _, body = self.transport("GET", f"{self.base_url}/models", self._headers(), None, self.cfg.timeout_s)
        if status != 200:
            raise LLMError(f"model list failed: HTTP {status}")
        return sorted(m["id"] for m in json.loads(body)["data"])

    def _post(self, payload: dict) -> dict:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set (put it in .env)")
        body = json.dumps(payload).encode()
        delay = self.cfg.backoff_base_s
        last = "no attempt"
        for attempt in range(self.cfg.max_retries + 1):
            self.limiter.wait()
            t0 = time.perf_counter()
            try:
                status, headers, raw = self.transport("POST", f"{self.base_url}/chat/completions",
                                                      self._headers(), body, self.cfg.timeout_s)
            except Exception as e:  # network error / timeout
                status, headers, raw = 599, {}, str(e).encode()
            with self.lock:
                self.usage.latency_s += time.perf_counter() - t0
            if status == 200:
                return json.loads(raw)
            last = f"HTTP {status}"
            retryable = status in (429, 500, 502, 503, 504, 599)
            if not retryable or attempt == self.cfg.max_retries:
                break
            with self.lock:
                self.usage.retries += 1
            ra = {k.lower(): v for k, v in headers.items()}.get("retry-after")
            wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else delay
            self.sleep(min(wait, 30.0))
            delay *= 2
        with self.lock:
            self.usage.errors += 1
        raise LLMError(f"Groq request failed ({last})")

    def chat(self, messages: list[dict], model: str | None = None, json_mode: bool = False,
             schema: Mapping[str, Any] | None = None, temperature: float | None = None,
             max_tokens: int | None = None, use_cache: bool = True) -> str:
        model = model or self.cfg.seller_model
        if not model:
            raise LLMError("no model configured (set seller_model in config.json)")
        temperature = self.cfg.temperature if temperature is None else temperature
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature,
                                   "max_tokens": max_tokens or self.cfg.max_tokens}
        if schema is not None:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "move", "strict": True, "schema": dict(schema)}}
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if use_cache and temperature == 0 and key in self.cache:
            with self.lock:
                self.usage.cache_hits += 1
            return self.cache[key]
        try:
            data = self._post(payload)
        except LLMError:
            if schema is None:
                raise
            # some models do not accept json_schema: retry once as plain JSON mode (output is validated locally)
            payload["response_format"] = {"type": "json_object"}
            data = self._post(payload)
        text = data["choices"][0]["message"]["content"] or ""
        u = data.get("usage") or {}
        with self.lock:
            self.usage.calls += 1
            self.usage.prompt_tokens += int(u.get("prompt_tokens", 0))
            self.usage.completion_tokens += int(u.get("completion_tokens", 0))
        if use_cache and temperature == 0:
            self.cache[key] = text
        return text

    def chat_json(self, messages: list[dict], **kw: Any) -> dict:
        text = self.chat(messages, json_mode=kw.pop("json_mode", True), **kw)
        try:
            out = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"model did not return JSON: {e}") from e
        if not isinstance(out, dict):
            raise LLMError("model JSON is not an object")
        return out
