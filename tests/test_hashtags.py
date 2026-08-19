import os

os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")

import hashtags
import main


LIVE_CAPTION = (
    "Generating multi-shot cinematic films in AI without losing character consistency or camera control.\n"
    "\n"
    "Here is a shot-for-shot breakdown of our latest dark cinematic sequence built with multi-shot continuous generation."
)


def test_brand_tags_always_come_first():
    pool = hashtags.collect_hashtag_pool({
        "text": LIVE_CAPTION,
        "campaign_title": "Autonomous: Kling 3.0 cinematic",
        "suggested_hashtags": ["#AIvideo", "#6framestudio"],
    })
    assert pool[:3] == ["#6FrameStudio", "#AIFilmmaking", "#AICinema"]
    assert "#KlingAI" in pool
    assert pool.count("#6FrameStudio") == 1


def test_apply_merges_existing_trailing_tags_without_duplicating():
    caption = LIVE_CAPTION + "\n\n#AIvideo #KlingAI #6FrameStudio"
    tags = hashtags.hashtags_for_platform(
        hashtags.collect_hashtag_pool({
            "text": caption,
            "campaign_title": "Kling breakdown",
            "suggested_hashtags": ["#RunwayML"],
        }),
        "linkedin",
    )
    applied = hashtags.apply_hashtags_to_caption(caption, tags)
    body, trailing = hashtags.strip_trailing_hashtag_paragraph(applied)
    assert body == LIVE_CAPTION
    assert trailing[:3] == ["#6FrameStudio", "#AIFilmmaking", "#AICinema"]
    assert trailing.count("#KlingAI") == 1
    assert 5 <= len(trailing) <= 8
    assert applied == LIVE_CAPTION + "\n\n" + " ".join(trailing)


def test_inline_hook_hashtag_is_not_moved():
    caption = "Shot on #KlingAI with real camera control.\n\nBreakdown of the sequence."
    tags = ["#6FrameStudio", "#AIFilmmaking", "#AICinema", "#KlingAI"]
    applied = hashtags.apply_hashtags_to_caption(caption, tags)
    assert applied.startswith("Shot on #KlingAI with real camera control.")
    assert applied.endswith("#6FrameStudio #AIFilmmaking #AICinema #KlingAI")


def test_platform_limits_and_instagram_body():
    post = {
        "text": LIVE_CAPTION,
        "instagram_caption": "Dark cinematic sequence. Recreated at 6Frame.",
        "campaign_title": "Autonomous: Sora + Runway trailer",
        "suggested_hashtags": ["#Sora", "#RunwayML", "#CinematicTrailer", "#AIvideo"],
    }
    linkedin = hashtags.apply_platform_hashtags(post, "linkedin")
    facebook = hashtags.apply_platform_hashtags(post, "facebook")
    instagram = hashtags.apply_platform_hashtags(post, "instagram")
    tiktok = hashtags.apply_platform_hashtags(post, "tiktok")
    youtube = hashtags.apply_platform_hashtags(post, "youtube")

    _, li_tags = hashtags.strip_trailing_hashtag_paragraph(linkedin)
    _, ig_tags = hashtags.strip_trailing_hashtag_paragraph(instagram)
    _, yt_tags = hashtags.strip_trailing_hashtag_paragraph(youtube)
    assert 5 <= len(li_tags) <= 8
    assert 8 <= len(ig_tags) <= 12
    assert 8 <= len(yt_tags) <= 12
    assert "#Shorts" in yt_tags
    assert linkedin.startswith(LIVE_CAPTION)
    assert facebook.startswith(LIVE_CAPTION)
    assert youtube.startswith(LIVE_CAPTION)
    assert instagram.startswith("Dark cinematic sequence. Recreated at 6Frame.")
    assert tiktok.startswith("Dark cinematic sequence. Recreated at 6Frame.")
    assert "#Sora" in ig_tags
    assert "#RunwayML" in ig_tags


def test_twitter_gets_one_or_two_tags_on_last_tweet_under_280():
    long_last = "x" * 270
    thread = hashtags.apply_hashtags_to_twitter_thread(
        ["Hook about Kling", long_last],
        ["#6FrameStudio", "#AIFilmmaking", "#AICinema", "#KlingAI"],
    )
    assert thread[0] == "Hook about Kling"
    assert "#" not in thread[0]
    last_tags = hashtags.extract_hashtags(thread[-1])
    assert 1 <= len(last_tags) <= 2
    assert last_tags[0] == "#6FrameStudio"
    assert len(thread[-1]) <= 280
    assert thread[-1].split("\n\n")[-1].startswith("#")


