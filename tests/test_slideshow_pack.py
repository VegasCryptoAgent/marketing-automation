import importlib
import os
from pathlib import Path

os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import slideshow_pack

main = importlib.import_module("main")
client = TestClient(main.app)
_REAL_LOAD_SETTINGS = main.load_settings

BRIEF = "Night drive cinematic trailer for AI filmmakers"


@pytest.fixture(autouse=True)
def no_gemini_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    def load_settings_without_gemini():
        settings = _REAL_LOAD_SETTINGS()
        settings["gemini_api_key"] = ""
        return settings

    monkeypatch.setattr(main, "load_settings", load_settings_without_gemini)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("slideshow pack tests must not call Gemini or the network")

    monkeypatch.setattr(main, "call_gemini_json", forbidden)


def _beat_file(output_dir, beat):
    return os.path.join(output_dir, os.path.basename(beat["image_path"]))


def test_seven_slides_are_1080x1920_and_do_not_publish(tmp_path):
    pack = slideshow_pack.build_slideshow_pack(
        {"brief": BRIEF, "slide_count": 7},
        output_dir=str(tmp_path),
        pack_id="test7",
    )
    assert pack["ok"] is True
    assert pack["source"] == "slideshow-pack-1.0"
    assert pack["advisory"] is True
    assert pack["publishes"] is False
    assert pack["format"]["width"] == 1080
    assert pack["format"]["height"] == 1920
    assert pack["format"]["tiktok_photo_mode"] is True
    assert pack["format"]["instagram_carousel"] is True
    assert pack["slide_count"] == 7
    assert len(pack["beats"]) == 7
    assert "#6FrameStudio" in pack["caption"]
    assert "#AIFilmmaking" in pack["caption"]
    assert "#AICinema" in pack["caption"]
    roles = [beat["role"] for beat in pack["beats"]]
    assert roles[0] == "hook"
    assert roles[-1] == "close"
    assert "tension" in roles
    assert "mechanism" in roles
    assert "rule" in roles
    for beat in pack["beats"]:
        path = _beat_file(tmp_path, beat)
        assert os.path.isfile(path)
        with Image.open(path) as image:
            assert image.size == (1080, 1920)
            assert image.format == "PNG"
        assert beat["overlay"]
        assert beat["alt"]
        assert beat["image_path"].startswith("/static/assets/generated/slideshow-")


def test_slide_count_3_clamps_up(tmp_path):
    pack = slideshow_pack.build_slideshow_pack(
        {"brief": BRIEF, "slide_count": 3},
        output_dir=str(tmp_path),
        pack_id="clamp3",
    )
    assert pack["slide_count"] == 5
    assert len(pack["beats"]) == 5
    assert any("clamped up" in warning for warning in pack["warnings"])


def test_missing_brief_still_builds_templated_deck(tmp_path):
    pack = slideshow_pack.build_slideshow_pack(
        {},
        output_dir=str(tmp_path),
        pack_id="empty",
    )
    assert pack["ok"] is True
    assert pack["publishes"] is False
    assert pack["slide_count"] == 5
    assert len(pack["beats"]) == 5
    assert any("Missing brief" in warning for warning in pack["warnings"])
    assert "#6FrameStudio" in pack["caption"]
    assert all(os.path.isfile(_beat_file(tmp_path, beat)) for beat in pack["beats"])


def test_injected_rewrite_updates_overlays_without_network(tmp_path):
    def rewrite(beats, caption, brief):
        return {
            "beats": [
                {"index": 1, "overlay": "Rewritten hook for the night drive."},
            ],
            "caption": "Rewritten caption in 6Frame voice.",
        }

    pack = slideshow_pack.build_slideshow_pack(
        {"brief": BRIEF, "slide_count": 5},
        rewrite_fn=rewrite,
        output_dir=str(tmp_path),
        pack_id="rewrite",
    )
    assert pack["rewritten"] is True
    assert pack["beats"][0]["overlay"] == "Rewritten hook for the night drive."
    assert "Rewritten caption" in pack["caption"]
    assert "#6FrameStudio" in pack["caption"]


def test_module_never_mentions_postproxy():
    source = Path(slideshow_pack.__file__).read_text()
    assert "postproxy" not in source.lower()


def test_api_get_and_post_public_and_advisory():
    body = {"brief": BRIEF, "slide_count": 7}
    posted = client.post("/api/slideshow-pack", json=body)
    assert posted.status_code == 200
    payload = posted.json()
    assert payload["ok"] is True
    assert payload["publishes"] is False
    assert payload["advisory"] is True
    assert payload["source"] == "slideshow-pack-1.0"
    assert "#6FrameStudio" in payload["caption"]
    assert len(payload["beats"]) == 7
    for beat in payload["beats"]:
        local = os.path.join(main.GENERATED_DIR, os.path.basename(beat["image_path"]))
        assert os.path.isfile(local)
        with Image.open(local) as image:
            assert image.size == (1080, 1920)
        image_res = client.get(beat["image_path"])
        assert image_res.status_code == 200
        assert image_res.headers.get("content-type", "").startswith("image/")

    queried = client.get("/api/slideshow-pack", params={"brief": BRIEF, "slide_count": 3})
    assert queried.status_code == 200
    clamped = queried.json()
    assert clamped["ok"] is True
    assert clamped["publishes"] is False
    assert clamped["slide_count"] == 5
    assert len(clamped["beats"]) == 5

    missing = client.get("/api/slideshow-pack")
    assert missing.status_code == 200
    empty = missing.json()
    assert empty["ok"] is True
    assert empty["warnings"]
    assert empty["publishes"] is False


def test_dashboard_includes_slideshow_pack_card():
    page = client.get("/")
    assert page.status_code == 200
    assert "slideshow-pack-strip" in page.text
    assert "Build slideshow" in page.text
    assert "This does not publish." in page.text
    assert "shorts-pack-strip" in page.text
    assert "cockpit-slideshow-recap" in page.text


def test_health_and_shorts_pack_still_work():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
    shorts = client.get("/api/shorts-pack", params={"title": "Night Drive"})
    assert shorts.status_code == 200
    shorts_payload = shorts.json()
    assert shorts_payload["ok"] is True
    assert shorts_payload["source"] == "shorts-pack-1.0"
    assert "platforms" in shorts_payload
