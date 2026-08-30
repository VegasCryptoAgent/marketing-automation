import base64
import importlib
import os
from datetime import datetime, timedelta, timezone

import pytest
import requests

os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")

import radar

main = importlib.import_module("main")
from fastapi.testclient import TestClient

client = TestClient(main.app)
NOW = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)


def basic_headers(username="admin", password="test-password"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _obs(title, url, source, engagement, hours_ago, metrics=None):
    published = NOW - timedelta(hours=hours_ago)
    return {
        "title": title,
        "url": url,
        "source": source,
        "engagement": engagement,
        "observed_at": NOW,
        "published_at": published,
        "metrics": metrics or {},
    }


def test_failed_adapter_yields_empty_list():
    def boom():
        raise TimeoutError("source timed out")

    assert radar.collect_or_empty("hacker_news", boom) == []


def test_empty_adapter_yields_empty_list():
    assert radar.collect_or_empty("bluesky", lambda: []) == []
    assert radar.collect_or_empty("google_news", lambda: None) == []


def test_network_timeout_adapter_yields_empty():
    def bad_get(*args, **kwargs):
        raise requests.Timeout("no network in unit tests")

    assert radar.collect_or_empty(
        "hacker_news",
        lambda: radar.collect_hacker_news(http_get=bad_get, now=NOW),
    ) == []
    assert radar.collect_or_empty(
        "google_news",
        lambda: radar.collect_google_news(http_get=bad_get, now=NOW),
    ) == []
    assert radar.collect_or_empty(
        "bluesky",
        lambda: radar.collect_bluesky(http_get=bad_get, now=NOW),
    ) == []


def test_run_radar_all_failed_adapters_returns_schema(tmp_path):
    def boom():
        raise RuntimeError("adapter down")

    payload = radar.run_radar(
        collectors=[("hacker_news", boom), ("google_news", lambda: [])],
        now=NOW,
        snapshot_file=str(tmp_path / "radar_snapshots.json"),
        persist=False,
        use_cache=False,
        refresh=True,
    )
    assert payload["items"] == []
    assert isinstance(payload["summary"], str)
    assert payload["summary"]


def test_score_drops_walled_rows_without_real_url():
    items = radar.score_observations(
        [
            _obs("fake tiktok", "", "tiktok", 9999, 1),
            _obs("bare x", "https://x.com/", "twitter", 9999, 1),
            _obs("bare ig", "https://www.instagram.com/", "instagram", 9999, 1),
        ],
        now=NOW,
    )
    assert items == []


def test_score_first_snapshot_new_and_emerging():
    items = radar.score_observations(
        [
            _obs("Quiet AI trailer note", "https://news.ycombinator.com/item?id=1", "hacker_news", 4, 36),
            _obs("Kling cinematic short", "https://news.ycombinator.com/item?id=2", "hacker_news", 12, 18),
        ],
        previous_by_url={},
        source_history={},
        now=NOW,
    )
    by_url = {row["url"]: row for row in items}
    quiet = by_url["https://news.ycombinator.com/item?id=1"]
    kling = by_url["https://news.ycombinator.com/item?id=2"]
    assert quiet["lifecycle"] == "NEW"
    assert quiet["confidence"] == pytest.approx(0.30)
    assert quiet["metrics"]["first_seen"] is True
    assert kling["lifecycle"] == "EMERGING"
    assert kling["confidence"] == pytest.approx(0.30)
    assert 0 <= quiet["score"] <= 100


def test_score_velocity_snapshots_expected_lifecycle():
    rising_url = "https://news.ycombinator.com/item?id=rising"
    viral_url = "https://news.ycombinator.com/item?id=viral"
    previous = {
        rising_url: {
            "engagement": 85,
            "velocity": 0,
            "observed_at": (NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "source": "hacker_news",
        },
        viral_url: {
            "engagement": 40,
            "velocity": 0,
            "observed_at": (NOW - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            "source": "hacker_news",
        },
    }
    history = {
        "hacker_news": [80, 95, 100, 90, 110, 20, 25, 30, 28, 40],
    }
    items = radar.score_observations(
        [
            _obs("Veo 3 workflow thread", rising_url, "hacker_news", 100, 1),
            _obs("Seedance trailer explodes", viral_url, "hacker_news", 400, 1),
            _obs("Seedance trailer on news", "https://news.google.com/articles/seedance", "google_news", 30, 1),
        ],
        previous_by_url=previous,
        source_history=history,
        now=NOW,
    )
    by_url = {row["url"]: row for row in items}
    rising = by_url[rising_url]
    viral = by_url[viral_url]
    assert rising["lifecycle"] == "RISING"
    assert rising["confidence"] > 0.5
    assert rising["metrics"]["first_seen"] is False
    assert viral["lifecycle"] == "VIRAL"
    assert viral["score"] >= 82
    assert viral["metrics"]["cross_source"] is True
    assert by_url["https://news.google.com/articles/seedance"]["metrics"]["cross_source"] is True


def test_second_scan_uses_persisted_snapshot_for_velocity(tmp_path):
    snap = str(tmp_path / "radar_snapshots.json")
    url = "https://news.ycombinator.com/item?id=persist"

    def first_pass():
        return [
            _obs("Kling 3 night drive", url, "hacker_news", 50, 3),
        ]

    first = radar.run_radar(
        collectors=[("hacker_news", first_pass)],
        now=NOW - timedelta(hours=2),
        snapshot_file=snap,
        persist=True,
        use_cache=False,
        refresh=True,
    )
    assert first["items"][0]["metrics"]["first_seen"] is True
    assert first["items"][0]["confidence"] == pytest.approx(0.30)

    def second_pass():
        return [
            _obs("Kling 3 night drive", url, "hacker_news", 220, 1),
        ]

    second = radar.run_radar(
        collectors=[("hacker_news", second_pass)],
        now=NOW,
        snapshot_file=snap,
        persist=True,
        use_cache=False,
        refresh=True,
    )
    row = second["items"][0]
    assert row["metrics"]["first_seen"] is False
    assert row["metrics"]["velocity_per_hour"] > 0
    assert row["confidence"] > first["items"][0]["confidence"]
    assert row["lifecycle"] in {"EMERGING", "RISING", "HOT", "VIRAL"}


def test_evidence_pack_empty_when_no_items():
    assert radar.format_evidence_pack([]) == ""


def test_evidence_pack_cites_real_urls_only():
    pack = radar.format_evidence_pack([
        {
            "title": "Kling short",
            "url": "https://news.ycombinator.com/item?id=9",
            "source": "hacker_news",
            "score": 71.2,
            "confidence": 0.6,
            "lifecycle": "HOT",
        }
    ])
    assert "https://news.ycombinator.com/item?id=9" in pack
    assert "HARD RULE" in pack
    assert "tiktok.com/@invented" not in pack


def test_health_is_public_and_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_radar_schema_without_gemini(monkeypatch):
    monkeypatch.setattr(
        main,
        "run_radar",
        lambda refresh=False: {
            "items": [
                {
                    "title": "Veo clip",
                    "url": "https://example.com/veo",
                    "source": "hacker_news",
                    "score": 64.0,
                    "confidence": 0.3,
                    "lifecycle": "RISING",
                    "metrics": {"engagement": 12},
                    "observedAt": "2026-08-30T12:00:00Z",
                }
            ],
            "summary": "1 observed item",
        },
    )
    for method in ("GET", "POST"):
        response = client.request(method, "/api/radar")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body and "summary" in body
        assert body["items"][0]["url"] == "https://example.com/veo"
        assert body["items"][0]["lifecycle"] == "RISING"


def test_api_radar_empty_schema(monkeypatch):
    monkeypatch.setattr(main, "run_radar", lambda refresh=False: {"items": [], "summary": "empty"})
    response = client.get("/api/radar")
    assert response.status_code == 200
    assert response.json() == {"items": [], "summary": "empty"}