def test_apply_twice_is_idempotent():
    post = {
        "text": LIVE_CAPTION,
        "campaign_title": "Veo night drive",
        "suggested_hashtags": ["#Veo"],
    }
    once = hashtags.apply_platform_hashtags(post, "linkedin")
    twice = hashtags.apply_platform_hashtags({**post, "text": once}, "linkedin")
    assert once == twice


def test_publish_via_postproxy_splits_when_tag_counts_differ(monkeypatch):
    captured = []

    def fake_post(settings, path, payload, timeout=180):
        captured.append(payload)
        return {
            "id": f"pp_{len(captured)}",
            "platforms": [{"platform": p, "status": "published"} for p in payload["profiles"]],
        }

    monkeypatch.setattr(main, "postproxy_post", fake_post)
    monkeypatch.setattr(main, "postproxy_media_url", lambda *args, **kwargs: "https://example.com/clip.mp4")
    monkeypatch.setattr(main, "resolve_postproxy_platform_params", lambda *args, **kwargs: {"facebook": {"page_id": "123"}})
    monkeypatch.setattr(main, "load_postproxy_state", lambda: {})

    post = {
        "text": LIVE_CAPTION,
        "thread": ["Hook about Kling multi-shot", "More on camera control"],
        "instagram_caption": "Dark cinematic sequence built with Kling.",
        "suggested_hashtags": ["#KlingAI", "#CinematicTrailer"],
        "campaign_title": "Autonomous: Kling dark cinematic",
        "video_path": "/static/assets/generated/clip.mp4",
    }
    result = main.publish_via_postproxy(
        post,
        {"postproxy_enabled": True, "postproxy_api_key": "test"},
        ["linkedin", "twitter", "instagram", "tiktok", "youtube", "facebook"],
    )
    assert result["errors"] == []
    assert set(result["successes"]) >= {"linkedin", "twitter", "instagram", "tiktok", "youtube", "facebook"}

    by_platform = {}
    for payload in captured:
        for platform in payload["profiles"]:
            by_platform[platform] = payload

    li_body = by_platform["linkedin"]["post"]["body"]
    fb_body = by_platform["facebook"]["post"]["body"]
    ig_body = by_platform["instagram"]["post"]["body"]
    tt_body = by_platform["tiktok"]["post"]["body"]
    yt_body = by_platform["youtube"]["post"]["body"]
    tw_payload = by_platform["twitter"]

    assert li_body == fb_body
    assert ig_body == tt_body
    assert ig_body != li_body
    assert li_body.startswith(LIVE_CAPTION)
    assert ig_body.startswith("Dark cinematic sequence built with Kling.")
    assert yt_body.startswith(LIVE_CAPTION)

    _, li_tags = hashtags.strip_trailing_hashtag_paragraph(li_body)
    _, ig_tags = hashtags.strip_trailing_hashtag_paragraph(ig_body)
    _, yt_tags = hashtags.strip_trailing_hashtag_paragraph(yt_body)
    assert 5 <= len(li_tags) <= 8
    assert 8 <= len(ig_tags) <= 12
    assert 8 <= len(yt_tags) <= 12
    assert "#Shorts" in yt_tags
    assert li_tags[:3] == ["#6FrameStudio", "#AIFilmmaking", "#AICinema"]
    yt_title = (by_platform["youtube"].get("platforms") or {}).get("youtube", {}).get("title", "")
    assert "#Shorts" in yt_title
    assert len(yt_title) <= 100

    thread_bodies = [tw_payload["post"]["body"]] + [item["body"] for item in tw_payload.get("thread") or []]
    assert all(len(part) <= 280 for part in thread_bodies)
    last = thread_bodies[-1]
    last_tags = hashtags.extract_hashtags(last)
    assert 1 <= len(last_tags) <= 2
    assert last_tags[0] == "#6FrameStudio"
    assert "#" not in thread_bodies[0] or hashtags.extract_hashtags(thread_bodies[0]) == []
