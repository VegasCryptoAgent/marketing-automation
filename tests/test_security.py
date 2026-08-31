import importlib
import os

from fastapi.testclient import TestClient


os.environ["ADMIN_PASSWORD"] = "test-password"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["DISABLE_BACKGROUND_SCHEDULER"] = "true"

main = importlib.import_module("main")
client = TestClient(main.app)


def test_dashboard_is_public_without_credentials():
    response = client.get("/")
    assert response.status_code == 200
    assert "www-authenticate" not in {k.lower() for k in response.headers}
    assert "6Frame Studio" in response.text
    assert "Autopilot" in response.text
    assert "Live Trend Scanner" in response.text or "Live Trends Scanner" in response.text
    assert "auth-overlay" not in response.text
    assert "Admin Access" not in response.text


def test_admin_password_env_does_not_gate_the_app():
    assert os.environ.get("ADMIN_PASSWORD") == "test-password"
    assert client.get("/").status_code == 200
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/auth/status").json() == {"auth_required": False, "authenticated": True}
    login = client.post("/api/auth/login", json={"password": "wrong"})
    assert login.status_code == 200
    assert login.json()["auth_required"] is False


def test_public_apis_stay_public():
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/radar").status_code == 200
    assert client.get("/api/shorts-pack", params={"title": "Night Drive"}).status_code == 200
    assert client.get("/api/slideshow-pack", params={"brief": "Night Drive"}).status_code == 200


def test_arbitrary_filesystem_paths_are_rejected():
    response = client.post(
        "/api/analyze",
        json={"video_path": "/etc/passwd", "website_url": "https://example.com"},
    )
    assert response.status_code == 400
    assert "uploaded or generated media" in response.json()["detail"]


def test_allowed_uploaded_video_path_is_accepted_by_resolver(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    video = upload_dir / "clip.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(main, "UPLOAD_DIR", str(upload_dir))
    assert main.resolve_local_video_path(str(video)) == str(video.resolve())
