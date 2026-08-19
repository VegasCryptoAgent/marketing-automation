import os

os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")

import main


def test_twitter_caption_is_truncated_to_280():
    long_text = "Vegas crypto after dark. " * 20
    assert len(long_text) > 280
    trimmed = main.truncate_twitter_text(long_text)
    assert len(trimmed) <= 280
    assert trimmed.endswith("…")


def test_twitter_caption_is_split_into_thread_parts():
    text = ("Hook one. " * 20) + "\n\n" + ("Second beat. " * 20)
    parts = main.split_twitter_caption(text)
    assert len(parts) >= 2
    assert all(len(part) <= 280 for part in parts)
    assert parts[0]


def test_existing_thread_parts_are_truncated():
    parts = main.split_twitter_caption("ignored", existing_thread=["ok", "x" * 400])
    assert parts[0] == "ok"
    assert len(parts[1]) <= 280


def test_placement_picker_skips_null_ids():
    assert main.pick_placement_id([{"id": None, "name": "Personal"}, {"id": "12345", "name": "Page"}]) == "12345"
    assert main.pick_placement_id([{"id": "", "name": "Empty"}]) is None


def test_facebook_params_require_cached_page_id(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "POSTPROXY_STATE_FILE", str(tmp_path / "postproxy_state.json"))
    main.save_postproxy_state({
        "profiles": [{"id": "prof_fb", "platform": "facebook", "status": "active", "name": "Page"}],
        "placements": {"facebook": {"placement_id": "998877", "param": "page_id"}},
    })
    params = main.resolve_postproxy_platform_params({}, ["facebook", "twitter"])
    assert params["facebook"]["page_id"] == "998877"
    assert "twitter" not in params


def test_capabilities_requires_auth():
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    assert client.get("/api/capabilities").status_code == 401
    assert client.get("/api/credentials").status_code == 401
    assert client.post("/api/postproxy/sync").status_code == 401
    assert client.get("/api/postproxy/status").status_code == 401


def test_postproxy_callback_is_public():
    from fastapi.testclient import TestClient
    client = TestClient(main.app, follow_redirects=False)
    res = client.get("/api/postproxy/callback")
    assert res.status_code in (302, 307)
    assert "postproxy=ok" in res.headers.get("location", "")
    fail = client.get("/api/postproxy/callback?error=access_denied")
    assert "postproxy=failure" in fail.headers.get("location", "")
    alias = client.get("/oauth/postproxy/callback")
    assert alias.status_code in (302, 307)
    assert "postproxy=ok" in alias.headers.get("location", "")


def test_postproxy_status_has_no_secrets(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "POSTPROXY_STATE_FILE", str(tmp_path / "postproxy_state.json"))
    main.save_postproxy_state({
        "key_valid": True,
        "profile_group_id": "grp_demo",
        "profiles": [{"id": "prof_x", "name": "@studio", "platform": "twitter", "status": "active"}],
        "placements": {"twitter": {"placement_id": None, "placements": []}},
        "synced_at": "2026-08-19T00:00:00",
    })
    client = TestClient(main.app)
    token = __import__("base64").b64encode(b"admin:test-password").decode()
    res = client.get("/api/postproxy/status", headers={"Authorization": f"Basic {token}"})
    assert res.status_code == 200
    payload = res.json()
    blob = str(payload).lower()
    assert "bearer " not in blob
    assert "postproxy_api_key" not in payload
    assert payload["configured"] in (True, False)
    assert "channels" in payload
    assert payload["channels"]["twitter"]["live"] is True


def test_inactive_postproxy_profile_is_not_live():
    channels = main.build_social_channel_status({}, {
        "profiles": [{"id": "p1", "platform": "linkedin", "status": "inactive", "name": "Old"}],
        "placements": {},
    })
    linkedin = next(item for item in channels if item["platform"] == "linkedin")
    assert linkedin["live"] is False
    assert linkedin["status"] == "INACTIVE"


