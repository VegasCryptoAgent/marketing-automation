"""Advisory TikTok Photo Mode / Instagram carousel pack for Autopilot.

Idea (not source) from ali-abassi/social-slideshows (MIT): turn a brief into
a 5–7 beat photo-mode / carousel story (hook → tension → mechanism → rule →
close). Original implementation for 6Frame Studio Autopilot — deterministic
branded 9:16 text slides, optional Gemini rewrite in 6Frame voice, advisory
only. Does not publish. Autopilot still posts the viral clip via PostProxy.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from hashtags import (
    BRAND_HASHTAGS,
    apply_hashtags_to_caption,
    collect_hashtag_pool,
    hashtags_for_platform,
    strip_trailing_hashtag_paragraph,
)

SOURCE = "slideshow-pack-1.0"
SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1920
MIN_SLIDES = 5
MAX_SLIDES = 7
DEFAULT_SLIDES = 5
DEFAULT_TOPIC = "cinematic AI"

# Spine is hook → tension → mechanism → rule → close. Extra beats fill 6–7.
ROLES_BY_COUNT: Dict[int, Tuple[str, ...]] = {
    5: ("hook", "tension", "mechanism", "rule", "close"),
    6: ("hook", "tension", "mechanism", "rule", "proof", "close"),
    7: ("hook", "tension", "recognition", "mechanism", "rule", "proof", "close"),
}

FONT_CANDIDATES_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans-Bold.ttf",
)
FONT_CANDIDATES_REGULAR = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/opt/homebrew/share/fonts/DejaVuSans.ttf",
)

RewriteFn = Callable[[Sequence[Mapping[str, Any]], str, str], Optional[Mapping[str, Any]]]


def default_output_dir() -> str:
    state = os.environ.get("STATE_DIR") or os.environ.get("DATA_DIR")
    base = state or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, "generated")
    os.makedirs(path, exist_ok=True)
    return path


def _as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


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
    brief = str(merged.get("brief") or merged.get("title") or "").strip()
    return {
        "brief": brief,
        "slide_count": merged.get("slide_count"),
    }


def clamp_slide_count(value: Any) -> Tuple[int, Optional[str]]:
    number = _as_int(value)
    if number is None:
        return DEFAULT_SLIDES, None
    if number < MIN_SLIDES:
        return MIN_SLIDES, f"slide_count {number} clamped up to {MIN_SLIDES}."
    if number > MAX_SLIDES:
        return MAX_SLIDES, f"slide_count {number} clamped down to {MAX_SLIDES}."
    return number, None


def topic_phrase(brief: str, limit: int = 42) -> str:
    text = re.sub(r"\s+", " ", (brief or "").strip())
    if not text:
        return DEFAULT_TOPIC
    clause = re.split(r"[.!?]", text, 1)[0].strip()
    if len(clause) <= limit:
        return clause
    words = clause.split()
    kept: List[str] = []
    for word in words:
        trial = " ".join(kept + [word])
        if len(trial) > limit:
            break
        kept.append(word)
    return " ".join(kept) or clause[:limit].rstrip()


def _template_overlay(role: str, topic: str, has_brief: bool) -> str:
    if role == "hook":
        if has_brief:
            return f"{topic}.\nLooks finished until it moves."
        return "Most AI cuts look finished.\nUntil the camera has to mean something."
    if role == "tension":
        return f"Most AI cuts flatten {topic}\ninto noise and leftover glow."
    if role == "recognition":
        return "You feel the cheapness\nin the first three seconds."
    if role == "mechanism":
        return "Treat every frame as a camera.\nNot a prompt. Not a preset."
    if role == "rule":
        return "If the light has no source,\nthe shot has no spine."
    if role == "proof":
        return "One locked exposure.\nOne motivated light. One cut."
    if role == "close":
        return "6Frame Studio.\nCinematic AI, finished on purpose."
    return f"{topic}.\nFinished in 6Frame voice."


def template_beats(brief: str, slide_count: int) -> List[Dict[str, Any]]:
    roles = ROLES_BY_COUNT[slide_count]
    topic = topic_phrase(brief)
    has_brief = bool((brief or "").strip())
    beats: List[Dict[str, Any]] = []
    for index, role in enumerate(roles, start=1):
        overlay = _template_overlay(role, topic, has_brief)
        first = overlay.split("\n", 1)[0].strip()
        beats.append({
            "index": index,
            "role": role,
            "overlay": overlay,
            "alt": f"{role.replace('_', ' ').capitalize()} slide: {first}",
        })
    return beats


def template_caption_body(brief: str) -> str:
    topic = topic_phrase(brief, limit=56)
    if (brief or "").strip():
        return (
            f"A 6Frame Studio photo-mode deck on {topic} — "
            "hook, tension, and a rule you can shoot."
        )
    return (
        "A 6Frame Studio photo-mode deck: hook, tension, mechanism, "
        "and a rule you can actually shoot."
    )


def ensure_brand_caption(caption: str, brief: str = "") -> str:
    body, _existing = strip_trailing_hashtag_paragraph(caption or "")
    if not body:
        body = template_caption_body(brief)
    pool = collect_hashtag_pool(extra_texts=[brief, body], extra_tags=BRAND_HASHTAGS)
    tags = hashtags_for_platform(pool, "instagram")
    return apply_hashtags_to_caption(body, tags)


def _first_font(candidates: Sequence[str]) -> str:
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return ""


def _truetype(path: str, size: int) -> ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def load_slide_fonts(overlay_size: int = 62) -> Dict[str, ImageFont.ImageFont]:
    bold = _first_font(FONT_CANDIDATES_BOLD)
    regular = _first_font(FONT_CANDIDATES_REGULAR) or bold
    return {
        "role": _truetype(regular, 26),
        "overlay": _truetype(bold, overlay_size),
        "mark": _truetype(regular, 22),
        "index": _truetype(regular, 22),
    }


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return max(0, bbox[2] - bbox[0]), max(0, bbox[3] - bbox[1])


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    lines: List[str] = []
    for paragraph in (text or "").split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            trial = f"{current} {word}"
            width, _ = _text_size(draw, trial, font)
            if width <= max_width:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines or [""]


def _cinematic_canvas(width: int, height: int) -> Image.Image:
    top = Image.new("RGB", (width, height), (10, 10, 12))
    bottom = Image.new("RGB", (width, height), (22, 14, 36))
    try:
        mask = Image.linear_gradient("L").resize((width, height))
        canvas = Image.composite(bottom, top, mask)
    except Exception:
        canvas = top
    bars = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bars)
    draw.rectangle([0, 0, width, 240], fill=(0, 0, 0, 96))
    draw.rectangle([0, height - 280, width, height], fill=(0, 0, 0, 120))
    return Image.alpha_composite(canvas.convert("RGBA"), bars).convert("RGB")


def compose_slide(
    overlay: str,
    role: str,
    index: int,
    total: int,
    output_path: str,
) -> str:
    """Render one branded 9:16 PNG. Original 6Frame compositor — not Muse/TikTok."""
    image = _cinematic_canvas(SLIDE_WIDTH, SLIDE_HEIGHT)
    draw = ImageDraw.Draw(image)
    fonts = load_slide_fonts()
    margin = 96
    max_width = SLIDE_WIDTH - (margin * 2)

    # Inner frame
    draw.rectangle(
        [42, 42, SLIDE_WIDTH - 43, SLIDE_HEIGHT - 43],
        outline=(58, 52, 78),
        width=2,
    )

    role_label = (role or "slide").replace("_", " ").upper()
    role_w, role_h = _text_size(draw, role_label, fonts["role"])
    role_x = (SLIDE_WIDTH - role_w) // 2
    role_y = 168
    draw.text((role_x, role_y), role_label, font=fonts["role"], fill=(167, 139, 250))
    accent_y = role_y + role_h + 18
    draw.rectangle(
        [(SLIDE_WIDTH // 2) - 36, accent_y, (SLIDE_WIDTH // 2) + 36, accent_y + 3],
        fill=(251, 191, 36),
    )

    overlay_size = 62
    lines = wrap_text(draw, overlay, fonts["overlay"], max_width)
    line_gap = 18
    block_h = 0
    for line in lines:
        _, h = _text_size(draw, line or " ", fonts["overlay"])
        block_h += h + line_gap
    while (block_h > 720 or any(_text_size(draw, line, fonts["overlay"])[0] > max_width for line in lines)) and overlay_size > 36:
        overlay_size -= 4
        fonts["overlay"] = load_slide_fonts(overlay_size)["overlay"]
        lines = wrap_text(draw, overlay, fonts["overlay"], max_width)
        block_h = 0
        for line in lines:
            _, h = _text_size(draw, line or " ", fonts["overlay"])
            block_h += h + line_gap
    block_h = max(0, block_h - line_gap)
    text_y = (SLIDE_HEIGHT - block_h) // 2 + 20
    for line in lines:
        w, h = _text_size(draw, line or " ", fonts["overlay"])
        draw.text(((SLIDE_WIDTH - w) // 2, text_y), line, font=fonts["overlay"], fill=(243, 244, 246))
        text_y += h + line_gap

    mark = "6FRAME STUDIO"
    mark_w, mark_h = _text_size(draw, mark, fonts["mark"])
    draw.text(
        ((SLIDE_WIDTH - mark_w) // 2, SLIDE_HEIGHT - 168 - mark_h),
        mark,
        font=fonts["mark"],
        fill=(156, 163, 175),
    )
    counter = f"{index:02d}  ·  {total:02d}"
    count_w, _ = _text_size(draw, counter, fonts["index"])
    draw.text(
        ((SLIDE_WIDTH - count_w) // 2, SLIDE_HEIGHT - 128),
        counter,
        font=fonts["index"],
        fill=(107, 114, 128),
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    image.save(output_path, format="PNG")
    return output_path


def apply_rewrite(
    beats: Sequence[Mapping[str, Any]],
    caption: str,
    brief: str,
    rewrite_fn: Optional[RewriteFn],
) -> Tuple[List[Dict[str, Any]], str, List[str], bool]:
    warnings: List[str] = []
    working = [dict(beat) for beat in beats]
    if not rewrite_fn:
        return working, caption, warnings, False
    try:
        result = rewrite_fn(working, caption, brief)
    except Exception as exc:
        warnings.append(f"Gemini rewrite skipped ({exc}). Using templated beats.")
        return working, caption, warnings, False
    if not result or not isinstance(result, Mapping):
        return working, caption, warnings, False

    rewritten_rows = result.get("beats")
    if isinstance(rewritten_rows, list):
        by_index = {}
        for row in rewritten_rows:
            if not isinstance(row, Mapping):
                continue
            idx = _as_int(row.get("index"))
            overlay = str(row.get("overlay") or "").strip()
            if idx and overlay:
                by_index[idx] = overlay
        if by_index:
            for beat in working:
                idx = _as_int(beat.get("index"))
                if idx in by_index:
                    beat["overlay"] = by_index[idx]
                    first = str(beat["overlay"]).split("\n", 1)[0].strip()
                    role = str(beat.get("role") or "slide")
                    beat["alt"] = f"{role.replace('_', ' ').capitalize()} slide: {first}"
    new_caption = str(result.get("caption") or caption)
    return working, ensure_brand_caption(new_caption, brief), warnings, True


def _summary_line(count: int, rewritten: bool, warnings: Sequence[str]) -> str:
    voice = "Gemini 6Frame rewrite" if rewritten else "templated 6Frame beats"
    note = " Warnings present." if warnings else ""
    return (
        f"{count}-slide advisory carousel ({voice}). "
        f"Does not publish. Autopilot still uses PostProxy.{note}"
    )


def build_slideshow_pack(
    payload: Optional[Mapping[str, Any]] = None,
    *,
    rewrite_fn: Optional[RewriteFn] = None,
    output_dir: Optional[str] = None,
    pack_id: Optional[str] = None,
) -> Dict[str, Any]:
    parsed = parse_request_payload({}, payload or {})
    brief = parsed["brief"]
    slide_count, clamp_warning = clamp_slide_count(parsed.get("slide_count"))
    warnings: List[str] = []
    if clamp_warning:
        warnings.append(clamp_warning)
    if not brief:
        warnings.append("Missing brief — used a templated cinematic-AI deck.")

    beats = template_beats(brief, slide_count)
    caption = ensure_brand_caption(template_caption_body(brief), brief)
    beats, caption, rewrite_warnings, rewritten = apply_rewrite(
        beats, caption, brief, rewrite_fn
    )
    warnings.extend(rewrite_warnings)

    dest = output_dir or default_output_dir()
    os.makedirs(dest, exist_ok=True)
    token = pack_id or uuid.uuid4().hex[:12]
    rendered: List[Dict[str, Any]] = []
    for beat in beats:
        index = int(beat["index"])
        filename = f"slideshow-{token}-{index:02d}.png"
        local_path = os.path.join(dest, filename)
        compose_slide(
            overlay=str(beat.get("overlay") or ""),
            role=str(beat.get("role") or "slide"),
            index=index,
            total=slide_count,
            output_path=local_path,
        )
        rendered.append({
            "index": index,
            "role": beat.get("role"),
            "overlay": beat.get("overlay"),
            "alt": beat.get("alt"),
            "image_path": f"/static/assets/generated/{filename}",
        })

    return {
        "ok": True,
        "source": SOURCE,
        "advisory": True,
        "publishes": False,
        "format": {
            "width": SLIDE_WIDTH,
            "height": SLIDE_HEIGHT,
            "tiktok_photo_mode": True,
            "instagram_carousel": True,
        },
        "slide_count": slide_count,
        "brief": brief,
        "caption": caption,
        "beats": rendered,
        "warnings": warnings,
        "rewritten": rewritten,
        "summary": _summary_line(slide_count, rewritten, warnings),
    }
