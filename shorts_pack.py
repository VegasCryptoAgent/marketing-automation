"""Per-platform Shorts / vertical-video publish preflight for Autopilot.

Idea (not source) from ivanchik-byte/ShortsMCP (MIT): check duration and
aspect per network, then adapt title, caption, and hashtags to that
network's limits. Cold-reader copy gate idea from amitdeshmukh/banger-ads
(MIT): flag surveillance phrasing and label/pill fragments. Original
implementation for 6Frame Studio Autopilot — deterministic and advisory
only. Publishing still goes through hashtags.py, youtube_shorts_title,
uses_vertical_media, and PostProxy.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from hashtags import (
    PLATFORM_HASHTAG_COUNTS,
    apply_hashtags_to_caption,
    apply_hashtags_to_twitter_thread,
    collect_hashtag_pool,
    hashtags_for_platform,
    strip_trailing_hashtag_paragraph,
    truncate_to_limit,
)

SOURCE = "shorts-pack-1.0"
DEFAULT_PLATFORMS = (
    "twitter",
    "linkedin",
    "instagram",
    "tiktok",
    "youtube",
    "facebook",
    "threads",
)
YOUTUBE_TITLE_LIMIT = 100
YOUTUBE_SHORTS_SUFFIX = " #Shorts"
TWITTER_CHAR_LIMIT = 280
RATIO_SLACK = 0.08

# Bret's Autopilot set: 9:16 for IG / TikTok / YouTube Shorts / Facebook;
# 16:9 landscape only for LinkedIn and X; Threads accepts 9:16 or 1:1.
PLATFORM_RULES: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "want_vertical": True,
        "accept_square": False,
        "title_limit": 100,
        "caption_limit": 5000,
        "min_duration": 3,
        "max_duration": 180,
        "require_shorts_title": True,
    },
    "tiktok": {
        "want_vertical": True,
        "accept_square": False,
        "title_limit": None,
        "caption_limit": 2200,
        "min_duration": 3,
        "max_duration": 600,
        "require_shorts_title": False,
    },
    "instagram": {
        "want_vertical": True,
        "accept_square": False,
        "title_limit": None,
        "caption_limit": 2200,
        "min_duration": 3,
        "max_duration": 90,
        "require_shorts_title": False,
    },
    "facebook": {
        "want_vertical": True,
        "accept_square": False,
        "title_limit": None,
        "caption_limit": 2200,
        "min_duration": None,
        "max_duration": None,
        "require_shorts_title": False,
    },
    "twitter": {
        "want_vertical": False,
        "accept_square": False,
        "title_limit": None,
        "caption_limit": TWITTER_CHAR_LIMIT,
        "min_duration": None,
        "max_duration": None,
        "require_shorts_title": False,
    },
    "linkedin": {
        "want_vertical": False,
        "accept_square": False,
        "title_limit": None,
        "caption_limit": 3000,
        "min_duration": None,
        "max_duration": None,
        "require_shorts_title": False,
    },
    "threads": {
        "want_vertical": True,
        "accept_square": True,
        "title_limit": None,
        "caption_limit": 500,
        "min_duration": None,
        "max_duration": None,
        "require_shorts_title": False,
    },
}

SURVEILLANCE_PHRASES = (
    "watches your business",
    "keeps an eye on",
    "ai that watches",
)
SURVEILLANCE_RE = re.compile(
    "|".join(re.escape(phrase) for phrase in SURVEILLANCE_PHRASES),
    re.I,
)
SENTENCE_END_RE = re.compile(r"[.!?…]")
VERBISH_RE = re.compile(
    r"\b("
    r"is|are|was|were|be|been|being|am|"
    r"has|have|had|do|does|did|"
    r"can|could|will|would|should|may|might|"
    r"make|makes|made|create|creates|created|"
    r"build|builds|built|generate|generates|generated|"
    r"watch|watches|watched|keep|keeps|kept|"
    r"see|sees|saw|run|runs|ran|cut|cuts|"
    r"edit|edits|shoot|shoots|shot|"
    r"bring|brings|take|takes|get|gets|"
    r"go|goes|here|this|that"
    r")\b",
    re.I,
)
HASHTAG_TOKEN_RE = re.compile(r"#[A-Za-z0-9_]+")


def normalize_platform(name: str) -> str:
    key = (name or "").strip().lower()
    if key in {"x", "twitter/x"}:
        return "twitter"
    return key


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[\s,]+", value.strip())
        return [part for part in parts if part]
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for item in value:
            out.extend(_as_list(item))
        return out
    text = str(value).strip()
    return [text] if text else []


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    number = _as_float(value)
    if number is None:
        return None
    return int(round(number))


def parse_request_payload(
    query: Optional[Mapping[str, Any]] = None,
    body: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge query + JSON body. Body wins on overlap."""
    merged: Dict[str, Any] = {}
    for source in (query, body):
        if not source:
            continue
        for key, value in dict(source).items():
            if value is not None:
                merged[key] = value
    platforms = [normalize_platform(item) for item in _as_list(merged.get("platforms"))]
    platforms = [item for item in platforms if item]
    hashtags = _as_list(merged.get("hashtags"))
    return {
        "title": str(merged.get("title") or "").strip(),
        "description": str(merged.get("description") or "").strip(),
        "hashtags": hashtags,
        "duration_seconds": _as_float(merged.get("duration_seconds")),
        "width": _as_int(merged.get("width")),
        "height": _as_int(merged.get("height")),
        "platforms": platforms or list(DEFAULT_PLATFORMS),
        "video_path": str(merged.get("video_path") or "").strip(),
    }


