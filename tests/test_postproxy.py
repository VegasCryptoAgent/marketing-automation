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


def test_postproxy_callback_is_public():
    from fastapi.testclient import TestClient
    client = TestClient(main.app, follow_redirects=False)
    res = client.get("/api/postproxy/callback")
    assert res.status_code in (302, 307)
    assert "postproxy=connected" in res.headers.get("location", "")
