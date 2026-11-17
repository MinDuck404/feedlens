"""Conservative client defaults, not guarantees of a project's actual quota."""
from dataclasses import dataclass, replace
import re


@dataclass(frozen=True)
class Limits:
    rpm: int | None = None
    tpm: int | None = None
    rpd: int | None = None


def default_limits(provider: str, model: str, tier: str = "free") -> Limits:
    if tier == "paid" or provider != "gemini":
        return Limits()
    if model.removeprefix("models/").startswith("gemini-3.5-flash-lite"):
        return Limits(15, 250_000, 500)
    return Limits(5, 250_000, 20)


def learn_limits(message: str, current: Limits) -> Limits:
    """Read each quotaId/limit pair separately so RPM and RPD cannot be confused."""
    quotas = list(re.finditer(r"quotaId\W+([\w-]+)", message, re.I))
    for index, quota in enumerate(quotas):
        start = quotas[index - 1].end() if index else 0
        end = quotas[index + 1].start() if index + 1 < len(quotas) else len(message)
        limits = list(re.finditer(r"\blimit\W+(\d+)", message[start:end], re.I))
        if not limits:
            continue
        limit = min(limits, key=lambda m: abs(start + m.start() - quota.start()))
        amount = int(limit[1])
        if re.search(r"PerDay", quota[1], re.I):
            current = replace(current, rpd=amount)
        elif re.search(r"PerMinute", quota[1], re.I):
            field = "tpm" if re.search(r"token", quota[1], re.I) else "rpm"
            current = replace(current, **{field: amount})
    return current