def infer_aspect(width: Optional[int], height: Optional[int]) -> Tuple[str, Optional[bool]]:
    """Return (aspect label, is_vertical). height > width means vertical."""
    if not width or not height or width <= 0 or height <= 0:
        return "unknown", None
    portrait_ratio = height / width
    landscape_ratio = width / height
    if abs(portrait_ratio - 16 / 9) <= RATIO_SLACK:
        return "9:16", True
    if abs(landscape_ratio - 16 / 9) <= RATIO_SLACK:
        return "16:9", False
    if abs(landscape_ratio - 1.0) <= RATIO_SLACK:
        return "1:1", False
    if height > width:
        return "9:16", True
    return "16:9", False


def adapt_youtube_title(title: str, description: str = "") -> str:
    """Match Autopilot youtube_shorts_title: ≤100 chars and always #Shorts."""
    raw = (title or description or "6Frame Studio").strip()
    raw = raw.split("\n", 1)[0].strip()
    raw = re.sub(r"(?:^|\s)#shorts\b", "", raw, flags=re.I).strip()
    budget = YOUTUBE_TITLE_LIMIT - len(YOUTUBE_SHORTS_SUFFIX)
    if len(raw) > budget:
        cut = raw[:budget]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        raw = cut.rstrip(" -|:;,")
    if not raw:
        raw = "6Frame Studio"
    return f"{raw}{YOUTUBE_SHORTS_SUFFIX}"[:YOUTUBE_TITLE_LIMIT]


def _caption_body_for_gate(text: str) -> str:
    cleaned = HASHTAG_TOKEN_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def copy_gate_issues(title: str, description: str) -> List[Dict[str, str]]:
    """Deterministic cold-reader flags. Never calls a model."""
    issues: List[Dict[str, str]] = []
    blob = " ".join(part for part in (title, description) if part)
    match = SURVEILLANCE_RE.search(blob)
    if match:
        issues.append({
            "severity": "WARNING",
            "message": (
                f'Surveillance phrasing: "{match.group(0)}" reads like monitoring copy.'
            ),
        })
    caption = _caption_body_for_gate(description)
    if caption:
        words = caption.split()
        title_case_pill = (
            1 <= len(words) <= 5
            and all(word[:1].isupper() for word in words if word[:1].isalpha())
        )
        short_and_verbless = len(words) <= 6 and not VERBISH_RE.search(caption)
        if not SENTENCE_END_RE.search(caption) and (short_and_verbless or title_case_pill):
            issues.append({
                "severity": "WARNING",
                "message": "Caption looks like a label/pill fragment rather than a sentence.",
            })
    return issues


def _hashtag_bounds(platform: str) -> Tuple[int, int]:
    key = normalize_platform(platform)
    return PLATFORM_HASHTAG_COUNTS.get(key, (5, 8))


