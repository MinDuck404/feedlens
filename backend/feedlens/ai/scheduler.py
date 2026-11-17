"""Process-shared, thread-safe request reservations with persistent daily counts."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import threading
import time
from zoneinfo import ZoneInfo

from .base import AIError, MAX_OUTPUT_TOKENS
from .limits import Limits, default_limits, learn_limits

MAX_OUTPUT = MAX_OUTPUT_TOKENS


class QuotaExhausted(AIError):
    pass


def pacific_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()


@dataclass
class Candidate:
    key_id: int | str
    client: object
    priority: int = 0
    tier: str = "free"
    disabled: bool = False

    @property
    def model(self):
        return self.client.model

    @property
    def pair(self):
        return self.key_id, self.model


class QuotaScheduler:
    def __init__(self, db=None, *, clock=None, sleep=None, now=None, default_limits=default_limits):
        self.db = db
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.default_limits = default_limits
        self.lock = threading.RLock()
        self.windows = defaultdict(deque)
        self.learned = {}
        self.blocked_until = {}
        self.daily_blocked = set()
        self.usage = defaultdict(lambda: [0, 0])
        self.status = {}

    def limits(self, candidate):
        if candidate.tier == "paid":
            return Limits()  # Paid keys only obey the provider's retry-after, not client caps.
        return self.learned.get(candidate.pair, self.default_limits(getattr(candidate.client.info, "key", ""), candidate.model, candidate.tier))

    def forget_key(self, key_id):
        with self.lock:
            for mapping in (self.windows, self.learned, self.blocked_until):
                for pair in list(mapping):
                    if pair[0] == key_id:
                        mapping.pop(pair, None)
            self.daily_blocked = {entry for entry in self.daily_blocked if entry[0][0] != key_id}
            self.status.pop(key_id, None)

    def daily_requests(self, candidate, day):
        if self.db is not None and isinstance(candidate.key_id, int):
            return self.db.ai_usage(candidate.key_id, day).get(candidate.model, {}).get("requests", 0)
        return self.usage[(candidate.key_id, candidate.model, day)][0]

    def daily_exhausted(self, candidate, day):
        if (candidate.pair, day) in self.daily_blocked:
            return True
        return (self.db is not None and isinstance(candidate.key_id, int) and
                self.db.ai_usage(candidate.key_id, day).get(candidate.model, {}).get("exhausted", False))

    def _ordered(self, candidates, day):
        def rank(c):
            rpd = self.limits(c).rpd
            remaining = float("inf") if rpd is None else rpd - self.daily_requests(c, day)
            return c.priority, -remaining
        return sorted((c for c in candidates if not c.disabled), key=rank)

    def acquire(self, candidates, est_tokens, notify=lambda message: None):
        while True:
            with self.lock:
                day, now = pacific_day(self.now()), self.clock()
                for candidate in self._ordered(candidates, day):
                    limits = self.limits(candidate)
                    if (self.daily_exhausted(candidate, day) or
                            limits.rpd is not None and self.daily_requests(candidate, day) >= limits.rpd):
                        continue
                    if limits.tpm is not None and est_tokens > limits.tpm:
                        continue  # Waiting cannot make an oversized request fit.
                    window = self.windows[candidate.pair]
                    while window and window[0][0] <= now - 60:
                        window.popleft()
                    wait = max(0, self.blocked_until.get(candidate.pair, 0) - now)
                    if limits.rpm is not None and len(window) >= limits.rpm:
                        if limits.rpm == 0:
                            continue
                        wait = max(wait, window[0][0] + 60 - now)
                    if limits.tpm is not None and sum(tokens for _, tokens in window) + est_tokens > limits.tpm:
                        released = sum(tokens for _, tokens in window) + est_tokens - limits.tpm
                        for started, tokens in window:
                            released -= tokens
                            if released <= 0:
                                wait = max(wait, started + 60 - now)
                                break
                    if wait > 0:
                        break  # Wait for the preferred pair rather than spend a smaller daily allowance.
                    if self.db is not None and isinstance(candidate.key_id, int):
                        if not self.db.reserve_ai_usage(candidate.key_id, candidate.model, day, est_tokens, limits.rpd):
                            continue
                    else:
                        usage = self.usage[(candidate.key_id, candidate.model, day)]
                        usage[0] += 1; usage[1] += est_tokens
                    window.append((now, est_tokens))
                    return candidate
                else:
                    raise QuotaExhausted("AI quota exhausted: every enabled key/model has exhausted its daily allowance or cannot fit this request.")
            notify(f"Đang chờ hạn mức phút của {candidate.client.info.name} ({candidate.model}): {wait:.0f} giây")
            self.sleep(max(0.001, wait))

    def parallelism(self, candidates):
        with self.lock:
            day, now = pacific_day(self.now()), self.clock()
            active = self._ordered(candidates, day)
            if not active:
                return 1
            c = next((c for c in active if self.limits(c).rpd is None or self.daily_requests(c, day) < self.limits(c).rpd), active[0])
            limits = self.limits(c)
            if c.tier == "free" and getattr(c.client.info, "key", "") == "gemini" and limits.rpm is not None and limits.rpm <= 5:
                return 1
            used = sum(started > now - 60 for started, _ in self.windows[c.pair])
            return min(4, max(1, limits.rpm - used)) if limits.rpm is not None else 4

    def complete_json(self, candidates, system, prompt, schema, effort="low", notify=lambda message: None,
                      retry_base=3.0, on_selected=lambda candidate: None):
        attempts = defaultdict(int)
        est_tokens = (len(system) + len(prompt)) // 3 + MAX_OUTPUT
        while True:
            candidate = self.acquire(candidates, est_tokens, notify)
            on_selected(candidate)
            try:
                result = candidate.client.complete_json(system, prompt, schema, effort)
                attempts.pop(candidate.pair, None)
                self.status[candidate.key_id] = "ok"
                return result
            except Exception as exc:
                message = str(exc)
                status = next((getattr(exc, k, None) for k in ("status_code", "code", "status") if isinstance(getattr(exc, k, None), int)), None)
                auth = status in {401, 403} or bool(re.search(r"\b(?:401|403)\b|UNAUTHENTICATED|invalid api.?key", message, re.I))
                daily = bool(re.search(r"per\s?day", message, re.I))
                rate = status == 429 or "429" in message or "RESOURCE_EXHAUSTED" in message.upper()
                transient = status in {408, 500, 502, 503, 504, 529} or bool(re.search(r"UNAVAILABLE|OVERLOADED|TIMEOUT|TIMED OUT|HIGH DEMAND", message, re.I))
                with self.lock:
                    if auth:
                        for c in candidates:
                            if c.key_id == candidate.key_id:
                                c.disabled = True
                        self.status[candidate.key_id] = "invalid"
                        if all(c.disabled and self.status.get(c.key_id) == "invalid" for c in candidates):
                            raise AIError("401 Authentication failed for all enabled AI keys") from None
                    elif daily:
                        self.daily_blocked.add((candidate.pair, pacific_day(self.now())))
                        self.learned[candidate.pair] = learn_limits(message, self.limits(candidate))
                        if self.db is not None and isinstance(candidate.key_id, int):
                            self.db.exhaust_ai_usage(candidate.key_id, candidate.model, pacific_day(self.now()))
                    elif rate or transient:
                        self.learned[candidate.pair] = learn_limits(message, self.limits(candidate))
                        attempts[candidate.pair] += 1
                        if attempts[candidate.pair] > (6 if rate else 3):
                            candidate.disabled = True
                        else:
                            delay = re.search(r"retry in ([\d.]+)\s*s\b|retryDelay\W+([\d.]+)s", message, re.I)
                            headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
                            try:
                                after = float(headers.get("retry-after", 0))
                            except (TypeError, ValueError):
                                after = 0
                            wait = (float(next(g for g in delay.groups() if g)) if delay else
                                    after or min(60, retry_base * 2 ** min(attempts[candidate.pair] - 1, 6)))
                            self.blocked_until[candidate.pair] = self.clock() + wait
                    else:
                        raise
                if candidate.disabled or daily:
                    remaining = self._ordered(candidates, pacific_day(self.now()))
                    next_model = remaining[0].model if remaining else "key/model dự phòng"
                    notify(f"{candidate.model} không còn dùng được, chuyển sang {next_model}…")


_LOCK = threading.Lock()


def scheduler_for(db):
    with _LOCK:
        if not hasattr(db, "_quota_scheduler"):
            db._quota_scheduler = QuotaScheduler(db)
        return db._quota_scheduler
