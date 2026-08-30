"""Keyless public-source radar for the Live Trend Scanner.

Velocity radar idea inspired by ViralRadar (MIT); original implementation.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import statistics
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote, urlparse

import requests

logger = logging.getLogger("radar")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("STATE_DIR") or os.environ.get("DATA_DIR") or BASE_DIR
SNAPSHOT_FILENAME = "radar_snapshots.json"
SOURCE_TIMEOUT_SEC = 4.0
CACHE_TTL_SEC = 45
MAX_ITEMS = 12
USER_AGENT = "6FrameStudioRadar/1.0 (+https://6framestudio.com; cinematic-ai-video-research)"

# Small allowlist of AI-film / generative-video channels. RSS only — no YouTube API key.
YOUTUBE_CHANNEL_ALLOWLIST = (
    ("UClnFtyUEaxQOCd1s5NKYGFA", "Curious Refuge"),
    ("UC9Ryt3XOGYBoAJVsBHNGDzA", "Theoretically Media"),
    ("UCP7jMXSY2xbc3KCAE0MHQ-A", "Google DeepMind"),
)

WIKIPEDIA_ARTICLES = (
    "Sora_(text-to-video_model)",
    "Text-to-video_model",
    "Artificial_intelligence_art",
    "OpenAI",
    "Runway_AI",
)

HN_QUERIES = ("Seedance", "Sora", "Veo", "Kling AI", "AI video", "AI filmmaking")
NEWS_RSS_URL = (
    "https://news.google.com/rss/search?"
    "q=AI+filmmaking+OR+AI+video+OR+Sora+OR+Kling+OR+Veo+OR+Seedance+OR+Runway+Gen"
    "&hl=en-US&gl=US&ceid=US:en"
)
BLUESKY_QUERY = "AI video Kling Sora Veo Seedance"

NICHE_RE = re.compile(
    r"\b("
    r"sora|seedance|veo(?:\s*[23])?|kling(?:\s*(?:ai|[23](?:\.0)?))?|"
    r"runway(?:\s*(?:ml|gen))?|luma|hailuo|pika|gen-?[34]|"
    r"ai[-\s]?(video|film|cinema|trailer|movie)|text-to-video|"
    r"filmmak|cinematic|motion\s*design|aivideo|generative\s+video"
    r")\b",
    re.I,
)
TOKEN_RE = re.compile(r"[a-z0-9]{4,}")
STOP_TOKENS = {
    "this", "that", "with", "from", "your", "about", "video", "using", "have",
    "just", "into", "over", "after", "more", "some", "what", "when", "make",
    "made", "they", "them", "will", "been", "were", "their", "than", "also",
    "news", "post", "show", "free", "open", "full", "best", "real",
}
WALLED_HOST_MARKERS = ("tiktok.com", "instagram.com", "x.com", "twitter.com")
LIFECYCLES = ("NEW", "EMERGING", "RISING", "HOT", "VIRAL")

SOURCE_ENGAGEMENT_SCALE = {
    "hacker_news": 200.0,
    "bluesky": 80.0,
    "wikipedia": 8000.0,
    "google_news": 36.0,
    "youtube_rss": 36.0,
}
SOURCE_VELOCITY_SCALE = {
    "hacker_news": 25.0,
    "bluesky": 12.0,
    "wikipedia": 400.0,
    "google_news": 8.0,
    "youtube_rss": 8.0,
}

CollectorFn = Callable[[], List[Dict[str, Any]]]

_CACHE_LOCK = threading.Lock()
_SNAPSHOT_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"at": 0.0, "payload": None}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_any_date(value: Any) -> Optional[datetime]:
    parsed = _parse_iso(value)
    if parsed:
        return parsed
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def snapshot_path() -> str:
    return os.path.join(STATE_DIR, SNAPSHOT_FILENAME)


def default_http_get(url: str, timeout: float = SOURCE_TIMEOUT_SEC, **kwargs: Any) -> requests.Response:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, application/rss+xml, application/atom+xml, text/xml, */*",
    }
    extra = kwargs.pop("headers", None) or {}
    headers.update(extra)
    return requests.get(url, timeout=timeout, headers=headers, **kwargs)


def _safe_json(response: requests.Response) -> Any:
    response.raise_for_status()
    return response.json()


def _is_http_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_walled_without_real_url(url: str) -> bool:
    if not _is_http_url(url):
        return True
    host = _host(url)
    if any(host == marker or host.endswith("." + marker) for marker in WALLED_HOST_MARKERS):
        path = urlparse(url).path.strip("/")
        # A bare profile/home link is not a fetched post. Need a real path.
        if not path:
            return True
    return False


def _recency_proxy(age_hours: Optional[float]) -> float:
    if age_hours is None:
        return 8.0
    return max(0.0, 36.0 - float(age_hours))


def _observation(
    *,
    title: str,
    url: str,
    source: str,
    engagement: float,
    observed_at: datetime,
    published_at: Optional[datetime] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    title = (title or "").strip()
    url = (url or "").strip()
    if not title or _is_walled_without_real_url(url):
        return None
    published = published_at or observed_at
    return {
        "title": title[:240],
        "url": url,
        "source": source,
        "engagement": max(0.0, float(engagement)),
        "observed_at": observed_at,
        "published_at": published,
        "metrics": metrics or {},
    }


def collect_or_empty(name: str, collector: CollectorFn) -> List[Dict[str, Any]]:
    """Run one adapter; failed/empty sources always yield []. Never invent rows."""
    try:
        rows = collector() or []
    except Exception as exc:
        logger.warning("Radar adapter %s failed: %s", name, exc)
        return []
    if not isinstance(rows, list):
        return []
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = _observation(
            title=str(row.get("title") or ""),
            url=str(row.get("url") or ""),
            source=str(row.get("source") or name),
            engagement=float(row.get("engagement") or 0.0),
            observed_at=row.get("observed_at") or _utcnow(),
            published_at=row.get("published_at"),
            metrics=row.get("metrics") if isinstance(row.get("metrics"), dict) else {},
        )
        if item:
            cleaned.append(item)
    return cleaned


def collect_hacker_news(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or _utcnow()
    items: List[Dict[str, Any]] = []
    seen_ids = set()
    per_query_timeout = min(1.6, SOURCE_TIMEOUT_SEC)
    for query in HN_QUERIES:
        url = (
            "https://hn.algolia.com/api/v1/search"
            f"?query={quote(query)}"
            "&tags=story&hitsPerPage=8"
        )
        try:
            data = _safe_json(http_get(url, timeout=per_query_timeout))
        except Exception as exc:
            logger.warning("Hacker News query %r failed: %s", query, exc)
            continue
        for hit in data.get("hits") or []:
            object_id = hit.get("objectID")
            if object_id in seen_ids:
                continue
            title = (hit.get("title") or "").strip()
            if not title or not NICHE_RE.search(title):
                continue
            # Drop obvious non-video collisions (Andreas Kling, airport runways).
            lowered = title.lower()
            if "andreas kling" in lowered or "airport" in lowered or "runway name" in lowered:
                continue
            story_url = (hit.get("url") or "").strip()
            hn_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
            final_url = story_url if _is_http_url(story_url) else hn_url
            published = _parse_iso(hit.get("created_at")) or now
            points = float(hit.get("points") or 0)
            comments = float(hit.get("num_comments") or 0)
            item = _observation(
                title=title,
                url=final_url,
                source="hacker_news",
                engagement=points + (comments * 0.25),
                observed_at=now,
                published_at=published,
                metrics={"points": points, "comments": comments, "query": query},
            )
            if item:
                seen_ids.add(object_id)
                items.append(item)
        if len(items) >= 12:
            break
    return items


def collect_google_news(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or _utcnow()
    response = http_get(NEWS_RSS_URL, timeout=SOURCE_TIMEOUT_SEC)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items: List[Dict[str, Any]] = []
    for node in root.findall(".//item")[:18]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        pub = _parse_any_date(node.findtext("pubDate")) or now
        age_hours = max(0.0, (now - pub).total_seconds() / 3600.0)
        if not title or not NICHE_RE.search(title):
            continue
        item = _observation(
            title=title,
            url=link,
            source="google_news",
            engagement=_recency_proxy(age_hours),
            observed_at=now,
            published_at=pub,
            metrics={"age_hours": round(age_hours, 2)},
        )
        if item:
            items.append(item)
    return items


def collect_youtube_rss(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or _utcnow()
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    items: List[Dict[str, Any]] = []
    for channel_id, label in YOUTUBE_CHANNEL_ALLOWLIST:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            response = http_get(feed_url, timeout=min(2.0, SOURCE_TIMEOUT_SEC))
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as exc:
            logger.warning("YouTube RSS failed for %s: %s", label, exc)
            continue
        for entry in root.findall("atom:entry", ns)[:4]:
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            href = (link_el.get("href") if link_el is not None else "") or ""
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns) or ""
            if not href and video_id:
                href = f"https://www.youtube.com/watch?v={video_id}"
            published = _parse_iso(entry.findtext("atom:published", default="", namespaces=ns)) or now
            age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
            if age_hours > 168:
                continue
            item = _observation(
                title=title or f"{label} upload",
                url=href,
                source="youtube_rss",
                engagement=_recency_proxy(age_hours),
                observed_at=now,
                published_at=published,
                metrics={"channel": label, "video_id": video_id, "age_hours": round(age_hours, 2)},
            )
            if item:
                items.append(item)
    return items


def collect_bluesky(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or _utcnow()
    url = (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"
        f"?q={quote(BLUESKY_QUERY)}&limit=20&sort=latest"
    )
    data = _safe_json(http_get(url, timeout=SOURCE_TIMEOUT_SEC))
    items: List[Dict[str, Any]] = []
    for post in data.get("posts") or []:
        author = post.get("author") or {}
        record = post.get("record") or {}
        handle = (author.get("handle") or "").strip()
        uri = (post.get("uri") or "").strip()
        rkey = uri.rsplit("/", 1)[-1] if uri else ""
        href = f"https://bsky.app/profile/{handle}/post/{rkey}" if handle and rkey else ""
        text = (record.get("text") or "").strip()
        if not text or not NICHE_RE.search(text):
            continue
        likes = float(post.get("likeCount") or 0)
        replies = float(post.get("replyCount") or 0)
        reposts = float(post.get("repostCount") or 0)
        published = _parse_iso(record.get("createdAt") or post.get("indexedAt")) or now
        item = _observation(
            title=text.split("\n", 1)[0][:180],
            url=href,
            source="bluesky",
            engagement=likes + (reposts * 1.5) + (replies * 0.5),
            observed_at=now,
            published_at=published,
            metrics={"likes": likes, "replies": replies, "reposts": reposts, "handle": handle},
        )
        if item:
            items.append(item)
    return items


def collect_wikipedia_pageviews(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    now = now or _utcnow()
    end = (now.date() - timedelta(days=1)).strftime("%Y%m%d")
    start = (now.date() - timedelta(days=8)).strftime("%Y%m%d")
    items: List[Dict[str, Any]] = []
    for article in WIKIPEDIA_ARTICLES:
        api = (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"en.wikipedia/all-access/all-agents/{quote(article, safe='()')}/daily/{start}/{end}"
        )
        try:
            data = _safe_json(http_get(api, timeout=min(2.0, SOURCE_TIMEOUT_SEC)))
        except Exception as exc:
            logger.warning("Wikipedia pageviews failed for %s: %s", article, exc)
            continue
        series = data.get("items") or []
        if len(series) < 2:
            continue
        latest = float(series[-1].get("views") or 0)
        previous = float(series[-2].get("views") or 0)
        views = [float(row.get("views") or 0) for row in series]
        title = article.replace("_", " ")
        wiki_url = f"https://en.wikipedia.org/wiki/{article}"
        item = _observation(
            title=f"{title} pageviews",
            url=wiki_url,
            source="wikipedia",
            engagement=latest,
            observed_at=now,
            published_at=now - timedelta(hours=12),
            metrics={
                "views_yesterday": latest,
                "views_day_before": previous,
                "views_series": views,
            },
        )
        if item:
            items.append(item)
    return items


def default_collectors(http_get: Callable = default_http_get, now: Optional[datetime] = None) -> List[Tuple[str, CollectorFn]]:
    return [
        ("hacker_news", lambda: collect_hacker_news(http_get=http_get, now=now)),
        ("google_news", lambda: collect_google_news(http_get=http_get, now=now)),
        ("youtube_rss", lambda: collect_youtube_rss(http_get=http_get, now=now)),
        ("bluesky", lambda: collect_bluesky(http_get=http_get, now=now)),
        ("wikipedia", lambda: collect_wikipedia_pageviews(http_get=http_get, now=now)),
    ]


def gather_observations(
    collectors: Sequence[Tuple[str, CollectorFn]],
    timeout: float = SOURCE_TIMEOUT_SEC,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    if not collectors:
        return [], [], []
    observations: List[Dict[str, Any]] = []
    used: List[str] = []
    failed: List[str] = []
    with ThreadPoolExecutor(max_workers=len(collectors)) as pool:
        future_map = {
            pool.submit(collect_or_empty, name, fn): name
            for name, fn in collectors
        }
        done, pending = wait(future_map.keys(), timeout=timeout + 0.8)
        for fut in pending:
            name = future_map[fut]
            failed.append(name)
            fut.cancel()
        for fut in done:
            name = future_map[fut]
            try:
                rows = fut.result()
            except Exception as exc:
                logger.warning("Radar adapter %s failed: %s", name, exc)
                failed.append(name)
                continue
            if rows:
                used.append(name)
                observations.extend(rows)
            else:
                failed.append(name)
    return observations, used, failed


def story_tokens(title: str) -> set:
    return {tok for tok in TOKEN_RE.findall((title or "").lower()) if tok not in STOP_TOKENS}


def _log_norm(value: float, scale: float) -> float:
    scale = max(1.0, float(scale))
    return min(1.0, math.log1p(max(0.0, float(value))) / math.log1p(scale))


def freshness_score(age_hours: Optional[float]) -> float:
    if age_hours is None:
        return 0.45
    if age_hours <= 0:
        return 1.0
    if age_hours >= 48:
        return 0.05
    return max(0.05, 1.0 - (float(age_hours) / 48.0))


def anomaly_score(value: float, samples: Sequence[float]) -> float:
    if len(samples) < 3:
        return 0.0
    mean = statistics.mean(samples)
    stdev = statistics.pstdev(samples)
    if stdev <= 1e-6:
        return 1.0 if value > mean else 0.0
    z = (float(value) - mean) / stdev
    return max(0.0, min(1.0, z / 3.0))


def lifecycle_label(score: float, velocity_norm: float, first_seen: bool) -> str:
    if score >= 82 and (velocity_norm >= 0.40 or not first_seen):
        return "VIRAL"
    if score >= 70:
        return "HOT"
    if score >= 52:
        return "RISING"
    if score >= 32:
        return "EMERGING"
    return "NEW"


def _cross_source_urls(observations: Sequence[Dict[str, Any]]) -> set:
    flagged = set()
    token_map = [(row["url"], row["source"], story_tokens(row["title"])) for row in observations]
    for i, (url_a, source_a, tokens_a) in enumerate(token_map):
        for url_b, source_b, tokens_b in token_map[i + 1 :]:
            if source_a == source_b or not tokens_a or not tokens_b:
                continue
            if len(tokens_a & tokens_b) >= 2:
                flagged.add(url_a)
                flagged.add(url_b)
    return flagged


def load_snapshot(path: Optional[str] = None) -> Dict[str, Any]:
    target = path or snapshot_path()
    if not os.path.exists(target):
        return {"updated_at": None, "items": {}, "source_engagements": {}}
    try:
        with open(target, "r") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {"updated_at": None, "items": {}, "source_engagements": {}}
        data.setdefault("items", {})
        data.setdefault("source_engagements", {})
        return data
    except Exception as exc:
        logger.warning("Radar snapshot unreadable (%s): %s", target, exc)
        return {"updated_at": None, "items": {}, "source_engagements": {}}


def save_snapshot(snapshot: Dict[str, Any], path: Optional[str] = None) -> None:
    target = path or snapshot_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = f"{target}.{os.getpid()}.tmp"
    with _SNAPSHOT_LOCK:
        with open(tmp, "w") as handle:
            json.dump(snapshot, handle)
        os.replace(tmp, target)


def score_observations(
    observations: Sequence[Dict[str, Any]],
    previous_by_url: Optional[Dict[str, Any]] = None,
    source_history: Optional[Dict[str, List[float]]] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Score real observations only. Empty input → []. No invented rows."""
    now = now or _utcnow()
    previous_by_url = previous_by_url or {}
    source_history = source_history or {}
    if not observations:
        return []

    cross_urls = _cross_source_urls(observations)
    scored: List[Dict[str, Any]] = []
    for raw in observations:
        url = raw.get("url") or ""
        if _is_walled_without_real_url(url):
            continue
        source = raw.get("source") or "unknown"
        published = raw.get("published_at") or raw.get("observed_at") or now
        if not isinstance(published, datetime):
            published = _parse_iso(published) or now
        age_hours = max(0.0, (now - published).total_seconds() / 3600.0)
        engagement = float(raw.get("engagement") or 0.0)
        prior = previous_by_url.get(url) if isinstance(previous_by_url.get(url), dict) else None
        first_seen = prior is None
        hours_between = 0.0
        velocity = 0.0
        prior_velocity = 0.0
        if prior:
            prior_at = _parse_iso(prior.get("observed_at")) or (now - timedelta(hours=1))
            hours_between = max((now - prior_at).total_seconds() / 3600.0, 1.0 / 12.0)
            velocity = (engagement - float(prior.get("engagement") or 0.0)) / hours_between
            prior_velocity = float(prior.get("velocity") or 0.0)
        elif source == "wikipedia":
            series = (raw.get("metrics") or {}).get("views_series") or []
            if len(series) >= 2:
                velocity = (float(series[-1]) - float(series[-2])) / 24.0
                first_seen = False
                hours_between = 24.0

        acceleration = velocity - prior_velocity if prior else 0.0
        eng_scale = SOURCE_ENGAGEMENT_SCALE.get(source, 100.0)
        vel_scale = SOURCE_VELOCITY_SCALE.get(source, 20.0)
        history = source_history.get(source) or []
        if source == "wikipedia":
            history = (raw.get("metrics") or {}).get("views_series") or history

        engagement_n = _log_norm(engagement, eng_scale)
        freshness_n = freshness_score(age_hours)
        velocity_n = _log_norm(max(0.0, velocity), vel_scale)
        acceleration_n = _log_norm(max(0.0, acceleration), vel_scale)
        anomaly_n = anomaly_score(engagement, history)
        cross_n = 1.0 if url in cross_urls else 0.0

        if first_seen:
            score = 100.0 * (
                0.55 * engagement_n
                + 0.35 * freshness_n
                + 0.10 * cross_n
            )
            confidence = 0.30
        else:
            score = 100.0 * (
                0.30 * velocity_n
                + 0.15 * acceleration_n
                + 0.20 * anomaly_n
                + 0.15 * freshness_n
                + 0.10 * cross_n
                + 0.10 * engagement_n
            )
            confidence = min(0.92, 0.55 + 0.20 * min(1.0, hours_between / 2.0) + 0.10 * anomaly_n)

        score = max(0.0, min(100.0, round(score, 1)))
        confidence = max(0.0, min(1.0, round(confidence, 2)))
        lifecycle = lifecycle_label(score, velocity_n, first_seen)
        metrics = dict(raw.get("metrics") or {})
        metrics.update({
            "engagement": round(engagement, 2),
            "velocity_per_hour": round(velocity, 3),
            "acceleration": round(acceleration, 3),
            "age_hours": round(age_hours, 2),
            "first_seen": first_seen,
            "cross_source": bool(cross_n),
        })
        scored.append({
            "title": raw.get("title") or "",
            "url": url,
            "source": source,
            "score": score,
            "confidence": confidence,
            "lifecycle": lifecycle,
            "metrics": metrics,
            "observedAt": _iso(now),
        })

    scored.sort(key=lambda row: (row["score"], row["confidence"]), reverse=True)
    deduped: List[Dict[str, Any]] = []
    seen_urls = set()
    for row in scored:
        if row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        deduped.append(row)
        if len(deduped) >= MAX_ITEMS:
            break
    return deduped


