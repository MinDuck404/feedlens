"""Platform scrapers; compatibility exports for existing callers."""
import base64
import json
import os
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import escape
from typing import Callable
from urllib.parse import parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from ..models import RawPost
from .facebook_links import (
    AD_QUERY_KEYS,
    clean_facebook_author,
    facebook_ad_link,
    select_facebook_link,
    is_facebook_content_url,
    facebook_dom_permalink,
    POST_LINK_RE,
)
from .facebook_stories import (
    facebook_story_id,
    facebook_actor_slug,
    _DEBUG_SECRET,
    sanitize_facebook_debug,
    FacebookStoryCache,
    _extract_facebook_post_id,
    facebook_graphql_debug,
    facebook_stories,
    cache_facebook_stories,
    _match_facebook_story_by_id,
    match_facebook_story,
    _normalize_fb_prefix,
    _facebook_story_belongs_to_group,
    _is_other_facebook_group,
    _should_use_story_text,
    capture_facebook_response,
)
from .facebook_dom import (
    FB_NODE_SELECTOR,
    FB_LINK_SELECTOR,
    FB_SCROLL_MESSAGES_JS,
    FB_JS,
    FB_HEADER_SNAPSHOT_JS,
    _facebook_items,
    _resolve_facebook_items,
    FB_EXPAND_JS,
    FB_EXPAND_CANDIDATES_JS,
    FB_EXPAND_CLICK_JS,
    _wait_for_facebook_scroll,
)
from .base import (
    ProgressFn,
    is_chronological_url,
    STOP_REASON_TEXT,
    collection_message,
    Scraper,
    NeedsVerification,
    VERIFY_TIMEOUT,
    BLOCKED_PATHS,
    is_blocked_url,
    has_login_form,
    PACE,
    _human_pause,
)
from .platforms import (
    LINKEDIN_JS,
    LINKEDIN_EXPAND_JS,
    X_JS,
    REDDIT_JS,
    _group_url,
    FacebookScraper,
    LinkedInJobsScraper,
    LinkedInScraper,
    XScraper,
    RedditScraper,
    SCRAPERS,
)
