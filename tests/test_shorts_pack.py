import importlib
import os

os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")

import shorts_pack
from fastapi.testclient import TestClient

main = importlib.import_module("main")
client = TestClient(main.app)


CINEMATIC_TITLE = "Night Drive Cinematic Trailer"
CINEMATIC_DESCRIPTION = "A cinematic night drive built as a vertical Shorts cut."


def _by_platform(payload):
    return {row["platform"]: row for row in payload["platforms"]}


def test_vertical_12s_youtube_go_with_shorts():
    pack = shorts_pack.build_shorts_pack({
        "title": CINEMATIC_TITLE,
        "description": CINEMATIC_DESCRIPTION,
        "duration_seconds": 12,
        "width": 1080,
        "height": 1920,
        "hashtags": ["#CinematicTrailer", "#AIvideo"],
        "platforms": ["youtube", "twitter"],
    })
    assert pack["ok"] is True
    assert pack["source"] == "shorts-pack-1.0"
    assert pack["vertical"] is True
    assert pack["duration_seconds"] == 12
    youtube = _by_platform(pack)["youtube"]
    assert youtube["status"] == "GO"
    assert youtube["aspect"] == "9:16"
    assert "#Shorts" in youtube["title"]
    assert youtube["title"].endswith("#Shorts")
    assert len(youtube["title"]) <= 100
    assert "#6FrameStudio" in youtube["hashtags"]
    assert 8 <= len(youtube["hashtags"]) <= 12

    twitter = _by_platform(pack)["twitter"]
    # Landscape-preferred: vertical clip is WARN, not a hard NO-GO.
    assert twitter["status"] in {"GO", "WARN"}
    assert "#6FrameStudio" in twitter["hashtags"]


def test_twitter_not_nogo_when_aspect_missing():
    pack = shorts_pack.build_shorts_pack({
        "title": CINEMATIC_TITLE,
        "description": CINEMATIC_DESCRIPTION,
        "duration_seconds": 12,
        "platforms": ["twitter"],
    })
    twitter = _by_platform(pack)["twitter"]
    assert twitter["aspect"] == "unknown"
    assert twitter["status"] in {"GO", "WARN"}
    assert twitter["status"] != "NO-GO"


def test_instagram_nogo_on_200s_reel():
    pack = shorts_pack.build_shorts_pack({
        "title": CINEMATIC_TITLE,
        "description": CINEMATIC_DESCRIPTION,
        "duration_seconds": 200,
        "width": 1080,
        "height": 1920,
        "platforms": ["instagram"],
    })
    instagram = _by_platform(pack)["instagram"]
    assert instagram["status"] == "NO-GO"
    assert any(
        item["severity"] == "ERROR" and "200" in item["message"]
        for item in instagram["issues"]
    )


def test_surveillance_phrase_is_copy_gate_warning():
    pack = shorts_pack.build_shorts_pack({
        "title": CINEMATIC_TITLE,
        "description": "An AI that watches your business while you sleep.",
        "duration_seconds": 12,
        "width": 1080,
        "height": 1920,
        "platforms": ["youtube"],
    })
    youtube = _by_platform(pack)["youtube"]
    assert youtube["status"] == "WARN"
    assert any(
        item["severity"] == "WARNING" and "Surveillance" in item["message"]
        for item in youtube["issues"]
    )


def test_pill_caption_is_copy_gate_warning():
    issues = shorts_pack.copy_gate_issues("Night Drive", "Cinematic Trailer")
    assert any("pill" in item["message"].lower() or "fragment" in item["message"].lower() for item in issues)


def test_api_shorts_pack_public_post_and_get():
    body = {
        "title": CINEMATIC_TITLE,
        "description": CINEMATIC_DESCRIPTION,
        "duration_seconds": 12,
        "width": 1080,
        "height": 1920,
        "hashtags": "#CinematicTrailer,#AIvideo",
    }
    posted = client.post("/api/shorts-pack", json=body)
    assert posted.status_code == 200
    payload = posted.json()
    assert payload["ok"] is True
    assert payload["source"] == "shorts-pack-1.0"
    assert "platforms" in payload
    youtube = _by_platform(payload)["youtube"]
    assert youtube["status"] == "GO"
    assert "#Shorts" in youtube["title"]
    assert "#6FrameStudio" in youtube["hashtags"]

    queried = client.get(
        "/api/shorts-pack",
        params={
            "title": CINEMATIC_TITLE,
            "description": CINEMATIC_DESCRIPTION,
            "duration_seconds": 12,
            "width": 1080,
            "height": 1920,
        },
    )
    assert queried.status_code == 200
    assert queried.json()["ok"] is True
    assert queried.json()["vertical"] is True


def test_json_only_is_enough_without_ffmpeg():
    pack = shorts_pack.build_shorts_pack({
        "title": "Seedance night cut",
        "description": "This is a finished sentence for the caption.",
        "duration_seconds": 8,
        "width": 1080,
        "height": 1920,
    })
    assert pack["ok"] is True
    assert pack["duration_seconds"] == 8
    assert all(row["hashtags"] for row in pack["platforms"])
