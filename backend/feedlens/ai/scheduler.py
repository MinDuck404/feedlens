"""Process-shared, thread-safe request reservations with persistent daily counts."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import threading
import time
from zoneinfo import ZoneInfo

from .base import AIError, AIOutputTruncated, MAX_OUTPUT_TOKENS
from .limits import Limits, daily_quota_error, default_limits, learn_limits

MAX_OUTPUT = MAX_OUTPUT_TOKENS


class QuotaExhausted(AIError):
    pass


class AnalysisStopped(AIError):
    def __init__(self):
        super().__init__("AI analysis stopped by user; saved posts can be continued.")


def check_stopped(stop_event):
    if stop_event is not None and stop_event.is_set():
        raise AnalysisStopped()


def pacific_day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()


@dataclass
class Candidate:
    key_id: int | str
    client: object
    priority: int = 0
    tier: str = "free"
    disabled: bool = False
    key_label: str = ""

    def progress(self, state, **details):
        return {"state": state, "provider": self.client.info.name,
                "provider_id": getattr(self.client.info, "key", ""), "model": self.model,
                "key_label": self.key_label or (f"#{self.key_id}" if isinstance(self.key_id, int) else ""),
                **details}

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
        self.failures = defaultdict(int)
        self.key_projects = {}
        self.model_aliases = {}

    def quota_pair(self, candidate):
        provider = getattr(candidate.client.info, "key", "")
        project = self.key_projects.get((provider, candidate.key_id))
        key = f"project:{provider}:{project}" if project else candidate.key_id
        return key, self.model_aliases.get((provider, candidate.model), candidate.model)

    def _merge_pair(self, old, new):
        if old == new:
            return
        self.windows[new].extend(self.windows.pop(old, []))
        self.windows[new] = deque(sorted(self.windows[new]))
        if old in self.blocked_until:
            self.blocked_until[new] = max(self.blocked_until.get(new, 0), self.blocked_until.pop(old))
        if old in self.learned:
            self.learned[new] = self.learned.pop(old)
        self.daily_blocked.update((new, day) for pair, day in list(self.daily_blocked) if pair == old)

    def limits(self, candidate):
        if candidate.tier == "paid":
            return Limits()  # Paid keys only obey the provider's retry-after, not client caps.
        return self.learned.get(self.quota_pair(candidate), self.default_limits(getattr(candidate.client.info, "key", ""), candidate.model, candidate.tier))

    def forget_key(self, key_id):
        with self.lock:
            for mapping in (self.windows, self.learned, self.blocked_until):
                for pair in list(mapping):
                    if pair[0] == key_id:
                        mapping.pop(pair, None)
            self.daily_blocked = {entry for entry in self.daily_blocked if entry[0][0] != key_id}
            self.status.pop(key_id, None)

    def daily_requests(self, candidate, day):
        provider = getattr(candidate.client.info, "key", "")
        project = self.key_projects.get((provider, candidate.key_id))
        keys = ({key for (p, key), value in self.key_projects.items() if p == provider and value == project}
                if project else {candidate.key_id})
        model = self.quota_pair(candidate)[1]
        if self.db is not None and isinstance(candidate.key_id, int):
            return sum(usage.get("requests", 0) for key in keys if isinstance(key, int)
                       for name, usage in self.db.ai_usage(key, day).items()
                       if self.model_aliases.get((provider, name), name) == model)
        return sum(usage[0] for (key, name, date), usage in self.usage.items()
                   if key in keys and date == day and self.model_aliases.get((provider, name), name) == model)

    def daily_exhausted(self, candidate, day):
        if (self.quota_pair(candidate), day) in self.daily_blocked:
            return True
        provider = getattr(candidate.client.info, "key", "")
        model = self.quota_pair(candidate)[1]
        return (self.db is not None and isinstance(candidate.key_id, int) and
                any(usage.get("exhausted", False) for name, usage in self.db.ai_usage(candidate.key_id, day).items()
                    if self.model_aliases.get((provider, name), name) == model))

    def _ordered(self, candidates, day):
        # Exhaust the keys of a generous model before spending a scarce fallback model's RPD.
        models = {}
        for c in candidates:
            capacity = self.limits(c).rpd
            score = -(capacity if capacity is not None else float("inf"))
            previous = models.get(c.model)
            models[c.model] = (min(score, previous[0]), previous[1]) if previous else (score, len(models))
        def rank(c):
            rpd = self.limits(c).rpd
            remaining = float("inf") if rpd is None else rpd - self.daily_requests(c, day)
            return models[c.model], c.priority, -remaining
        return sorted((c for c in candidates if not c.disabled), key=rank)

    def acquire(self, candidates, est_tokens, notify=lambda message: None, *, stop_event=None, on_state=lambda state: None):
        while True:
            check_stopped(stop_event)
            with self.lock:
                day, now = pacific_day(self.now()), self.clock()
                waiting = []
                selected_model = None
                for candidate in self._ordered(candidates, day):
                    limits = self.limits(candidate)
                    if (self.daily_exhausted(candidate, day) or
                            limits.rpd is not None and self.daily_requests(candidate, day) >= limits.rpd):
                        continue
                    if limits.tpm is not None and est_tokens > limits.tpm:
                        continue  # Waiting cannot make an oversized request fit.
                    if limits.rpm == 0:
                        continue
                    if selected_model is not None and candidate.model != selected_model:
                        continue
                    selected_model = candidate.model
                    pair = self.quota_pair(candidate)
                    window = self.windows[pair]
                    while window and window[0][0] <= now - 60:
                        window.popleft()
                    wait = max(0, self.blocked_until.get(pair, 0) - now)
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
                        waiting.append((wait, candidate))
                        continue
                    check_stopped(stop_event)
                    if self.db is not None and isinstance(candidate.key_id, int):
                        if not self.db.reserve_ai_usage(candidate.key_id, candidate.model, day, est_tokens, limits.rpd):
                            continue
                    else:
                        usage = self.usage[(candidate.key_id, candidate.model, day)]
                        usage[0] += 1; usage[1] += est_tokens
                    window.append((now, est_tokens))
                    return candidate
                if not waiting:
                    on_state({"state": "exhausted", "daily": all(
                        self.daily_exhausted(c, day) or self.limits(c).rpd is not None and
                        self.daily_requests(c, day) >= self.limits(c).rpd for c in candidates)})
                    raise QuotaExhausted("AI quota exhausted: every enabled key/model has exhausted its daily allowance or cannot fit this request.")
                wait, candidate = min(waiting, key=lambda item: item[0])
            on_state(candidate.progress("quota_wait", retry_at=time.time() + wait, wait_seconds=wait))
            notify(f"Đang chờ hạn mức phút của {candidate.client.info.name} ({candidate.model}): {wait:.0f} giây")
            if stop_event is not None:
                stop_event.wait(max(0.001, wait))
            else:
                self.sleep(max(0.001, wait))

    def parallelism(self, candidates):
        with self.lock:
            day, now = pacific_day(self.now()), self.clock()
            active = self._ordered(candidates, day)
            ready, pairs = 0, set()
            for c in active:
                pair, limits = self.quota_pair(c), self.limits(c)
                if pair in pairs or self.daily_exhausted(c, day):
                    continue
                pairs.add(pair)
                used = sum(started > now - 60 for started, _ in self.windows[pair])
                ready += max(0, limits.rpm - used) if limits.rpm is not None else 4
            return min(4, max(1, ready))

    def complete_json(self, candidates, system, prompt, schema, effort="low", notify=lambda message: None,
                      retry_base=3.0, on_selected=lambda candidate: None, *, stop_event=None, on_state=lambda state: None):
        est_tokens = (len(system) + len(prompt)) // 3 + MAX_OUTPUT
        with self.lock:
            ordered = self._ordered(candidates, pacific_day(self.now()))
            previous = ordered[0] if ordered else None
        while True:
            candidate = self.acquire(candidates, est_tokens, notify, stop_event=stop_event, on_state=on_state)
            check_stopped(stop_event)
            switched = previous is not None and candidate.key_id != previous.key_id and candidate.model == previous.model
            if switched:
                notify(f"Chuyển sang key {candidate.progress('sending')['key_label']} (cùng model {candidate.model}).")
            on_selected(candidate)
            on_state(candidate.progress("sending", switched_key=switched))

            def response_state(state):
                served = getattr(candidate.client, "served_model", candidate.model)
                with self.lock:
                    old = self.quota_pair(candidate)
                    if served != candidate.model:
                        self.model_aliases[(getattr(candidate.client.info, "key", ""), candidate.model)] = served
                        self._merge_pair(old, self.quota_pair(candidate))
                on_selected(candidate)
                on_state(candidate.progress(state, model=served, requested_model=candidate.model, switched_key=switched))

            try:
                result = candidate.client.complete_json(system, prompt, schema, effort)
                response_state("received")
                with self.lock:
                    self.failures.pop(self.quota_pair(candidate), None)
                self.status[candidate.key_id] = "ok"
                return result
            except AIOutputTruncated:
                response_state("output_retry")
                raise
            except Exception as exc:
                message = str(exc)
                status = next((getattr(exc, k, None) for k in ("status_code", "code", "status") if isinstance(getattr(exc, k, None), int)), None)
                auth = status in {401, 403} or bool(re.search(r"\b(?:401|403)\b|UNAUTHENTICATED|invalid api.?key", message, re.I))
                daily = daily_quota_error(message)
                rate = status == 429 or "429" in message or "RESOURCE_EXHAUSTED" in message.upper()
                missing = status == 404 or bool(re.search(r"\b404\b|model.*(?:not found|not supported|no longer)", message, re.I))
                transient = (isinstance(exc, (ConnectionError, TimeoutError, OSError)) or status in {408, 500, 502, 503, 504, 529}
                             or bool(re.search(r"UNAVAILABLE|OVERLOADED|TIMEOUT|TIMED OUT|HIGH DEMAND|CONNECTION|CONNECTERROR|GETADDRINFO|DNS|SOCKET", message, re.I)))
                with self.lock:
                    provider = getattr(candidate.client.info, "key", "")
                    if provider == "gemini" and (project := re.search(r"(?:projects/|project[_ ]?id\W+)([\w-]+)", message, re.I)):
                        old = self.quota_pair(candidate)
                        self.key_projects[(provider, candidate.key_id)] = project[1]
                        self._merge_pair(old, self.quota_pair(candidate))
                        on_state(candidate.progress("quota_wait", project_shared=True))
                    pair = self.quota_pair(candidate)
                    if auth:
                        for c in candidates:
                            if c.key_id == candidate.key_id:
                                c.disabled = True
                        self.status[candidate.key_id] = "invalid"
                        if all(c.disabled and self.status.get(c.key_id) == "invalid" for c in candidates):
                            raise AIError("401 Authentication failed for all enabled AI keys") from None
                    elif daily:
                        self.daily_blocked.add((pair, pacific_day(self.now())))
                        self.learned[pair] = learn_limits(message, self.limits(candidate))
                        if self.db is not None and isinstance(candidate.key_id, int):
                            self.db.exhaust_ai_usage(candidate.key_id, candidate.model, pacific_day(self.now()))
                    elif missing:
                        candidate.disabled = True
                    elif rate or transient:
                        self.learned[pair] = learn_limits(message, self.limits(candidate))
                        self.failures[pair] += 1
                        if self.failures[pair] >= 3:
                            candidate.disabled = True
                        else:
                            delay = re.search(r"retry in ([\d.]+)\s*s\b|retryDelay\W+([\d.]+)s", message, re.I)
                            headers = getattr(getattr(exc, "response", None), "headers", {}) or {}
                            try:
                                after = float(headers.get("retry-after", 0))
                            except (TypeError, ValueError):
                                after = 0
                            wait = (float(next(g for g in delay.groups() if g)) if delay else
                                    after or min(60, retry_base * 2 ** min(self.failures[pair] - 1, 6)))
                            self.blocked_until[pair] = self.clock() + wait
                    else:
                        raise
                if candidate.disabled or daily:
                    day = pacific_day(self.now())
                    remaining = [c for c in self._ordered(candidates, day) if not self.daily_exhausted(c, day)
                                 and (self.limits(c).rpd is None or self.daily_requests(c, day) < self.limits(c).rpd)]
                    next_model = remaining[0].model if remaining else "key/model dự phòng"
                    on_state(candidate.progress("switching", next_model=remaining[0].model if remaining else ""))
                    notify(f"{candidate.model} không còn dùng được, chuyển sang {next_model}…")
                previous = candidate


_LOCK = threading.Lock()


def scheduler_for(db):
    with _LOCK:
        if not hasattr(db, "_quota_scheduler"):
            db._quota_scheduler = QuotaScheduler(db)
        return db._quota_scheduler
