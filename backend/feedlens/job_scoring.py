"""CV skills and job fit scoring."""
from __future__ import annotations

import re
import unicodedata
from .job_profile import JobProfile
from .models import JobInfo
from . import analyzer as facade


MATCH_STOPWORDS = set("""
    các hoặc cận của cho với trong ngoài những một và hay là có không được cần tìm mong muốn về
    từ đến tại theo như này đó khi thì nếu cũng việc làm công mức thể hơn nhất vào trên dưới
    the and for with from that this have has are was were will can not but your you our their
    experience skills role work years year job jobs hcm tphcm
""".split())


TECH_SKILL_TOKENS = {"python", "javascript", "typescript", "react", "reactjs", "node", "nodejs", "java", "php",
                     "laravel", "django", "fastapi", "docker", "kubernetes", "aws", "azure", "gcp", "sql",
                     "mysql", "postgresql", "mongodb", "redis", "graphql", "api", "rest", "git", "linux",
                     "terraform", "figma", "swift", "kotlin", "c++", "c#", ".net", "excel", "powerbi"}


_SKILLS_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s+)?\*{0,2}(?:main skills|other skills|technical skills|skills|"
    r"kỹ năng(?: chính| khác| chuyên môn| bổ sung)?|(?:主要|其他|核心|技术)?技能)\*{0,2}"
    r"\s*(?:[:：]\*{0,2}\s*(.*))?$", re.I,
)


_PAY_NUMBER = r"\d+(?:[.,]\d+)*"


_PAY_CURRENCY = r"(?:USD|VND|VNĐ)\b|\$"


_PAY_UNIT = (r"(?:triệu|tr|million|m|nghìn|ngàn|k)\b(?:[ \t]*(?:USD|VND|VNĐ|đồng)\b|[ \t]*₫)?"
             r"|(?:USD|VND|VNĐ|đồng)\b|[₫$]")


_PAY_AMOUNT = rf"(?:(?:{_PAY_CURRENCY})[ \t]*)?{_PAY_NUMBER}"


_SALARY = re.compile(
    rf"(?<!\w)(?P<label>(?:lương(?:[ \t]+cứng)?|thu nhập|salary)\b[ \t]*[:：]?[ \t]*)?"
    rf"(?P<pay>(?:(?P<qualifier>up to|tối đa|từ)[ \t]+)?{_PAY_AMOUNT}"
    rf"(?:[ \t]*(?:{_PAY_UNIT}))?"
    rf"(?P<range>[ \t]*(?:[-–—~]|đến|to)[ \t]*{_PAY_AMOUNT}(?:[ \t]*(?:{_PAY_UNIT}))?)?"
    r"(?P<period>[ \t]*(?:/|per\b|mỗi\b)[ \t]*(?:tháng|năm|ngày|giờ|month|year|day|hour)\b)?)"
    r"(?![\w]|[.,]\d)", re.I,
)


def _cv_skills(profile: JobProfile) -> list[str]:
    skills = []
    in_skills = False
    for line in profile.markdown.splitlines():
        heading = _SKILLS_HEADING.match(line)
        if heading:
            in_skills = True
            line = heading[1] or ""
        elif re.match(r"^\s*(?:#{1,6}\s|\*\*[^*]+\*\*\s*(?:[:：]|$))", line):
            in_skills = False
        if in_skills:
            line = re.sub(r"^\s*(?:[-*+]\s+|\d+\.\s+)", "", line)
            skills.extend(term.strip(" \t.*_`").casefold() for term in re.split(r"[,;|、，；]", line))
    if not skills:
        role_words = {word for role in profile.primary_roles + [r.role for r in profile.adjacent_roles]
                      for word in re.findall(r"[\w+#.]+", role.casefold())}
        skills = [word for word in re.findall(r"[\w+#.]+", profile.markdown.casefold())
                  if (word in TECH_SKILL_TOKENS or any(char.isdigit() for char in word)
                      or any(char in word for char in "+#.") and len(word) > 2)
                  and word not in MATCH_STOPWORDS and word not in role_words]
    return list(dict.fromkeys(skill for skill in skills if skill and skill not in MATCH_STOPWORDS))


