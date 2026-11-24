"""Choose an offline analyzer or configured AI candidates for one user's run."""
from feedlens.ai import registry
from feedlens.ai.scheduler import Candidate, QuotaScheduler, scheduler_for
from .heuristic import HeuristicAnalyzer
from .llm import LLMAnalyzer


def get_analyzer(provider: str | None, model: str | None, keys, user_id: int = 0):
    mapping = keys if isinstance(keys, dict) else {k.provider: (k.api_key, k.source) for k in keys}
    key = registry.resolve_provider_key(provider, mapping)
    if key == "offline":
        return HeuristicAnalyzer()
    credentials = getattr(keys, "credentials", keys if isinstance(keys, list) else None)
    if credentials is None:
        credentials = [registry.KeyCredential(f"legacy:{user_id}:{key}", key, mapping[key][0])]
    candidates = []
    for credential in credentials:
        if credential.provider != key:
            continue
        for candidate_model in registry.resolve_models(user_id, key, credential.api_key, model):
            candidates.append(Candidate(credential.id, registry.get_provider(key, candidate_model, credential.api_key),
                                        credential.priority, credential.tier, key_label=credential.label))
    database = getattr(keys, "db", None)
    scheduler = scheduler_for(database) if database is not None else QuotaScheduler()
    return LLMAnalyzer(candidates[0].client, candidates=candidates, scheduler=scheduler)
