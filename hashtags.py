"""Guaranteed hashtags for Autopilot / PostProxy captions.

Gemini copy often omits tags. Apply/merge them at publish time so every
platform caption ends with a dedicated hashtag paragraph.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

BRAND_HASHTAGS = ["#6FrameStudio", "#AIFilmmaking", "#AICinema"]

# Inclusive counts. X stays tiny; LinkedIn/Facebook stay moderate; Reels/Shorts get more.
PLATFORM_HASHTAG_COUNTS: Dict[str, Tuple[int, int]] = {
    "linkedin": (5, 8),
    "facebook": (5, 8),
    "threads": (5, 8),
    "instagram": (8, 12),
    "tiktok": (8, 12),
    "youtube": (8, 12),
    "twitter": (1, 2),
    "x": (1, 2),
}

INSTAGRAM_STYLE_PLATFORMS = {"instagram", "tiktok"}

HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]{1,100})")

CANONICAL_TAG_CASE = {
    "#6framestudio": "#6FrameStudio",
    "#aifilmmaking": "#AIFilmmaking",
    "#aicinema": "#AICinema",
    "#klingai": "#KlingAI",
    "#kling": "#KlingAI",
    "#sora": "#Sora",
    "#soraai": "#Sora",
    "#runwayml": "#RunwayML",
    "#runway": "#RunwayML",
    "#runwaygen3": "#RunwayGen3",
    "#veo": "#Veo",
    "#veovideo": "#Veo",
    "#luma": "#LumaDreamMachine",
    "#lumadreammachine": "#LumaDreamMachine",
    "#midjourney": "#Midjourney",
    "#aivideo": "#AIvideo",
    "#cinematictrailer": "#CinematicTrailer",
    "#generativeai": "#GenerativeAI",
    "#aiart": "#AIArt",
    "#cinematography": "#Cinematography",
    "#visualeffects": "#VisualEffects",
    "#motiondesign": "#MotionDesign",
    "#shortfilm": "#ShortFilm",
    "#shorts": "#Shorts",
}

TOOL_TAG_PATTERNS = (
    (re.compile(r"\bkling\b", re.I), "#KlingAI"),
    (re.compile(r"\bsora\b", re.I), "#Sora"),
    (re.compile(r"\brunway\b", re.I), "#RunwayML"),
    (re.compile(r"\bveo\b", re.I), "#Veo"),
    (re.compile(r"\bluma\b", re.I), "#LumaDreamMachine"),
    (re.compile(r"\bmidjourney\b", re.I), "#Midjourney"),
    (re.compile(r"\bpika\b", re.I), "#Pika"),
    (re.compile(r"\bhailuo\b", re.I), "#Hailuo"),
    (re.compile(r"\bminimax\b", re.I), "#MiniMax"),
    (re.compile(r"cinematic\s+trailer", re.I), "#CinematicTrailer"),
    (re.compile(r"\b(?:ai[\s-]*)?(?:short[\s-]*)?film", re.I), "#ShortFilm"),
    (re.compile(r"\bai[\s-]*video", re.I), "#AIvideo"),
)

FALLBACK_TOPIC_TAGS = [
    "#AIvideo",
    "#CinematicTrailer",
    "#GenerativeAI",
    "#Cinematography",
    "#VisualEffects",
    "#MotionDesign",
    "#AIArt",
    "#ShortFilm",
]


def normalize_hashtag(raw: str) -> str:
    token = (raw or "").strip()
    if not token:
        return ""
    token = token if token.startswith("#") else f"#{token}"
    match = HASHTAG_RE.match(token)
    if not match:
        cleaned = re.sub(r"[^A-Za-z0-9_]", "", token.lstrip("#"))
        if not cleaned or not re.search(r"[A-Za-z]", cleaned):
            return ""
        token = f"#{cleaned}"
    else:
        token = f"#{match.group(1)}"
    if not re.search(r"[A-Za-z]", token):
        return ""
    return CANONICAL_TAG_CASE.get(token.lower(), token)


def extract_hashtags(text: str) -> List[str]:
    found: List[str] = []
    seen = set()
    for match in HASHTAG_RE.finditer(text or ""):
        tag = normalize_hashtag(f"#{match.group(1)}")
        key = tag.lower()
        if tag and key not in seen:
            seen.add(key)
            found.append(tag)
    return found


def _is_hashtag_only_line(line: str) -> bool:
    stripped = (line or "").strip()
    if not stripped or not extract_hashtags(stripped):
        return False
    leftover = HASHTAG_RE.sub("", stripped)
    leftover = re.sub(r"[\s,;·•|/]+", "", leftover)
    return leftover == ""


def strip_trailing_hashtag_paragraph(text: str) -> Tuple[str, List[str]]:
    """Remove a trailing hashtag-only paragraph; keep hook text intact."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.strip():
        return "", []
    lines = raw.split("\n")
    collected: List[str] = []
    while lines:
        last = lines[-1]
        if not last.strip():
            lines.pop()
            continue
        if _is_hashtag_only_line(last):
            lines.pop()
            collected = extract_hashtags(last) + collected
            continue
        break
    body = "\n".join(lines).rstrip()
    return body, _dedupe_hashtags(collected)


def infer_topic_hashtags(*texts: str) -> List[str]:
    blob = " ".join(part for part in texts if part)
    if not blob:
        return []
    found: List[str] = []
    seen = set()
    for pattern, tag in TOOL_TAG_PATTERNS:
        if pattern.search(blob):
            key = tag.lower()
            if key not in seen:
                seen.add(key)
                found.append(tag)
    return found