_LEVELS = {"intern": 0, "fresher": 1, "junior": 1, "mid": 2, "middle": 2,
           "senior": 3, "lead": 4, "principal": 5, "staff": 5}


def _normalize_level(value: str) -> str:
    folded = value.casefold()
    return next((level for level in _LEVELS if re.search(r"(?<!\w)" + level + r"(?!\w)", folded)), "")


def _profile_level(profile: JobProfile) -> tuple[str, float | None]:
    section = re.search(r"(?im)^\s*#{1,6}\s*level\s+and\s+years\s*\n(?P<body>(?:(?!^\s*#{1,6}\s).*(?:\n|$))*)", profile.markdown)
    body = section["body"] if section else profile.markdown
    level = profile.criteria.level or _normalize_level(body)
    years = re.search(r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?|năm)\b", body)
    return level, float(years[1]) if years else None


def _role_terms(roles: list[str]) -> list[str]:
    out = []
    for role in roles:
        original = re.sub(r"[^\w+#]+", " ", role).strip().casefold()
        role = re.sub(r"(?i)\b(intern|fresher|junior|mid|middle|senior|lead|principal|staff)\b", "", original)
        role = re.sub(r"(?i)\bdev\b|\bengineer\b|lập trình viên|kỹ sư phần mềm", "developer", role)
        role = re.sub(r"(?i)\bfullstack\b|full[- ]stack", "full stack", role)
        role = re.sub(r"[^\w+#]+", " ", role).strip()
        for term in (original, role):
            if term:
                out.append(term.casefold())
        out.extend(token.casefold() for token in original.split() if token.isupper() and len(token) <= 4)
            # Fresher/Junior/senior qualifiers can vary while the primary role remains identical.
    return list(dict.fromkeys(out))


def _role_text(value: str) -> str:
    value = re.sub(r"(?i)\bdev\b|\bengineer\b|lập trình viên|kỹ sư phần mềm", "developer", value)
    return re.sub(r"(?i)\bfullstack\b|full[- ]stack", "full stack", value)


def _match_terms(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text)]


def _job_salary(text: str) -> str:
    candidate = ""
    for match in _SALARY.finditer(text):
        # A number without currency or scale may be experience, headcount, or a date.
        if not re.search(_PAY_UNIT, match["pay"], re.I):
            continue
        if match["label"]:
            return match["pay"]
        if not candidate and (match["range"] or match["period"] or match["qualifier"]):
            candidate = match["pay"]
    return candidate


def _location_conflict(preferences: str, location: str, work_mode: str = "") -> bool:
    if _work_mode_value(work_mode) == "remote":
        return False
    expected = _location_regions(preferences)
    actual = _location_regions(location)
    if not expected or not actual or actual & expected:
        return False
    if "hcm" in expected and _nearby_locations_allowed(preferences):
        if actual <= _HCM_NEIGHBOR_REGIONS:
            return False
    return True


def _extract_location(text: str) -> str:
    regions = []
    for line in text.splitlines():
        folded = _fold_location(line)
        anchored = re.search(r"(?:dia diem|noi lam viec|location|workplace|office|working (?:in|at)|lam viec tai|lam viec o)", folded)
        bracket = re.search(r"\[([^\]]+)\]", line)
        candidate = line if anchored else bracket[1] if bracket else ""
        if candidate and _location_regions(candidate):
            regions.extend(sorted(_location_regions(candidate)))
    if not regions:
        return ""
    return ", ".join(dict.fromkeys(regions))


