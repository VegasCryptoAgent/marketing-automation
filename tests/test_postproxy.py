import importlib
import os

from fastapi.testclient import TestClient


os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["DISABLE_BACKGROUND_SCHEDULER"] = "true"

main = importlib.import_module("main")
client = TestClient(main.app)


def test_split_twitter_chunks_stays_within_280():
    short = "hello world"
    assert main.split_twitter_chunks(short) == [short]
    long = ("Cinematic AI video from 6Frame Studio. " * 20).strip()
    chunks = main.split_twitter_chunks(long)
    assert len(chunks) > 1
    assert all(len(chunk) <= 280 for chunk in chunks)
    assert "".join(chunks).replace(" ", "") in long.replace(" ", "")


def test_placement_target_id_reads_page_and_org_fields():
    assert main.placement_target_id({"id": "page-1", "name": "Page"}) == "page-1"
    assert main.placement_target_id({"id": None, "page_id": "999"}) == "999"
    assert main.placement_target_id({"id": None, "organization_id": "org-8"}) == "org-8"
    assert main.placement_target_id({"id": None, "metadata": {"page_id": "meta-page"}}) == "meta-page"
    assert main.placement_target_id({"id": None, "name": "Personal Profile"}) is None


def test_postproxy_status_has_no_secrets(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "SETTINGS_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(main, "POSTPROXY_CACHE_FILE", str(tmp_path / "postproxy_cache.json"))
    response = client.get("/api/postproxy/status", headers={"Authorization": "Basic YWRtaW46dGVzdC1wYXNzd29yZA=="})
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert "postproxy_api_key" not in payload
    blob = str(payload).lower()
    assert "bearer " not in blob
    assert "channels" in payload
    assert "twitter" in payload["channels"]


def test_build_live_integration_status_uses_postproxy_active_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "POSTPROXY_CACHE_FILE", str(tmp_path / "postproxy_cache.json"))
    cache = {
        "ok": True,
        "synced_at": "2026-08-19T00:00:00",
        "channels": {
            "twitter": {"live": True, "status": "active", "profile_id": "prof_x", "name": "@sixframe", "placements": []},
            "linkedin": {"live": False, "status": "disconnected", "profile_id": None, "name": None, "placements": []},
        },
    }
    main.save_postproxy_cache(cache)
    settings = main.DEFAULT_SETTINGS.copy()
    rows = {row["id"]: row for row in main.build_live_integration_status(settings, {"integrations": []})}
    assert rows["twitter"]["status"] == "credentials_present"
    assert rows["twitter"]["source"] == "postproxy"
    assert rows["linkedin"]["status"] == "needs_credentials"


def test_publish_via_postproxy_attaches_facebook_page_id_and_splits_twitter(monkeypatch):
    captured = []

    def fake_post(settings, path, payload, timeout=180):
        captured.append(payload)
        return {"id": f"post_{len(captured)}", "platforms": [{"platform": p, "status": "published"} for p in payload["profiles"]]}

    monkeypatch.setattr(main, "postproxy_post", fake_post)
    monkeypatch.setattr(main, "postproxy_media_url", lambda post, settings, platforms: None)
    monkeypatch.setattr(main, "resolve_facebook_page_id", lambda settings: "page-42")
    monkeypatch.setattr(main, "resolve_linkedin_organization_id", lambda settings: "org-7")

    long_text = ("Cinematic AI video from 6Frame Studio. " * 12).strip()
    assert len(long_text) > 280
    result = main.publish_via_postproxy(
        {"text": long_text, "campaign_title": "Test"},
        {"postproxy_enabled": True, "postproxy_api_key": "x"},
        ["facebook", "linkedin", "twitter"],
    )
    assert result["successes"]
    facebook_payload = next(item for item in captured if "facebook" in item["profiles"])
    twitter_payload = next(item for item in captured if "twitter" in item["profiles"])
    assert facebook_payload["platforms"]["facebook"]["page_id"] == "page-42"
    assert facebook_payload["platforms"]["linkedin"]["organization_id"] == "org-7"
    assert len(twitter_payload["post"]["body"]) <= 280
    if twitter_payload.get("thread"):
        assert all(len(item["body"]) <= 280 for item in twitter_payload["thread"])


def test_oauth_callback_redirects_to_dashboard():
    ok = client.get("/api/postproxy/callback", follow_redirects=False)
    assert ok.status_code in (302, 307)
    assert ok.headers["location"].endswith("/?postproxy=ok")
    fail = client.get("/api/postproxy/callback?error=access_denied", follow_redirects=False)
    assert fail.headers["location"].endswith("/?postproxy=failure")