def _dedupe_hashtags(tags: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in tags:
        tag = normalize_hashtag(raw)
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        out.append(tag)
    return out


def collect_hashtag_pool(
    post: Optional[dict] = None,
    extra_tags: Optional[Sequence[str]] = None,
    extra_texts: Optional[Sequence[str]] = None,
) -> List[str]:
    post = post or {}
    texts = [
        post.get("campaign_title") or "",
        post.get("title") or "",
        post.get("source_url") or "",
        post.get("text") or "",
        post.get("instagram_caption") or "",
        post.get("recreated_instagram_caption") or "",
        post.get("repurposed_instagram_caption") or "",
    ]
    if extra_texts:
        texts.extend(extra_texts)
    if post.get("thread"):
        texts.extend(str(part) for part in post.get("thread") or [])

    suggested = list(post.get("suggested_hashtags") or [])
    if extra_tags:
        suggested.extend(extra_tags)

    pool = _dedupe_hashtags(
        [
            *BRAND_HASHTAGS,
            *infer_topic_hashtags(*texts),
            *suggested,
            *extract_hashtags("\n".join(str(t) for t in texts if t)),
            *FALLBACK_TOPIC_TAGS,
        ]
    )
    return pool


def hashtags_for_platform(pool: Sequence[str], platform: str) -> List[str]:
    key = (platform or "").lower()
    if key == "x":
        key = "twitter"
    min_n, max_n = PLATFORM_HASHTAG_COUNTS.get(key, (5, 8))
    cleaned = _dedupe_hashtags(pool)
    if key == "youtube":
        cleaned = [tag for tag in cleaned if tag.lower() != "#shorts"]
        brand = [tag for tag in cleaned if tag in BRAND_HASHTAGS]
        rest = [tag for tag in cleaned if tag not in BRAND_HASHTAGS]
        cleaned = _dedupe_hashtags([*brand, "#Shorts", *rest])
    if len(cleaned) < min_n:
        cleaned = _dedupe_hashtags([*cleaned, *FALLBACK_TOPIC_TAGS, *BRAND_HASHTAGS])
    return cleaned[:max_n]


def apply_hashtags_to_caption(text: str, tags: Sequence[str]) -> str:
    body, existing = strip_trailing_hashtag_paragraph(text or "")
    # Incoming tags are already platform-capped. Keep existing only if none were supplied.
    merged = _dedupe_hashtags(tags) if tags else existing
    if not merged:
        return body
    tag_line = " ".join(merged)
    if not body:
        return tag_line
    return f"{body}\n\n{tag_line}"


def truncate_to_limit(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    ellipsis = "…"
    budget = max(1, limit - len(ellipsis))
    cut = text[:budget]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(" ,;:-")
    return (cut or text[:budget]) + ellipsis


def apply_hashtags_to_twitter_thread(
    parts: Optional[Sequence[str]],
    tags: Sequence[str],
    limit: int = 280,
) -> List[str]:
    tweets = [str(part).strip() for part in (parts or []) if str(part).strip()] or [""]
    last_body, existing = strip_trailing_hashtag_paragraph(tweets[-1])
    chosen = _dedupe_hashtags([*tags, *existing])[:2]
    fitted: List[str] = []
    body = last_body
    for tag in chosen:
        candidate = fitted + [tag]
        suffix = "\n\n" + " ".join(candidate)
        if len(body) + len(suffix) <= limit:
            fitted = candidate
            continue
        budget = limit - len(suffix)
        if budget < 8:
            break
        trimmed = truncate_to_limit(body, budget)
        if len(trimmed) + len(suffix) <= limit:
            body = trimmed
            fitted = candidate
        else:
            break
    tweets[-1] = apply_hashtags_to_caption(body, fitted)
    if len(tweets[-1]) > limit:
        tweets[-1] = truncate_to_limit(tweets[-1], limit)
    return [part if len(part) <= limit else truncate_to_limit(part, limit) for part in tweets]


def base_caption_for_platform(post: dict, platform: str) -> str:
    key = (platform or "").lower()
    if key in INSTAGRAM_STYLE_PLATFORMS:
        return (
            (post.get("instagram_caption") or "").strip()
            or (post.get("recreated_instagram_caption") or "").strip()
            or (post.get("repurposed_instagram_caption") or "").strip()
            or (post.get("text") or "")
        )
    return post.get("text") or ""


def apply_platform_hashtags(post: dict, platform: str, limit: Optional[int] = None) -> str:
    key = (platform or "").lower()
    if key in {"twitter", "x"}:
        thread = apply_platform_twitter_thread(post, limit=limit or 280)
        return thread[-1] if thread else ""
    tags = hashtags_for_platform(collect_hashtag_pool(post), key)
    caption = apply_hashtags_to_caption(base_caption_for_platform(post, key), tags)
    if limit and len(caption) > limit:
        # Keep the tag paragraph when possible.
        body, _ = strip_trailing_hashtag_paragraph(caption)
        suffix = "\n\n" + " ".join(tags) if tags else ""
        budget = max(1, limit - len(suffix))
        return apply_hashtags_to_caption(truncate_to_limit(body, budget), tags)
    return caption


def apply_platform_twitter_thread(post: dict, limit: int = 280) -> List[str]:
    existing = post.get("thread")
    if existing:
        parts = [str(item).strip() for item in existing if str(item).strip()]
    else:
        parts = [post.get("text") or ""]
    tags = hashtags_for_platform(collect_hashtag_pool(post), "twitter")
    return apply_hashtags_to_twitter_thread(parts, tags, limit=limit)
