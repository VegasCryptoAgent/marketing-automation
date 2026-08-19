import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marketing_os import (
    empty_brand_context,
    generate_hook_matrix,
    generate_launch_packet,
    list_tactics,
    load_brand_context,
    normalize_brand_context,
    save_brand_context,
    score_hook,
    socialclaw_status,
    socialclaw_submit,
)


def sample_brand():
    return {
        "product": {
            "one_sentence": "Cinematic AI video lab that turns briefs into finished social cuts.",
            "mechanism": "Multimodal brief-to-cut pipeline with platform-native packing",
            "does_not": "We do not sell follower counts or fake testimonials.",
        },
        "audience": {
            "who_buys": "studio leads who still approve every frame",
            "belief_before": "another generator will look like everyone else's feed",
            "worry_2am": "launch morning with a generic cut",
            "alternative": "a freelance editor plus five AI tools",
        },
        "positioning": {
            "only_we_can_say": "We ship the cut, the copy, and the publish path in one desk.",
            "category": "AI video production",
            "competitors": "generic text-to-video apps",
        },
        "proof": {
            "numbers": "14 campaigns shipped in Q2 2026 (internal production log)",
            "customers": "6Frame Studio internal slate",
            "needs_legal": "",
        },
        "voice": {
            "how_we_sound": "specific, visual, no hype",
            "how_we_never_sound": "bro-marketing",
            "always_words": "cut, frame, brief",
            "never_words": "game-changer, revolutionize",
        },
        "constraints": {
            "regulatory": "",
            "off_limits": "invented customer quotes",
        },
    }


def test_eighteen_tactics_are_named():
    tactics = list_tactics()
    assert len(tactics) == 18
    names = [t["name"] for t in tactics]
    assert "Callout" in names
    assert "Identity" in names
    assert "Stat lead" in names


def test_empty_brand_is_not_contextualised():
    ctx = normalize_brand_context(empty_brand_context())
    assert ctx["contextualised"] is False
    assert ctx["filled_fields"] == 0


def test_hook_matrix_scores_all_eighteen_and_uses_brand_language():
    matrix = generate_hook_matrix(sample_brand(), segment="studio leads")
    assert matrix["tactic_count"] == 18
    assert matrix["contextualised"] is True
    assert len(matrix["hooks"]) == 18
    spoken = " ".join(h["spoken"] + " " + h["text"] + " " + h["visual"] for h in matrix["hooks"])
    assert "studio leads who still approve every frame" in spoken or "studio leads" in spoken
    for hook in matrix["hooks"]:
        assert isinstance(hook["score"]["total"], int)
        assert 0 <= hook["score"]["total"] <= 100
        assert hook["score"]["heuristic"] is True
        assert hook["visual"]
        assert hook["text"]
    assert matrix["recommended_first_tests"]
    assert any("[NEED:" not in h["spoken"] for h in matrix["hooks"])


def test_stat_lead_does_not_invent_a_number_when_proof_is_empty():
    brand = sample_brand()
    brand["proof"]["numbers"] = ""
    brand["proof"]["customers"] = ""
    matrix = generate_hook_matrix(brand)
    stat = next(h for h in matrix["hooks"] if h["slug"] == "stat_lead")
    assert "[NEED: figure]" in stat["spoken"]
    assert "possible invented number" not in stat["score"]["flags"]


def test_launch_packet_has_social_artifacts_and_gaps():
    packet = generate_launch_packet(
        sample_brand(),
        what_ships="TrendPilot launch cut",
        metric="waitlist signups",
        launch_date="2026-09-02",
    )
    assert packet["what_ships"] == "TrendPilot launch cut"
    assert packet["social"]["linkedin"]["body"]
    assert len(packet["social"]["x"]["thread"]) >= 4
    assert packet["social"]["instagram"]["body"]
    assert packet["asset_stack"]["email"]["subject"]
    assert packet["asset_stack"]["faq"]
    assert packet["honesty"]
    assert "14 campaigns shipped in Q2 2026" in packet["proof"]


def test_socialclaw_default_is_not_configured(monkeypatch):
    monkeypatch.delenv("SOCIALCLAW_API_URL", raising=False)
    status = socialclaw_status()
    assert status["configured"] is False
    assert status["status"] == "not configured"
    result = socialclaw_submit({"story": "x"}, apply=True)
    assert result["ok"] is False
    assert result["status"] == "not configured"
    assert result["applied"] is False


def test_brand_context_roundtrip(tmp_path):
    saved = save_brand_context(str(tmp_path), sample_brand())
    loaded = load_brand_context(str(tmp_path))
    assert loaded["product"]["one_sentence"] == saved["product"]["one_sentence"]
    assert loaded["contextualised"] is True


def test_score_hook_penalizes_slop():
    phrases = {
        "audience": "the people this is for",
        "category": "this category",
        "mechanism": "the mechanism",
        "worry": "the thing that keeps them up",
        "only_we": "the one thing only we can say",
        "alternative": "the old workaround",
        "product": "the product",
        "proof_numbers": "",
        "customers": "",
        "never_words": "game-changer",
        "contextualised": "no",
    }
    sloppy = {
        "visual": "seamless journey",
        "spoken": "We unlock and supercharge your ecosystem, game-changer.",
        "text": "It's not just a tool — it's a revolutionize moment.",
        "on_ramp": "leverage holistic insights",
    }
    scored = score_hook(sloppy, phrases)
    assert scored["no_slop"] < 20
    assert scored["total"] < 80


os.environ.setdefault("ADMIN_PASSWORD", "test-password")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("DISABLE_BACKGROUND_SCHEDULER", "true")


def _headers():
    import base64
    token = base64.b64encode(b"admin:test-password").decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    os.environ["DISABLE_BACKGROUND_SCHEDULER"] = "true"
    os.environ["ADMIN_PASSWORD"] = "test-password"
    import main
    monkeypatch.setattr(main, "STATE_DIR", str(tmp_path))
    return TestClient(main.app)


def test_marketing_os_api_requires_auth(api_client):
    http = api_client
    assert http.get("/api/marketing-os").status_code == 401


def test_marketing_os_api_save_hooks_and_packet(api_client):
    http = api_client
    headers = _headers()
    snap = http.get("/api/marketing-os", headers=headers)
    assert snap.status_code == 200
    body = snap.json()
    assert body["socialclaw"]["status"] == "not configured"
    assert len(body["tactics"]) == 18

    saved = http.post("/api/marketing-os/brand-context", headers=headers, json=sample_brand())
    assert saved.status_code == 200
    assert saved.json()["contextualised"] is True

    hooks = http.post("/api/marketing-os/hooks", headers=headers, json={"segment": "studio leads"})
    assert hooks.status_code == 200
    assert hooks.json()["tactic_count"] == 18
    assert hooks.json()["hooks"][0]["score"]["total"] >= 1

    packet = http.post(
        "/api/marketing-os/launch-packet",
        headers=headers,
        json={"what_ships": "Launch cut", "metric": "signups", "launch_date": "2026-09-02"},
    )
    assert packet.status_code == 200
    assert "linkedin" in packet.json()["social"]

    preview = http.post("/api/marketing-os/socialclaw/submit", headers=headers, json={"apply": False})
    assert preview.status_code == 200
    assert preview.json()["status"] == "not configured"
    assert preview.json()["ok"] is False