def _fold_location(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold().replace("đ", "d"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


_UNKNOWN_LOCATIONS = {"", "chua ro", "khong neu", "khong ro", "n a", "na", "unknown", "unspecified",
                      "not specified", "khong co", "negotiable"}


_HCM_DISTRICTS = {"quan 1", "quan 2", "quan 3", "quan 4", "quan 5", "quan 6", "quan 7", "quan 8",
                  "quan 9", "quan 10", "quan 11", "quan 12", "q 1", "q 2", "q 3", "q 4", "q 5",
                  "q 6", "q 7", "q 8", "q 9", "q 10", "q 11", "q 12", "thu duc", "binh thanh",
                  "go vap", "tan binh", "tan phu", "phu nhuan", "binh tan", "hoc mon", "cu chi",
                  "nha be", "can gio", "binh chanh", "thu thiem", "binh chieu", "an phu"}


_HCM_NEIGHBOR_REGIONS = {"binh duong", "dong nai", "long an", "tay ninh", "ba ria vung tau", "tien giang"}


_LOCATION_ALIASES = {
    "hcm": ("hcm", "tp hcm", "tphcm", "ho chi minh", "ho chi minh city", "sai gon", "saigon"),
    "ha noi": ("ha noi", "hanoi", "ha noi city"),
    "can tho": ("can tho",), "da nang": ("da nang",), "hai phong": ("hai phong",),
    "an giang": ("an giang",), "ba ria vung tau": ("ba ria vung tau", "vung tau"),
    "bac giang": ("bac giang",), "bac kan": ("bac kan",), "bac lieu": ("bac lieu",),
    "bac ninh": ("bac ninh",), "ben tre": ("ben tre",), "binh dinh": ("binh dinh",),
    "binh duong": ("binh duong",), "binh phuoc": ("binh phuoc",), "binh thuan": ("binh thuan",),
    "ca mau": ("ca mau",), "cao bang": ("cao bang",), "dak lak": ("dak lak", "daklak"),
    "dak nong": ("dak nong", "daknong"), "dien bien": ("dien bien",), "dong nai": ("dong nai",),
    "dong thap": ("dong thap",), "gia lai": ("gia lai",), "ha giang": ("ha giang",),
    "ha nam": ("ha nam",), "ha tinh": ("ha tinh",), "hai duong": ("hai duong",),
    "hau giang": ("hau giang",), "hoa binh": ("hoa binh",), "hung yen": ("hung yen",),
    "khanh hoa": ("khanh hoa", "nha trang"), "kien giang": ("kien giang",), "kon tum": ("kon tum",),
    "lai chau": ("lai chau",), "lam dong": ("lam dong", "da lat"), "lang son": ("lang son",),
    "lao cai": ("lao cai",), "long an": ("long an",), "nam dinh": ("nam dinh",),
    "nghe an": ("nghe an",), "ninh binh": ("ninh binh",), "ninh thuan": ("ninh thuan",),
    "phu tho": ("phu tho",), "phu yen": ("phu yen",), "quang binh": ("quang binh",),
    "quang nam": ("quang nam",), "quang ngai": ("quang ngai",), "quang ninh": ("quang ninh",),
    "quang tri": ("quang tri",), "soc trang": ("soc trang",), "son la": ("son la",),
    "tay ninh": ("tay ninh",), "thai binh": ("thai binh",), "thai nguyen": ("thai nguyen",),
    "thanh hoa": ("thanh hoa",), "thua thien hue": ("thua thien hue", "hue"),
    "tien giang": ("tien giang",), "tra vinh": ("tra vinh",), "tuyen quang": ("tuyen quang",),
    "vinh long": ("vinh long",), "vinh phuc": ("vinh phuc",), "yen bai": ("yen bai",),
    "singapore": ("singapore",), "bangkok": ("bangkok",), "kuala lumpur": ("kuala lumpur",),
}


def _location_regions(value: str) -> set[str]:
    folded = _fold_location(value)
    if folded in _UNKNOWN_LOCATIONS or any(marker in folded for marker in ("chua ro", "khong neu", "n a", "not specified")):
        return set()
    regions = set()
    if any(re.search(r"(?<!\w)" + re.escape(area) + r"(?!\w)", folded) for area in _HCM_DISTRICTS):
        regions.add("hcm")
    for region, aliases in _LOCATION_ALIASES.items():
        for alias in aliases:
            pattern = r"(?<!\w)" + re.escape(_fold_location(alias)) + r"(?!\w)"
            if re.search(pattern, folded):
                regions.add(region)
                break
    return regions


def _nearby_locations_allowed(preferences: str) -> bool:
    folded = _fold_location(preferences)
    return any(term in folded for term in ("lan can", "ben canh", "nearby", "surrounding", "neighboring"))


def _work_mode_value(value: str) -> str:
    folded = value.casefold()
    remote = any(term in folded for term in ("remote", "wfh", "từ xa", "work from home"))
    onsite = any(term in folded for term in ("onsite", "on-site", "văn phòng", "office", "tại chỗ"))
    if any(term in folded for term in ("hybrid", "kết hợp", "mix")) or (remote and onsite):
        return "hybrid"  # e.g. "Onsite / WFH on Fridays" is hybrid, not remote
    return "remote" if remote else "onsite" if onsite else ""


def _work_mode_conflict(preferred: list[str], actual: str) -> bool:
    mode = _work_mode_value(actual)
    return bool(preferred and mode and mode not in preferred)


def _score_job(job: JobInfo, profile: JobProfile, user_level: str, user_years: float | None,
              notes: str, job_level: str = "", job_years: float | None = None, source_text: str = "") -> JobInfo:
    """Score = role base + capped skill bonus - hard conflicts; level cap replaces its penalty."""
    detected = job.match_type if job.match_type in {"primary", "adjacent", "stretch", "none"} else "none"
    if detected == "adjacent" and (not profile.allow_adjacent or
                                    not any(role.enabled for role in profile.adjacent_roles)):
        detected = "stretch"
    job.match_type = detected
    job.constraint_flags = list(dict.fromkeys(job.constraint_flags))

    preferences = " ".join(profile.criteria.locations) + " " + notes
    location = job.location if _location_regions(job.location) else _extract_location(source_text)
    if _location_conflict(preferences, location, job.work_mode):
        if "location" not in job.constraint_flags:
            job.constraint_flags.append("location")
    elif _location_regions(preferences) & _location_regions(location) or (
            "hcm" in _location_regions(preferences) and _nearby_locations_allowed(preferences)
            and _location_regions(location) and _location_regions(location) <= _HCM_NEIGHBOR_REGIONS):
        # Code can tell the place fits: drop a location flag the AI set by mistake. Remote jobs keep
        # an AI flag, which may mean "remote only for residents of another country".
        job.constraint_flags = [flag for flag in job.constraint_flags if flag != "location"]
    if _work_mode_conflict(profile.criteria.work_modes, job.work_mode) and "work_mode" not in job.constraint_flags:
        job.constraint_flags.append("work_mode")

    skill_hits = _match_terms(_cv_skills(profile), f"{job.title}\n{source_text}".casefold())
    score = {"primary": 70, "adjacent": 50, "stretch": 20, "none": 0}[detected]
    score += min(30, 10 * len(set(skill_hits)))
    effective_job_level = _normalize_level(job_level or job.title)
    level_gap = (_LEVELS.get(effective_job_level, -1) - _LEVELS.get(user_level, -1)
                 if effective_job_level and user_level else 0)
    try:
        years_gap = (float(job_years) >= float(user_years or 0) + 2
                     if job_years is not None and user_years is not None else False)
    except (TypeError, ValueError):
        years_gap = False
    level_capped = level_gap >= 2 or years_gap
    if level_capped:
        if "level" not in job.constraint_flags:
            job.constraint_flags.append("level")
        score = min(35, score)
    elif level_gap == 1:
        score = min(65, score)

    for flag, penalty in (("location", 30), ("work_mode", 20), ("salary", 20)):
        if flag in job.constraint_flags:
            score -= penalty
    job.match_score = max(0, min(100, score))
    level_note = f"; cấp bậc {effective_job_level}" if effective_job_level else ""
    job.match_reason = f"Vai trò {detected}: {job.title}{level_note}"
    if skill_hits:
        job.match_reason += f"; kỹ năng: {', '.join(dict.fromkeys(skill_hits[:4]))}"
    job.match_reason = job.match_reason[:140]
    return job