def _limits_for(platform: str) -> Dict[str, Any]:
    rules = PLATFORM_RULES[platform]
    min_n, max_n = _hashtag_bounds(platform)
    return {
        "title": rules["title_limit"] if rules["title_limit"] is not None else 0,
        "caption": rules["caption_limit"],
        "hashtags_max": max_n,
        "min_duration": rules["min_duration"] if rules["min_duration"] is not None else 0,
        "max_duration": rules["max_duration"] if rules["max_duration"] is not None else 0,
        "want_vertical": bool(rules["want_vertical"]),
    }


def _adapt_title(
    platform: str,
    title: str,
    description: str,
    youtube_title_fn: Optional[Callable[[dict, str], str]] = None,
) -> str:
    rules = PLATFORM_RULES[platform]
    if rules.get("require_shorts_title"):
        if youtube_title_fn:
            return youtube_title_fn({"campaign_title": title, "text": description}, description)
        return adapt_youtube_title(title, description)
    raw = (title or description.split("\n", 1)[0] if description else "").strip()
    limit = rules.get("title_limit")
    if limit:
        return truncate_to_limit(raw, limit)
    return raw


def _adapt_caption(
    platform: str,
    title: str,
    description: str,
    extra_tags: Sequence[str],
    truncate_twitter_fn: Optional[Callable[[str, int], str]] = None,
    twitter_limit: int = TWITTER_CHAR_LIMIT,
) -> Tuple[str, List[str]]:
    post = {
        "campaign_title": title,
        "title": title,
        "text": description or title,
        "instagram_caption": description or title,
        "suggested_hashtags": list(extra_tags),
    }
    pool = collect_hashtag_pool(post, extra_tags=extra_tags, extra_texts=[title, description])
    tags = hashtags_for_platform(pool, platform)
    body = description or title
    limit = int(PLATFORM_RULES[platform]["caption_limit"])
    if platform in {"twitter", "x"}:
        tagged = apply_hashtags_to_twitter_thread([body], tags, limit=twitter_limit)
        caption = tagged[0] if tagged else ""
        if truncate_twitter_fn and len(caption) > twitter_limit:
            caption = truncate_twitter_fn(caption, twitter_limit)
        return caption, tags
    caption = apply_hashtags_to_caption(body, tags)
    if limit and len(caption) > limit:
        body_only, _ = strip_trailing_hashtag_paragraph(caption)
        suffix = "\n\n" + " ".join(tags) if tags else ""
        budget = max(1, limit - len(suffix))
        caption = apply_hashtags_to_caption(truncate_to_limit(body_only, budget), tags)
    return caption, tags


def _platform_issues(
    platform: str,
    *,
    title: str,
    caption: str,
    tags: Sequence[str],
    aspect: str,
    is_vertical: Optional[bool],
    duration_seconds: Optional[float],
    copy_issues: Sequence[Mapping[str, str]],
) -> List[Dict[str, str]]:
    rules = PLATFORM_RULES[platform]
    issues: List[Dict[str, str]] = [dict(item) for item in copy_issues]
    min_n, max_n = _hashtag_bounds(platform)

    if duration_seconds is None:
        issues.append({"severity": "WARNING", "message": "Duration missing — cannot confirm length."})
    else:
        min_d = rules.get("min_duration")
        max_d = rules.get("max_duration")
        if min_d is not None and duration_seconds < min_d:
            issues.append({
                "severity": "ERROR",
                "message": f"Duration {duration_seconds:g}s is under the {min_d}s minimum.",
            })
        if max_d is not None and duration_seconds > max_d:
            issues.append({
                "severity": "ERROR",
                "message": f"Duration {duration_seconds:g}s is over the {max_d}s maximum.",
            })

    want_vertical = bool(rules["want_vertical"])
    accept_square = bool(rules.get("accept_square"))
    if aspect == "unknown" or is_vertical is None:
        issues.append({"severity": "WARNING", "message": "Aspect missing — cannot confirm 9:16 vs 16:9."})
    elif want_vertical:
        if accept_square and aspect == "1:1":
            pass
        elif not is_vertical:
            issues.append({
                "severity": "ERROR",
                "message": "Aspect is landscape; this network wants 9:16 vertical.",
            })
    elif is_vertical:
        # Landscape-preferred (LinkedIn / X). Advisory WARN, not a hard NO-GO —
        # Autopilot still publishes via PostProxy with its own media split.
        issues.append({
            "severity": "WARNING",
            "message": "Vertical clip on a landscape-preferred network (16:9 for LinkedIn / X).",
        })

    title_limit = rules.get("title_limit")
    if title_limit and len(title) > title_limit:
        issues.append({
            "severity": "ERROR",
            "message": f"Title is {len(title)} chars; limit is {title_limit}.",
        })
    if rules.get("require_shorts_title") and "#shorts" not in title.lower():
        issues.append({"severity": "ERROR", "message": "YouTube Shorts title must include #Shorts."})

    caption_limit = rules.get("caption_limit")
    if caption_limit and len(caption) > caption_limit:
        issues.append({
            "severity": "ERROR",
            "message": f"Caption is {len(caption)} chars; limit is {caption_limit}.",
        })

    if len(tags) < min_n:
        issues.append({
            "severity": "WARNING",
            "message": f"Only {len(tags)} hashtags; {platform} wants {min_n}–{max_n}.",
        })
    if len(tags) > max_n:
        issues.append({
            "severity": "WARNING",
            "message": f"{len(tags)} hashtags exceeds the {max_n} cap for {platform}.",
        })

    return issues


