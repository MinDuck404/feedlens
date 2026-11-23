"""Conservative, text-only duplicate grouping within one analysis run."""
import hashlib
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import RawPost


def normalize_text(text: str) -> str:
    def clean_url(match):
        try:
            parts = urlsplit(match.group())
        except ValueError:
            return match.group()
        query = [(key, value) for key, value in parse_qsl(parts.query)
                 if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}]
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))

    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"https?://[^\s]+", clean_url, text)
    text = re.sub(r"(?<!\w)#[\w]+", " ", text)
    return " ".join(re.findall(r"[^\W_]+(?:[+#]+)?|[$€£¥₫]", text, re.UNICODE))


def _same_post(a: RawPost, b: RawPost, left: str, right: str) -> bool:
    if a.platform != b.platform or min(len(left), len(right)) < 120:
        return False
    if a.job_seed and b.job_seed and a.job_seed.job_id and b.job_seed.job_id and a.job_seed.job_id != b.job_seed.job_id:
        return False
    # Keep changed pay, dates, phone numbers and requisition numbers distinct.
    if re.findall(r"\d+", left) != re.findall(r"\d+", right):
        return False
    if left == right:
        return True
    threshold = 0.95 if min(len(left), len(right)) < 240 else 0.90
    if 2 * min(len(left), len(right)) / (len(left) + len(right)) < threshold:
        return False
    words_a, words_b = left.split(), right.split()
    word_matcher = SequenceMatcher(None, words_a, words_b, autojunk=False)
    # Reject unrelated prose cheaply before character matching; allow languages without spaces.
    if min(len(words_a), len(words_b)) >= 12 and word_matcher.quick_ratio() < 0.75:
        return False
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    if matcher.quick_ratio() < threshold or matcher.ratio() < threshold:
        return False
    # A tiny role/technology replacement can describe a different vacancy even in a long template.
    for tag, i, j, k, l in word_matcher.get_opcodes():
        if tag == "insert" and i not in {0, len(words_a)}:
            return False
        if tag == "delete" and k not in {0, len(words_b)}:
            return False
        if tag == "replace":
            old, new = " ".join(words_a[i:j]), " ".join(words_b[k:l])
            if SequenceMatcher(None, old, new, autojunk=False).ratio() < 0.75:
                return False
    return True


def group_posts(posts: list[RawPost], preferred_fingerprints: set[str] | None = None) -> list[list[RawPost]]:
    """Prefer completed analyses, then longest text; ties keep collection order."""
    preferred_fingerprints = preferred_fingerprints or set()
    groups: list[list[RawPost]] = []
    normalized: list[str] = []
    observations = set()
    # Compare every member to its representative, so chains cannot join dissimilar endpoints.
    for post in sorted(posts, key=lambda item: (item.fingerprint not in preferred_fingerprints, -len(item.text))):
        observation = (post.platform, post.source, post.url, post.text, post.author,
                       post.job_seed.job_id if post.job_seed else "")
        if observation in observations:
            continue
        observations.add(observation)
        norm = normalize_text(post.text)
        for group, original in zip(groups, normalized):
            if _same_post(group[0], post, original, norm):
                group.append(post)
                break
        else:
            groups.append([post])
            normalized.append(norm)
    order = {id(post): i for i, post in enumerate(posts)}
    groups.sort(key=lambda group: min(order[id(post)] for post in group))
    return groups


def preserve_post_identities(posts: list[RawPost]) -> list[RawPost]:
    """Disambiguate legacy 500-character hashes without changing existing identities."""
    seen: set[str] = set()
    observations: dict[tuple[str, str, str, str, str, str], RawPost] = {}
    result = []
    for post in posts:
        observation = (post.platform, post.source, post.url, post.text, post.author,
                       post.job_seed.job_id if post.job_seed else "")
        if observation in observations:
            result.append(observations[observation])
            continue
        if post.fingerprint in seen:
            identity = f"{post.fingerprint}|{post.source}|{post.url}|{post.text}|{post.author}"
            post = post.model_copy(update={"storage_key": hashlib.sha1(identity.encode()).hexdigest()})
        seen.add(post.fingerprint)
        observations[observation] = post
        result.append(post)
    return result