def _aspect_post():
    return {
        "text": "Landscape hook for LinkedIn and X.",
        "thread": ["X hook"],
        "instagram_caption": "Vertical hook for Reels.",
        "campaign_title": "Autonomous: Kling 3.0 cinematic",
        "video_path": "/static/assets/generated/clip.mp4",
        "vertical_video_path": "/static/assets/generated/clip_vertical_9x16.mp4",
    }


def test_vertical_platforms_get_9x16_url(monkeypatch):
    monkeypatch.setattr(main, "ensure_vertical_video_variant", lambda post, **kwargs: post.get("vertical_video_path"))
    settings = {"public_base_url": "https://app.example.com"}
    post = _aspect_post()
    for platform in ("instagram", "tiktok", "youtube", "facebook", "threads"):
        url = main.postproxy_media_url(post, settings, [platform])
        assert url == "https://app.example.com/static/assets/generated/clip_vertical_9x16.mp4", platform


def test_linkedin_and_twitter_get_landscape_url(monkeypatch):
    monkeypatch.setattr(main, "ensure_vertical_video_variant", lambda post, **kwargs: post.get("vertical_video_path"))
    settings = {"public_base_url": "https://app.example.com"}
    post = _aspect_post()
    assert main.postproxy_media_url(post, settings, ["linkedin"]).endswith("/clip.mp4")
    assert main.postproxy_media_url(post, settings, ["twitter"]).endswith("/clip.mp4")
    assert main.postproxy_media_url(post, settings, ["x"]).endswith("/clip.mp4")


def test_youtube_shorts_title_contains_shorts_under_100():
    title = main.youtube_shorts_title({
        "campaign_title": "Autonomous: Kling 3.0 Full Tutorial | How to Make Cinematic AI Short Films"
    })
    assert title.endswith("#Shorts")
    assert "#Shorts" in title
    assert len(title) <= 100
    again = main.youtube_shorts_title({"campaign_title": title})
    assert again.count("#Shorts") == 1


def test_mixed_publish_splits_vertical_and_landscape_media(monkeypatch):
    captured = []

    def fake_post(settings, path, payload, timeout=180):
        captured.append(payload)
        return {
            "id": f"pp_{len(captured)}",
            "platforms": [{"platform": p, "status": "published"} for p in payload["profiles"]],
        }

    monkeypatch.setattr(main, "postproxy_post", fake_post)
    monkeypatch.setattr(main, "ensure_vertical_video_variant", lambda post, **kwargs: post.get("vertical_video_path"))
    monkeypatch.setattr(main, "resolve_postproxy_platform_params", lambda *args, **kwargs: {"facebook": {"page_id": "123"}})
    monkeypatch.setattr(main, "load_postproxy_state", lambda: {})

    result = main.publish_via_postproxy(
        _aspect_post(),
        {"postproxy_enabled": True, "postproxy_api_key": "test", "public_base_url": "https://app.example.com"},
        ["linkedin", "twitter", "youtube", "facebook"],
    )
    assert result["errors"] == []

    by_platform = {}
    for payload in captured:
        for platform in payload["profiles"]:
            by_platform[platform] = payload

    landscape = "https://app.example.com/static/assets/generated/clip.mp4"
    vertical = "https://app.example.com/static/assets/generated/clip_vertical_9x16.mp4"
    assert by_platform["linkedin"]["media"] == [landscape]
    assert by_platform["twitter"]["media"] == [landscape]
    assert by_platform["youtube"]["media"] == [vertical]
    assert by_platform["facebook"]["media"] == [vertical]
    assert by_platform["linkedin"] is not by_platform["youtube"]
    assert by_platform["linkedin"] is not by_platform["facebook"]
    yt_title = by_platform["youtube"]["platforms"]["youtube"]["title"]
    assert "#Shorts" in yt_title
    assert len(yt_title) <= 100

    mixed_batches = [
        payload for payload in captured
        if set(payload["profiles"]) & {"linkedin", "twitter"}
        and set(payload["profiles"]) & {"youtube", "facebook", "instagram", "tiktok"}
    ]
    assert mixed_batches == []