def _status_from_issues(issues: Sequence[Mapping[str, str]]) -> str:
    if any(item.get("severity") == "ERROR" for item in issues):
        return "NO-GO"
    if issues:
        return "WARN"
    return "GO"


def _summary_line(platforms: Sequence[Mapping[str, Any]], vertical: Optional[bool], duration: Optional[float]) -> str:
    counts = {"GO": 0, "WARN": 0, "NO-GO": 0}
    for row in platforms:
        counts[row.get("status") or "WARN"] = counts.get(row.get("status") or "WARN", 0) + 1
    shape = "vertical" if vertical else ("landscape" if vertical is False else "unknown aspect")
    length = f"{duration:g}s" if duration is not None else "no duration"
    return (
        f"{counts['GO']} GO · {counts['WARN']} WARN · {counts['NO-GO']} NO-GO · {shape}, {length}. "
        "Advisory only — Autopilot still uses PostProxy."
    )


def build_shorts_pack(
    payload: Optional[Mapping[str, Any]] = None,
    *,
    youtube_title_fn: Optional[Callable[[dict, str], str]] = None,
    truncate_twitter_fn: Optional[Callable[[str, int], str]] = None,
    twitter_limit: int = TWITTER_CHAR_LIMIT,
    probe_duration_fn: Optional[Callable[[str], Optional[float]]] = None,
) -> Dict[str, Any]:
    parsed = parse_request_payload({}, payload or {})
    duration = parsed["duration_seconds"]
    video_path = parsed.get("video_path") or ""
    if probe_duration_fn and video_path:
        try:
            probed = probe_duration_fn(video_path)
        except Exception:
            probed = None
        if probed is not None:
            duration = probed

    aspect, is_vertical = infer_aspect(parsed["width"], parsed["height"])
    copy_issues = copy_gate_issues(parsed["title"], parsed["description"])
    rows: List[Dict[str, Any]] = []
    for raw_name in parsed["platforms"]:
        platform = normalize_platform(raw_name)
        if platform not in PLATFORM_RULES:
            continue
        title = _adapt_title(platform, parsed["title"], parsed["description"], youtube_title_fn)
        caption, tags = _adapt_caption(
            platform,
            parsed["title"],
            parsed["description"],
            parsed["hashtags"],
            truncate_twitter_fn=truncate_twitter_fn,
            twitter_limit=twitter_limit,
        )
        issues = _platform_issues(
            platform,
            title=title,
            caption=caption,
            tags=tags,
            aspect=aspect,
            is_vertical=is_vertical,
            duration_seconds=duration,
            copy_issues=copy_issues,
        )
        rows.append({
            "platform": platform,
            "status": _status_from_issues(issues),
            "aspect": aspect,
            "title": title,
            "caption": caption,
            "hashtags": tags,
            "limits": _limits_for(platform),
            "issues": issues,
        })

    return {
        "ok": True,
        "source": SOURCE,
        "vertical": bool(is_vertical),
        "duration_seconds": duration,
        "summary": _summary_line(rows, is_vertical, duration),
        "platforms": rows,
    }