def persist_from_items(
    items: Sequence[Dict[str, Any]],
    previous: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    now = now or _utcnow()
    previous = previous or load_snapshot(path)
    stored_items = dict(previous.get("items") or {})
    source_engagements = {
        key: list(values[-39:])
        for key, values in (previous.get("source_engagements") or {}).items()
        if isinstance(values, list)
    }
    for item in items:
        url = item.get("url")
        if not url:
            continue
        metrics = item.get("metrics") or {}
        stored_items[url] = {
            "title": item.get("title"),
            "source": item.get("source"),
            "engagement": metrics.get("engagement", 0),
            "velocity": metrics.get("velocity_per_hour", 0),
            "observed_at": item.get("observedAt") or _iso(now),
        }
        source = item.get("source") or "unknown"
        source_engagements.setdefault(source, [])
        source_engagements[source].append(float(metrics.get("engagement") or 0))
        source_engagements[source] = source_engagements[source][-40:]
    snapshot = {
        "updated_at": _iso(now),
        "items": stored_items,
        "source_engagements": source_engagements,
    }
    save_snapshot(snapshot, path)
    return snapshot


def format_evidence_pack(items: Sequence[Dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [
        "PUBLIC RADAR EVIDENCE — real titles and URLs observed from keyless public sources.",
        "HARD RULE: Prefer these URLs. Do not invent, guess, or reconstruct links.",
        "Do not emit TikTok, X/Twitter, or Instagram rows unless the exact URL appears below.",
        "",
    ]
    for idx, item in enumerate(items[:MAX_ITEMS], 1):
        lines.append(
            f"{idx}. [{item.get('lifecycle')} score={item.get('score')} conf={item.get('confidence')}] "
            f"{item.get('source')}: {item.get('title')} | URL: {item.get('url')}"
        )
    return "\n".join(lines)


def _summarize(items: Sequence[Dict[str, Any]], used: Iterable[str], failed: Iterable[str]) -> str:
    used_list = list(used)
    failed_list = list(failed)
    if not items:
        if failed_list and not used_list:
            return "Radar adapters returned nothing (timeouts or empty public feeds)."
        return "No public cinematic-AI observations this pass."
    top = items[0]
    sources = sorted({item.get("source") for item in items if item.get("source")})
    return (
        f"{len(items)} observed items from {', '.join(sources)}. "
        f"Lead: {top.get('lifecycle')} {top.get('score')} — {top.get('title')}. "
        f"Failed adapters: {', '.join(failed_list) or 'none'}."
    )


def run_radar(
    collectors: Optional[Sequence[Tuple[str, CollectorFn]]] = None,
    now: Optional[datetime] = None,
    snapshot_file: Optional[str] = None,
    persist: bool = True,
    refresh: bool = False,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Collect, score, and optionally persist a radar pass. Never invents rows."""
    now = now or _utcnow()
    if use_cache and not refresh and collectors is None:
        with _CACHE_LOCK:
            payload = _CACHE.get("payload")
            cached_at = float(_CACHE.get("at") or 0)
        if payload and (now.timestamp() - cached_at) < CACHE_TTL_SEC:
            return payload

    active = list(collectors) if collectors is not None else default_collectors(now=now)
    observations, used, failed = gather_observations(active)
    previous = load_snapshot(snapshot_file)
    items = score_observations(
        observations,
        previous_by_url=previous.get("items") or {},
        source_history=previous.get("source_engagements") or {},
        now=now,
    )
    if persist:
        persist_from_items(items, previous=previous, now=now, path=snapshot_file)

    payload = {
        "items": items,
        "summary": _summarize(items, used, failed),
    }
    if collectors is None:
        with _CACHE_LOCK:
            _CACHE["at"] = now.timestamp()
            _CACHE["payload"] = payload
    return payload
