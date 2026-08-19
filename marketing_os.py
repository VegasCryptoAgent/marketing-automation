"""Marketing OS surface for 6Frame Studio.

Original implementation: brand-context persistence, an 18-tactic hook engine
that writes and scores original copy, a launch / social packet generator, and
an optional SocialClaw poster hook.

SocialClaw is a hosted/paid service. This module only talks to it when
SOCIALCLAW_API_URL is set. It never invents API keys and never reports a
successful post that did not happen.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests


BRAND_CONTEXT_FILENAME = "brand_context.json"
MARKETING_OS_STATE_FILENAME = "marketing_os_state.json"

SLOP_LEXICON = (
    "seamless", "seamlessly", "effortless", "frictionless", "streamlined",
    "transform", "revolutionise", "revolutionize", "unlock", "elevate",
    "empower", "supercharge", "journey", "landscape", "realm", "tapestry",
    "leverage", "utilise", "utilize", "facilitate", "robust", "holistic",
    "bespoke", "delve", "foster", "underscore", "harness", "pivotal",
    "cutting-edge", "industry-leading", "best-in-class", "world-class",
    "game-changer", "gamechanger", "in today's fast-paced", "now more than ever",
    "plethora", "myriad", "countless",
)

STRUCTURAL_SLOP = (
    re.compile(r"not just .+[,—-].+but", re.I),
    re.compile(r"it'?s not about .+[—-].+it'?s about", re.I),
    re.compile(r"what if there were a better way", re.I),
)

NUMBER_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?%?\b")

TACTICS: List[Dict[str, str]] = [
    {"id": "1", "name": "Callout", "slug": "callout", "format": "talking head",
     "what": "Name the audience in the first line."},
    {"id": "2", "name": "Question", "slug": "question", "format": "talking head",
     "what": "Open a loop the viewer has to resolve."},
    {"id": "3", "name": "Contrarian", "slug": "contrarian", "format": "static",
     "what": "Attack a belief the audience actually holds."},
    {"id": "4", "name": "Contrast", "slug": "contrast", "format": "split-screen",
     "what": "Before/after or us-vs-them, side by side."},
    {"id": "5", "name": "Demonstration", "slug": "demonstration", "format": "demo",
     "what": "The product doing the hard thing, cold, no setup."},
    {"id": "6", "name": "Pattern interrupt", "slug": "pattern_interrupt", "format": "ugc",
     "what": "Something visually wrong for the feed."},
    {"id": "7", "name": "Stat lead", "slug": "stat_lead", "format": "static",
     "what": "One number that reframes the problem."},
    {"id": "8", "name": "Fear / loss", "slug": "fear_loss", "format": "talking head",
     "what": "What the status quo is costing them right now."},
    {"id": "9", "name": "Outcome", "slug": "outcome", "format": "demo",
     "what": "The after-state, specific and sensory."},
    {"id": "10", "name": "Social witness", "slug": "social_witness", "format": "ugc",
     "what": "A real person mid-experience, overheard not performed."},
    {"id": "11", "name": "Authority", "slug": "authority", "format": "talking head",
     "what": "Credentials speak first."},
    {"id": "12", "name": "Social proof", "slug": "social_proof", "format": "static",
     "what": "Volume and consensus, only if it can be substantiated."},
    {"id": "13", "name": "Story cold-open", "slug": "story_cold_open", "format": "talking head",
     "what": "In medias res, mid-conflict, no preamble."},
    {"id": "14", "name": "Implied answer", "slug": "implied_answer", "format": "static",
     "what": "Pose the setup so the viewer finishes the thought."},
    {"id": "15", "name": "Borrowed enemy", "slug": "borrowed_enemy", "format": "talking head",
     "what": "Align against a shared villain — the old way, not the viewer."},
    {"id": "16", "name": "Trojan horse", "slug": "trojan_horse", "format": "native screenshot",
     "what": "Borrow a native format so the ad reads as content."},
    {"id": "17", "name": "Curiosity gap", "slug": "curiosity_gap", "format": "ugc",
     "what": "Withhold the mechanism, promise the reveal."},
    {"id": "18", "name": "Identity", "slug": "identity", "format": "talking head",
     "what": "Mirror the self-image, not just the job title."},
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def empty_brand_context() -> Dict[str, Any]:
    return {
        "product": {
            "one_sentence": "",
            "mechanism": "",
            "does_not": "",
        },
        "audience": {
            "who_buys": "",
            "belief_before": "",
            "worry_2am": "",
            "alternative": "",
        },
        "positioning": {
            "only_we_can_say": "",
            "category": "",
            "competitors": "",
        },
        "proof": {
            "numbers": "",
            "customers": "",
            "needs_legal": "",
        },
        "voice": {
            "how_we_sound": "",
            "how_we_never_sound": "",
            "always_words": "",
            "never_words": "",
        },
        "constraints": {
            "regulatory": "",
            "off_limits": "",
        },
        "updated_at": "",
        "contextualised": False,
    }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_brand_context(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    base = empty_brand_context()
    incoming = data or {}
    for section, fields in base.items():
        if section in ("updated_at", "contextualised"):
            continue
        src = incoming.get(section) if isinstance(incoming.get(section), dict) else {}
        for key in fields:
            base[section][key] = _clean(src.get(key, incoming.get(key, "")))
    filled = 0
    total = 0
    for section, fields in base.items():
        if section in ("updated_at", "contextualised"):
            continue
        for value in fields.values():
            total += 1
            if value:
                filled += 1
    base["updated_at"] = _clean(incoming.get("updated_at")) or utc_now()
    base["contextualised"] = filled >= 4
    base["filled_fields"] = filled
    base["total_fields"] = total
    return base


def brand_context_path(state_dir: str) -> str:
    return os.path.join(state_dir, BRAND_CONTEXT_FILENAME)


def state_path(state_dir: str) -> str:
    return os.path.join(state_dir, MARKETING_OS_STATE_FILENAME)


def load_brand_context(state_dir: str) -> Dict[str, Any]:
    path = brand_context_path(state_dir)
    if not os.path.exists(path):
        ctx = empty_brand_context()
        ctx["updated_at"] = ""
        return ctx
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return normalize_brand_context(json.load(handle))
    except Exception:
        ctx = empty_brand_context()
        ctx["updated_at"] = ""
        return ctx


def save_brand_context(state_dir: str, data: Dict[str, Any]) -> Dict[str, Any]:
    ctx = normalize_brand_context(data)
    ctx["updated_at"] = utc_now()
    os.makedirs(state_dir, exist_ok=True)
    path = brand_context_path(state_dir)
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(ctx, handle, indent=2)
    os.replace(tmp, path)
    return ctx


def load_os_state(state_dir: str) -> Dict[str, Any]:
    path = state_path(state_dir)
    if not os.path.exists(path):
        return {"hooks": None, "packet": None, "updated_at": ""}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return {"hooks": None, "packet": None, "updated_at": ""}
        data.setdefault("hooks", None)
        data.setdefault("packet", None)
        data.setdefault("updated_at", "")
        return data
    except Exception:
        return {"hooks": None, "packet": None, "updated_at": ""}


def save_os_state(state_dir: str, data: Dict[str, Any]) -> Dict[str, Any]:
    current = load_os_state(state_dir)
    current.update({k: v for k, v in data.items() if k in ("hooks", "packet")})
    current["updated_at"] = utc_now()
    os.makedirs(state_dir, exist_ok=True)
    path = state_path(state_dir)
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2)
    os.replace(tmp, path)
    return current


def list_tactics() -> List[Dict[str, str]]:
    return [dict(item) for item in TACTICS]


def _first_sentence(text: str, fallback: str) -> str:
    cleaned = re.sub(r"\s+", " ", _clean(text))
    if not cleaned:
        return fallback
    if len(cleaned) > 140:
        trimmed = cleaned[:137].rsplit(" ", 1)[0]
        return trimmed + "…"
    return cleaned


def _phrases(brand: Dict[str, Any]) -> Dict[str, str]:
    ctx = normalize_brand_context(brand)
    product = ctx["product"]
    audience = ctx["audience"]
    positioning = ctx["positioning"]
    proof = ctx["proof"]
    voice = ctx["voice"]
    constraints = ctx["constraints"]
    return {
        "product": _first_sentence(product["one_sentence"], "the product"),
        "mechanism": _first_sentence(product["mechanism"], "the mechanism"),
        "does_not": _first_sentence(product["does_not"], "things we refuse to overclaim"),
        "audience": _first_sentence(audience["who_buys"], "the people this is for"),
        "belief": _first_sentence(audience["belief_before"], "the default belief in this category"),
        "worry": _first_sentence(audience["worry_2am"], "the thing that keeps them up"),
        "alternative": _first_sentence(audience["alternative"], "the old workaround"),
        "only_we": _first_sentence(positioning["only_we_can_say"], "the one thing only we can say"),
        "category": _first_sentence(positioning["category"], "this category"),
        "competitors": _first_sentence(positioning["competitors"], "the usual vendors"),
        "proof_numbers": _clean(proof["numbers"]),
        "customers": _clean(proof["customers"]),
        "needs_legal": _clean(proof["needs_legal"]),
        "voice": _first_sentence(voice["how_we_sound"], "plain and specific"),
        "never_sound": _clean(voice["how_we_never_sound"]),
        "always_words": _clean(voice["always_words"]),
        "never_words": _clean(voice["never_words"]),
        "regulatory": _clean(constraints["regulatory"]),
        "off_limits": _clean(constraints["off_limits"]),
        "contextualised": "yes" if ctx["contextualised"] else "no",
        "filled_fields": str(ctx.get("filled_fields", 0)),
    }


def _allowed_numbers(phrases: Dict[str, str]) -> List[str]:
    blob = " ".join([phrases.get("proof_numbers", ""), phrases.get("customers", "")])
    return NUMBER_RE.findall(blob)


def _has_invented_number(text: str, phrases: Dict[str, str]) -> bool:
    allowed = set(_allowed_numbers(phrases))
    for match in NUMBER_RE.findall(text or ""):
        if match in {"1", "2", "3", "15", "90"}:
            continue
        if match not in allowed:
            return True
    return False


def _slop_hits(text: str, phrases: Dict[str, str]) -> List[str]:
    lowered = (text or "").lower()
    hits = [word for word in SLOP_LEXICON if word in lowered]
    for pattern in STRUCTURAL_SLOP:
        if pattern.search(text or ""):
            hits.append(pattern.pattern)
    never = [w.strip().lower() for w in (phrases.get("never_words") or "").split(",") if w.strip()]
    for word in never:
        if word and word in lowered:
            hits.append(f"banned:{word}")
    return hits


def _overlap_ratio(a: str, b: str) -> float:
    wa = set(re.findall(r"[a-z0-9']+", (a or "").lower()))
    wb = set(re.findall(r"[a-z0-9']+", (b or "").lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / float(max(len(wa | wb), 1))


def score_hook(hook: Dict[str, Any], phrases: Dict[str, str]) -> Dict[str, Any]:
    combined = " ".join([
        hook.get("visual") or "",
        hook.get("spoken") or "",
        hook.get("text") or "",
        hook.get("on_ramp") or "",
    ])
    flags: List[str] = []
    specifics = [
        phrases["audience"], phrases["category"], phrases["mechanism"],
        phrases["worry"], phrases["only_we"], phrases["alternative"],
        phrases["product"],
    ]
    used = 0
    for item in specifics:
        if item and item not in {
            "the product", "the mechanism", "the people this is for",
            "the thing that keeps them up", "the one thing only we can say",
            "this category", "the old workaround",
        } and item.lower() in combined.lower():
            used += 1
    specificity = min(25, 8 + used * 4)

    slop = _slop_hits(combined, phrases)
    no_slop = max(0, 20 - (6 * len(slop)))
    if slop:
        flags.append("slop:" + ",".join(slop[:4]))

    overlap = _overlap_ratio(hook.get("spoken") or "", hook.get("text") or "")
    no_duplication = 15 if overlap < 0.42 else 6
    if overlap >= 0.42:
        flags.append("spoken/text overlap")

    invented = _has_invented_number(combined, phrases)
    if invented:
        grounding = 0
        flags.append("possible invented number")
    elif "[NEED:" in combined:
        grounding = 8
        flags.append("ungrounded proof")
    elif phrases["proof_numbers"] and phrases["proof_numbers"][:24].lower() in combined.lower():
        grounding = 20
    elif phrases["contextualised"] == "yes":
        grounding = 16
    else:
        grounding = 9
        flags.append("un-contextualised brand")

    tactic_fit = 18
    total = specificity + no_slop + no_duplication + grounding + tactic_fit
    return {
        "total": int(total),
        "specificity": int(specificity),
        "no_slop": int(no_slop),
        "no_duplication": int(no_duplication),
        "grounding": int(grounding),
        "tactic_fit": int(tactic_fit),
        "flags": flags,
        "heuristic": True,
    }


def _need_figure() -> str:
    return "[NEED: figure]"


def _proof_or_need(phrases: Dict[str, str]) -> str:
    return phrases["proof_numbers"] or _need_figure()


def _customer_or_need(phrases: Dict[str, str]) -> str:
    return phrases["customers"] or "[NEED: named customer]"


def _build_components(tactic: Dict[str, str], phrases: Dict[str, str], extra: str) -> Dict[str, str]:
    product = phrases["product"]
    mechanism = phrases["mechanism"]
    audience = phrases["audience"]
    belief = phrases["belief"]
    worry = phrases["worry"]
    alternative = phrases["alternative"]
    only_we = phrases["only_we"]
    category = phrases["category"]
    competitors = phrases["competitors"]
    proof = _proof_or_need(phrases)
    customer = _customer_or_need(phrases)
    note = _first_sentence(extra, "")
    note_bit = f" {note}" if note else ""

    slug = tactic["slug"]
    if slug == "callout":
        return {
            "visual": f"Camera locks on a working {category} desk — screens live, no intro card.",
            "spoken": f"If you are {audience}, stop scrolling.",
            "text": f"for {audience}",
            "on_ramp": f"Not a pep talk. The next 12 seconds is why {alternative} keeps {worry} alive.{note_bit}",
            "motivation": worry,
            "corpus_source": "brand.audience.who_buys" if phrases["contextualised"] == "yes" else "ungrounded hypothesis",
        }
    if slug == "question":
        return {
            "visual": "A timeline playhead frozen on a ruined export. No logo.",
            "spoken": f"Why does {worry} still happen after you paid for {category}?",
            "text": "answer is not more tools",
            "on_ramp": f"If your honest answer is '{belief}', the rest of this is the counter.{note_bit}",
            "motivation": worry,
            "corpus_source": "brand.audience.worry_2am" if phrases["worry"] != "the thing that keeps them up" else "ungrounded hypothesis",
        }
    if slug == "contrarian":
        return {
            "visual": "Plain black card. One sentence. No stock smile.",
            "spoken": f"{belief} is the reason the work still looks like everyone else's.",
            "text": f"{only_we}",
            "on_ramp": f"We are not arguing taste. We are arguing that {alternative} cannot produce {only_we}.{note_bit}",
            "motivation": belief,
            "corpus_source": "brand.audience.belief_before",
        }
    if slug == "contrast":
        return {
            "visual": f"Split: left is {alternative}. Right is {mechanism} running.",
            "spoken": f"Left is how {audience} still ships. Right is the cut we actually deliver.",
            "text": "same brief. different cut.",
            "on_ramp": f"If the left side is your Tuesday, the right side is {product}.{note_bit}",
            "motivation": alternative,
            "corpus_source": "brand.audience.alternative / brand.product.mechanism",
        }
    if slug == "demonstration":
        return {
            "visual": f"No talking. Hands run {mechanism} from brief to finished frame.",
            "spoken": "Watch the cut, then decide if the voiceover was even needed.",
            "text": f"{mechanism}",
            "on_ramp": f"This is {product} doing the thing. No mood board. No 'imagine if'.{note_bit}",
            "motivation": mechanism,
            "corpus_source": "brand.product.mechanism",
        }
    if slug == "pattern_interrupt":
        return {
            "visual": "Someone bins a glossy brand-kit PDF into a studio trash can, then hits render.",
            "spoken": f"Your {category} deck is not the movie.",
            "text": "kill the deck. keep the cut.",
            "on_ramp": f"If {audience} is drowning in decks, this is the interrupt — then we show {mechanism}.{note_bit}",
            "motivation": worry,
            "corpus_source": "constructed from brand category; validate cheap",
        }
    if slug == "stat_lead":
        return {
            "visual": "One number, full frame, no decoration.",
            "spoken": f"{proof} — and {audience} still treats it like a vibe.",
            "text": "source the number before you run this",
            "on_ramp": f"If that figure is missing, do not ship this hook. Fill brand proof first.{note_bit}",
            "motivation": "reframe with a real number",
            "corpus_source": "brand.proof.numbers" if phrases["proof_numbers"] else "NEED: proof.numbers",
        }
    if slug == "fear_loss":
        return {
            "visual": "A calendar with launch day circled. The export still rendering.",
            "spoken": f"{worry} is already costing the next launch — not a future one.",
            "text": "the old way is on the clock",
            "on_ramp": f"Stay with {alternative} and you keep paying in missed windows, not in invoices.{note_bit}",
            "motivation": worry,
            "corpus_source": "brand.audience.worry_2am",
        }
    if slug == "outcome":
        return {
            "visual": "Finished piece playing on a phone in a loud room. People actually watch.",
            "spoken": f"The after-state: {audience} has a cut they can post today.",
            "text": "posted. not 'in review'.",
            "on_ramp": f"{product}. Mechanism: {mechanism}. Not a mood.{note_bit}",
            "motivation": "after-state",
            "corpus_source": "brand.product.one_sentence",
        }
    if slug == "social_witness":
        return {
            "visual": "Over-the-shoulder screen recording, notifications on, no color grade.",
            "spoken": f"'{customer} just pinged: this is the first cut I did not have to explain.'",
            "text": "overheard. not a testimonial ad.",
            "on_ramp": f"If you cannot name the customer, leave the quote as {customer} and do not fake a person.{note_bit}",
            "motivation": "in-moment proof",
            "corpus_source": "brand.proof.customers" if phrases["customers"] else "NEED: proof.customers",
        }
    if slug == "authority":
        return {
            "visual": "A bin of rejected cuts. The speaker does not look at camera at first.",
            "spoken": f"We make {category} for {audience}. {only_we}.",
            "text": "credentials, then the cut",
            "on_ramp": f"Authority here is the work, not a follower count. {product}.{note_bit}",
            "motivation": only_we,
            "corpus_source": "brand.positioning.only_we_can_say",
        }
    if slug == "social_proof":
        return {
            "visual": "A quiet grid of real project stills. No fake avatars.",
            "spoken": f"{proof} is the only volume we will put on a card.",
            "text": f"{customer}",
            "on_ramp": f"If either field is a NEED tag, this tactic stays on the bench.{note_bit}",
            "motivation": "consensus only with receipts",
            "corpus_source": "brand.proof" if phrases["proof_numbers"] or phrases["customers"] else "NEED: proof",
        }
    if slug == "story_cold_open":
        return {
            "visual": "Mid-argument in an edit bay. No title card.",
            "spoken": f"Launch morning. The {category} cut still looks like {competitors}.",
            "text": "start in the mess",
            "on_ramp": f"We do not rewind to the origin story. We show how {mechanism} got us out.{note_bit}",
            "motivation": "mid-conflict",
            "corpus_source": "constructed scene from brand category; not a fabricated client story",
        }
    if slug == "implied_answer":
        return {
            "visual": "Two folders: 'brand kit' and 'what actually posted'.",
            "spoken": f"{audience} already knows which folder the algorithm rewarded.",
            "text": "you already picked",
            "on_ramp": f"We never ask the question. The next shot is {mechanism}.{note_bit}",
            "motivation": belief,
            "corpus_source": "brand.audience",
        }
    if slug == "borrowed_enemy":
        return {
            "visual": "A stock 'AI influencer' template collapsing into artifacts.",
            "spoken": f"The enemy is {alternative} — not you for using it.",
            "text": f"vs {competitors}",
            "on_ramp": f"We line up with {audience} against the old pipeline, then show {only_we}.{note_bit}",
            "motivation": alternative,
            "corpus_source": "brand.audience.alternative / brand.positioning.competitors",
        }
    if slug == "trojan_horse":
        return {
            "visual": "iPhone Notes, dark mode, one paragraph, no brand chrome.",
            "spoken": "",
            "text": f"note to {audience}: {worry} is a process bug, not a taste problem. {mechanism} is the fix.",
            "on_ramp": f"Reads as a note, not an ad. Product reveal is the last line, not the first.{note_bit}",
            "motivation": "native format",
            "corpus_source": "native-notes format; copy from brand worry + mechanism",
        }
    if slug == "curiosity_gap":
        return {
            "visual": "A finished shot that should have taken a crew. No explanation yet.",
            "spoken": f"There is a reason this does not look like {competitors}. I will show the reason, not the slogan.",
            "text": "mechanism after the hold",
            "on_ramp": f"The cheque we cash is {mechanism}. If that field is empty, do not run this hook.{note_bit}",
            "motivation": "withhold mechanism for 3 seconds",
            "corpus_source": "brand.product.mechanism",
        }
    # identity
    return {
        "visual": "Founder, no ring light, work visible behind them.",
        "spoken": f"For {audience} who still care what the frame feels like.",
        "text": "identity, not a job title",
        "on_ramp": f"{only_we}. If that sentence could be said by {competitors}, rewrite brand context before you shoot.{note_bit}",
        "motivation": "self-image",
        "corpus_source": "brand.audience.who_buys + brand.positioning",
    }


def generate_hook_matrix(
    brand: Dict[str, Any],
    segment: str = "",
    extra_notes: str = "",
    tactic_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    phrases = _phrases(brand)
    selected = TACTICS
    if tactic_ids:
        wanted = {str(item) for item in tactic_ids}
        selected = [item for item in TACTICS if item["id"] in wanted or item["slug"] in wanted]
        if not selected:
            selected = TACTICS

    hooks = []
    for tactic in selected:
        components = _build_components(tactic, phrases, extra_notes)
        hook = {
            "id": tactic["id"],
            "tactic": tactic["name"],
            "slug": tactic["slug"],
            "format": tactic["format"],
            "what": tactic["what"],
            "segment": _clean(segment) or phrases["audience"],
            "motivation": components["motivation"],
            "visual": components["visual"],
            "spoken": components["spoken"],
            "text": components["text"],
            "on_ramp": components["on_ramp"],
            "corpus_source": components["corpus_source"],
        }
        hook["score"] = score_hook(hook, phrases)
        hooks.append(hook)

    hooks_sorted = sorted(hooks, key=lambda item: item["score"]["total"], reverse=True)
    recommended = hooks_sorted[:5]
    ungrounded = phrases["contextualised"] != "yes"
    gaps = []
    if ungrounded:
        gaps.append("Brand context has fewer than 4 filled fields. Output is un-contextualised.")
    if not phrases["proof_numbers"]:
        gaps.append("No citable numbers. Stat-lead and social-proof hooks carry [NEED: figure].")
    if not phrases["customers"]:
        gaps.append("No named customers. Social-witness quotes are tagged, not invented.")
    if phrases["needs_legal"]:
        gaps.append(f"Legal review required: {phrases['needs_legal']}")

    return {
        "generated_at": utc_now(),
        "segment": _clean(segment) or phrases["audience"],
        "contextualised": phrases["contextualised"] == "yes",
        "corpus": "brand-context.json" if phrases["contextualised"] == "yes" else "ungrounded hypotheses",
        "tactic_count": len(hooks),
        "hooks": hooks,
        "recommended_first_tests": [
            {
                "id": item["id"],
                "tactic": item["tactic"],
                "score": item["score"]["total"],
                "why": item["what"],
                "spoken": item["spoken"],
            }
            for item in recommended
        ],
        "ladder": {
            "rung_1_statics": [item["tactic"] for item in hooks if item["format"] in {"static", "native screenshot"}],
            "rung_2_motion": [item["tactic"] for item in hooks if item["format"] in {"ugc", "talking head", "demo", "split-screen"}],
            "rung_3_production": "Only promote a hook after a cheap static or uglies test survives.",
        },
        "gaps": gaps,
        "honesty": "Scores are heuristics from copy craft, not measured performance.",
        "extra_notes": _clean(extra_notes),
    }


def _flagged_claims(text: str, phrases: Dict[str, str]) -> List[str]:
    flags = []
    if "[NEED:" in text:
        flags.append("Contains a NEED tag — do not publish until filled.")
    if _has_invented_number(text, phrases):
        flags.append("Contains a number that is not in brand proof. Remove or source it.")
    slop = _slop_hits(text, phrases)
    if slop:
        flags.append("Slop lexicon: " + ", ".join(slop[:5]))
    return flags


def generate_launch_packet(
    brand: Dict[str, Any],
    what_ships: str = "",
    metric: str = "",
    launch_date: str = "",
    extra_notes: str = "",
) -> Dict[str, Any]:
    phrases = _phrases(brand)
    ships = _clean(what_ships) or phrases["product"]
    one_metric = _clean(metric) or "one conversion action (name it before launch day)"
    when = _clean(launch_date) or "[NEED: launch date]"
    proof = _proof_or_need(phrases)
    enemy = phrases["alternative"]
    story = f"{ships} exists so {phrases['audience']} can stop living with {enemy}."
    constraint = (
        "Reachable audience is unknown in this workspace — treat this as a distribution-building "
        "arc with a launch at the end, not a day you can project."
        if phrases["contextualised"] != "yes"
        else f"Strongest story lever: {phrases['only_we']}. Weakest unknown: actual list/following size."
    )

    linkedin = (
        f"{story}\n\n"
        f"The old way: {enemy}.\n"
        f"The mechanism: {phrases['mechanism']}.\n"
        f"The proof we will cite: {proof}.\n\n"
        f"If you are {phrases['audience']}, the ask is simple: {one_metric}.\n"
        f"I will answer every real objection in the comments for the first hour."
    )
    x_thread = [
        f"{story}",
        f"Enemy: {enemy}. Not you. The pipeline.",
        f"How it works: {phrases['mechanism']}.",
        f"Proof: {proof}.",
        f"If this is useful, the action is {one_metric}.",
    ]
    instagram = (
        f"{ships}\n"
        f"{phrases['only_we']}\n\n"
        f"{phrases['mechanism']}\n\n"
        f"Proof: {proof}\n"
        f"Save this if you are {phrases['audience']}."
    )
    email_subject = f"{ships} — {one_metric}"
    email_body = (
        f"Subject: {email_subject}\n\n"
        f"1. The story: {story}\n"
        f"2. What changed: {phrases['mechanism']}\n"
        f"3. What we will not claim: {phrases['does_not']}\n"
        f"4. Proof: {proof}\n"
        f"5. The only ask: {one_metric}\n"
        f"Date: {when}\n"
    )
    faq = [
        {"q": "What is actually shipping?", "a": ships},
        {"q": "Who is it for?", "a": phrases["audience"]},
        {"q": "How is this different?", "a": phrases["only_we"]},
        {"q": "What do you refuse to claim?", "a": phrases["does_not"]},
        {"q": "What number can we cite?", "a": proof},
        {"q": "What should a day-one voice actually do?", "a": "Comment or share with a specific reaction, not a generic fire emoji."},
    ]
    timeline = [
        {"when": "T-14 to T-8", "phase": "Seeding", "work": "Lock the one-sentence story. Warm 2-3 problem posts. Recruit day-one voices individually."},
        {"when": "T-7 to T-1", "phase": "Freeze", "work": "Feature freeze. Dry-run the conversion path on mobile. Pre-write posts, emails, and the 10 predictable replies."},
        {"when": f"Day 0 · {when}", "phase": "Launch", "work": "Ship primary post, personal-note the day-one list, email the list, founder posts, reply to everything for 3-4 hours."},
        {"when": "T+1 to T+7", "phase": "Harvest", "work": "How-we-built-it, objection teardown, numbers retrospective. Collect every question into FAQ."},
    ]
    social = {
        "linkedin": {
            "job": "authority",
            "hook": story,
            "body": linkedin,
            "first_comment": "Link lives here if you need a URL. Do not put it in the post body.",
            "best_window": "First 90 minutes decide distribution. Reply to every early comment.",
        },
        "x": {
            "job": "distribution",
            "hook": x_thread[0],
            "thread": x_thread,
            "first_comment": "Optional link. Native thread first.",
            "best_window": "Morning in the audience's timezone; first tweet must stand alone.",
        },
        "instagram": {
            "job": "engagement",
            "hook": phrases["only_we"],
            "body": instagram,
            "first_comment": "Keyword reply if you gate a resource. Deliver it.",
            "best_window": "When the audience actually scrolls — do not chase a generic 'best time'.",
        },
    }
    packet_text = "\n\n".join([linkedin, "\n".join(x_thread), instagram, email_body])
    gaps = []
    if phrases["contextualised"] != "yes":
        gaps.append("Brand context is thin. Packet will read interchangeable until you fill product, audience, and proof.")
    if not _clean(what_ships):
        gaps.append("what_ships was empty; fell back to product one-liner.")
    if not _clean(metric):
        gaps.append("No single metric. A launch pointed at two metrics hits neither.")
    if when.startswith("[NEED"):
        gaps.append("No launch date.")
    if not phrases["proof_numbers"]:
        gaps.append("No sourced numbers. Do not invent launch projections.")
    if extra_notes:
        gaps.append("Operator notes were included as context only, not as verified facts.")

    return {
        "generated_at": utc_now(),
        "what_ships": ships,
        "metric": one_metric,
        "launch_date": when,
        "story": story,
        "enemy": enemy,
        "proof": proof,
        "constraint": constraint,
        "timeline": timeline,
        "asset_stack": {
            "story": story,
            "email": {"subject": email_subject, "body": email_body},
            "demo_script": (
                f"0-15s problem: {phrases['worry']}. "
                f"15-45s mechanism: {phrases['mechanism']}. "
                f"45-75s result: {ships}. "
                f"75-90s CTA: {one_metric}."
            ),
            "press_blurb": f"{ships} — {phrases['only_we']} Proof: {proof}.",
            "faq": faq,
        },
        "social": social,
        "day_one_voices": {
            "ask": "Individual notes, not a BCC. Ask for one specific action at a specific time.",
            "count_target": "10-30 people who will actually show up in the first hours.",
            "list": "[NEED: names]. Do not invent a list.",
        },
        "risks": [
            {"risk": "Broken mobile conversion path", "response": "Dry-run the signup on a phone the day before. Launch week absorbs zero new scope."},
            {"risk": "Unsourced proof in public copy", "response": f"Cite only: {proof}."},
            {"risk": "Projecting launch numbers", "response": "Do not. Report levers (list size, historical CTR) after the fact."},
        ],
        "gaps": gaps,
        "flagged": _flagged_claims(packet_text, phrases),
        "honesty": "No projected launch numbers. Scores and plans are craft heuristics.",
        "extra_notes": _clean(extra_notes),
        "contextualised": phrases["contextualised"] == "yes",
    }


def socialclaw_status() -> Dict[str, Any]:
    base = (os.environ.get("SOCIALCLAW_API_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SC_API_KEY") or os.environ.get("SOCIALCLAW_API_KEY") or "").strip()
    if not base:
        return {
            "configured": False,
            "status": "not configured",
            "base_url": "",
            "has_api_key": False,
            "message": (
                "SocialClaw is a hosted/paid poster. Set SOCIALCLAW_API_URL to enable the optional hook. "
                "This app will not invent keys or fake publishes."
            ),
            "docs": "https://getsocialclaw.com",
        }
    return {
        "configured": True,
        "status": "configured",
        "base_url": base,
        "has_api_key": bool(key),
        "message": (
            "Poster hook is configured. Calls go to SOCIALCLAW_API_URL. "
            "Failed or unpaid workspaces return the real error. Nothing is faked."
        ),
        "docs": "https://getsocialclaw.com",
    }


def socialclaw_submit(packet: Dict[str, Any], apply: bool = False) -> Dict[str, Any]:
    cfg = socialclaw_status()
    if not cfg["configured"]:
        return {
            "ok": False,
            "status": "not configured",
            "applied": False,
            "message": cfg["message"],
            "docs": cfg["docs"],
        }
    base = cfg["base_url"]
    key = (os.environ.get("SC_API_KEY") or os.environ.get("SOCIALCLAW_API_KEY") or "").strip()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    path = "/v1/campaigns/preview" if not apply else "/v1/apply"
    url = urljoin(base + "/", path.lstrip("/")) if not base.endswith(path) else base
    try:
        response = requests.post(url, json={"packet": packet, "apply": apply}, headers=headers, timeout=20)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status": "request_failed",
            "applied": False,
            "message": f"SocialClaw request failed: {exc}",
            "url": url,
        }
    body: Any
    try:
        body = response.json()
    except ValueError:
        body = {"raw": (response.text or "")[:800]}
    return {
        "ok": 200 <= response.status_code < 300,
        "status": "submitted" if 200 <= response.status_code < 300 else f"http_{response.status_code}",
        "applied": bool(apply) and 200 <= response.status_code < 300,
        "http_status": response.status_code,
        "url": url,
        "response": body,
        "message": "Hosted SocialClaw responded. Inspect http_status and response; this app did not invent a publish.",
    }


def snapshot(state_dir: str) -> Dict[str, Any]:
    brand = load_brand_context(state_dir)
    state = load_os_state(state_dir)
    return {
        "brand": brand,
        "tactics": list_tactics(),
        "socialclaw": socialclaw_status(),
        "last_hooks": state.get("hooks"),
        "last_packet": state.get("packet"),
        "updated_at": state.get("updated_at") or brand.get("updated_at") or "",
    }
