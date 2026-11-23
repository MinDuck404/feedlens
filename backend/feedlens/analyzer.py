"""Analysis facade and provider selection."""
from __future__ import annotations

import json
import math
import re
import threading
import time
import copy
import unicodedata
import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
from .ai import AIProvider, get_provider, resolve_models, resolve_provider_key
from .ai.base import AIError, AIOutputTruncated
from .ai.registry import KeyCredential
from .ai.scheduler import Candidate, MAX_OUTPUT, QuotaScheduler, scheduler_for
from .job_profile import JobProfile, matching_context
from .models import CATEGORIES, AnalyzedPost, CategoryDigest, Digest, JobInfo, RawPost, Topic, TopicDigest


# Keep runtime settings here for compatibility with existing callers and tests.
BATCH_SIZE = 60
CLASSIFY_OUTPUT_TOKENS_PER_ITEM = 120
JOB_OUTPUT_TOKENS_PER_ITEM = 180
CLASSIFY_OUTPUT_SAFETY_TOKENS = 820
PARALLEL_BATCHES = 4  # số lô gửi AI cùng lúc
MAX_POST_CHARS = 3000  # bài cực dài bị cắt để giữ chi phí mỗi lô ổn định
ProgressFn = Callable[[int, str], None]
logger = logging.getLogger(__name__)
LANGUAGE_NAMES = {"vi": "tiếng Việt", "en": "English", "zh": "简体中文 (Simplified Chinese)"}
RETRIES = 3              # mỗi model: 1 lần gọi + 3 lần thử lại (chờ 3s, 6s, 12s)
RETRY_BASE_SECONDS = 3.0
MAX_RETRY_WAIT = 60.0    # nhà cung cấp bảo chờ lâu hơn thế này thì coi như model đó hết lượt
_TRANSIENT_CODES = {408, 429, 500, 502, 503, 504, 529}


from .analysis_prompts import (
    CLASSIFY_SCHEMA,
    DIGEST_SCHEMA,
    KNOWN_JOBS_SCHEMA,
    SYSTEM,
    _JOB_SCHEMA,
    _seeded_job,
    classification_batch_size,
    estimate_classification_requests,
    estimate_classification_requests_for_count,
    system_prompt,
)
from .analysis_topics import (
    RETAG_BATCH,
    RETAG_SCHEMA,
    RETAG_SNIPPET,
    TOPIC_DIGEST_SCHEMA,
    TOPIC_RULES,
    _clean_topic_ids,
    _topic_groups,
    _with_topic_fields,
    heuristic_topics,
    topics_block,
)
from .job_scoring import (
    MATCH_STOPWORDS,
    TECH_SKILL_TOKENS,
    _HCM_DISTRICTS,
    _HCM_NEIGHBOR_REGIONS,
    _LEVELS,
    _LOCATION_ALIASES,
    _PAY_AMOUNT,
    _PAY_CURRENCY,
    _PAY_NUMBER,
    _PAY_UNIT,
    _SALARY,
    _SKILLS_HEADING,
    _UNKNOWN_LOCATIONS,
    _cv_skills,
    _extract_location,
    _fold_location,
    _job_salary,
    _location_conflict,
    _location_regions,
    _match_terms,
    _nearby_locations_allowed,
    _normalize_level,
    _profile_level,
    _role_terms,
    _role_text,
    _score_job,
    _work_mode_conflict,
    _work_mode_value,
)
from .heuristic_analyzer import (
    HeuristicAnalyzer,
    KEYWORDS,
    _first_sentence,
    heuristic_category,
)
from .llm_analyzer import (
    LLMAnalyzer,
    _is_daily_quota,
    _is_transient,
    _retry_after,
)


def get_analyzer(provider: str | None, model: str | None, keys, user_id: int = 0):
    mapping = keys if isinstance(keys, dict) else {k.provider: (k.api_key, k.source) for k in keys}
    key = resolve_provider_key(provider, mapping)
    if key == "offline":
        return HeuristicAnalyzer()
    credentials = getattr(keys, "credentials", keys if isinstance(keys, list) else None)
    if credentials is None:
        credentials = [KeyCredential(f"legacy:{user_id}:{key}", key, mapping[key][0])]
    candidates = []
    for credential in credentials:
        if credential.provider != key:
            continue
        for candidate_model in resolve_models(user_id, key, credential.api_key, model):
            candidates.append(Candidate(credential.id, get_provider(key, candidate_model, credential.api_key),
                                        credential.priority, credential.tier, key_label=credential.label))
    database = getattr(keys, "db", None)
    scheduler = scheduler_for(database) if database is not None else QuotaScheduler()
    return LLMAnalyzer(candidates[0].client, candidates=candidates, scheduler=scheduler)
