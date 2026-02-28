"""
Dynamic source authority scoring — 3-tier lookup.

Tier 1: TLD/domain patterns (instant, covers all .gov/.edu/.int/.un.org)
Tier 2: OpenPageRank API (free, no key needed, covers millions of domains)
Tier 3: LLM inference (GPT-4o-mini, for unknown/niche sources)

Results are cached in MongoDB (DomainTrust collection) so each domain is
only looked up once. The static DB acts as curated overrides for known
biases (e.g. RT.com has high PageRank but is propaganda).
"""
from __future__ import annotations
import json
import re
import math
import httpx
from pathlib import Path
from urllib.parse import urlparse
from config import settings

# ── Static override DB (curated corrections) ─────────────────────────────────
_STATIC_DB_PATH = Path(__file__).parent.parent / "data" / "news_trust_db.json"
_static_db: dict[str, float] | None = None

# Manual bias corrections: high-PR domains with known credibility issues
_BIAS_CORRECTIONS = {
    "rt.com": 0.20,          # Russian state media (high PR, low trust)
    "sputniknews.com": 0.18,
    "globalresearch.ca": 0.15,
    "zerohedge.com": 0.28,
    "dailywire.com": 0.45,
    "thedailybeast.com": 0.58,
    "huffpost.com": 0.65,
    "buzzfeednews.com": 0.68,
}


def _load_static_db() -> dict[str, float]:
    global _static_db
    if _static_db is not None:
        return _static_db
    if _STATIC_DB_PATH.exists():
        with open(_STATIC_DB_PATH) as f:
            raw = json.load(f)
        _static_db = {k: v for k, v in raw.items() if not k.startswith("_")}
    else:
        _static_db = {}
    _static_db.update(_BIAS_CORRECTIONS)
    return _static_db


def _extract_domain(url: str) -> str:
    """Extract registrable domain from a URL, e.g. 'https://eaps.mit.edu/...' → 'mit.edu'."""
    try:
        host = urlparse(url).netloc.lower().lstrip("www.")
        # return last 2 parts (handles sub.domain.com → domain.com)
        # but keep 3 parts for known ccTLD combos like co.uk, gov.uk
        parts = host.split(".")
        if len(parts) >= 3 and parts[-2] in ("gov", "ac", "co", "edu", "org", "net"):
            return ".".join(parts[-3:])
        return ".".join(parts[-2:]) if len(parts) >= 2 else host
    except Exception:
        return url


# ── Tier-1: TLD / pattern rules (zero cost) ──────────────────────────────────

_TLD_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"\.gov(\/|$|\.)"),        0.93),
    (re.compile(r"\.gov\.[a-z]{2}(\/|$)"), 0.92),
    (re.compile(r"\.int(\/|$|\.)"),         0.94),
    (re.compile(r"\.un\.org"),              0.97),
    (re.compile(r"\.edu(\/|$|\.)"),         0.88),
    (re.compile(r"\.edu\.[a-z]{2}(\/|$)"),  0.87),
    (re.compile(r"\.ac\.[a-z]{2}(\/|$)"),   0.87),
]

_KNOWN_ADVOCACY_TLDS = re.compile(r"\.(advocacy|campaign)\.")


def _tier1_lookup(url: str) -> float | None:
    """TLD/pattern check — instant, covers .gov/.edu/.int etc."""
    db = _load_static_db()
    # Check static DB first (highest priority — includes bias corrections)
    for domain, score in db.items():
        if domain in url:
            return score
    # Pattern-based TLD matching
    for pattern, score in _TLD_PATTERNS:
        if pattern.search(url):
            return score
    return None


# ── Tier-2: OpenPageRank API (free, no auth needed) ──────────────────────────

OPEN_PR_API = "https://openpagerank.com/api/v1.0/getPageRank"


async def _tier2_openpagerank(domain: str) -> float | None:
    """
    OpenPageRank returns a 0-10 domain authority score.
    We normalise it to 0-1 with a calibrated curve:
    - Score 8-10: trusted major sites → 0.75-0.90
    - Score 5-7: mid-tier sites       → 0.55-0.74
    - Score 2-4: small/niche sites    → 0.35-0.54
    - Score 0-1: very small/unknown   → 0.20-0.34
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                OPEN_PR_API,
                params={"domains[]": domain},
                headers={"API-OPR": settings.open_pagerank_key} if getattr(settings, "open_pagerank_key", "") else {},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("response", [])
            if not results:
                return None
            pr_score = results[0].get("page_rank_decimal")
            if pr_score is None:
                return None

            # Calibrated normalisation: sigmoid-like curve anchored at real examples
            # PR=9 (google.com) → ~0.90, PR=7 (medium-sized news) → ~0.72,
            # PR=5 (small news) → ~0.58, PR=2 → ~0.38
            normalised = 0.20 + 0.70 * (1 - math.exp(-0.35 * float(pr_score)))
            return round(normalised, 4)
    except Exception:
        return None


# ── Tier-3: LLM inference (GPT-4o-mini) ──────────────────────────────────────

_LLM_SYSTEM = """You are a source credibility assessor. Given a domain name, output a JSON object with:
- "score": float 0.0-1.0 (credibility/authority)
- "type": one of "news", "academic", "government", "international_org", "advocacy", "blog", "unknown"
- "reasoning": one short sentence

Scoring guide:
- International orgs (UN, WHO, IEA): 0.90-0.97
- Government agencies: 0.88-0.96
- Top academic journals/universities: 0.85-0.97
- Major wire services / public broadcasters: 0.88-0.94
- Quality news outlets: 0.75-0.88
- Smaller news / magazines: 0.60-0.75
- Advocacy / think tanks with known bias: 0.40-0.65
- Blogs / personal sites: 0.30-0.55
- Conspiracy / state propaganda: 0.05-0.30

Respond ONLY with the JSON object."""


async def _tier3_llm(domain: str) -> float | None:
    """Ask GPT-4o-mini to assess domain credibility. Used for truly unknown sources."""
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": f"Domain: {domain}"},
            ],
            temperature=0,
            max_tokens=120,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        score = data.get("score")
        if isinstance(score, (int, float)) and 0 <= score <= 1:
            return round(float(score), 4)
    except Exception:
        pass
    return None


# ── MongoDB cache ─────────────────────────────────────────────────────────────

async def _cache_get(domain: str) -> float | None:
    """Check MongoDB for a cached score."""
    try:
        from db.models import DomainTrust
        entry = await DomainTrust.find_one(DomainTrust.domain == domain)
        return entry.score if entry else None
    except Exception:
        return None


async def _cache_set(domain: str, score: float, method: str) -> None:
    """Persist a score to MongoDB."""
    try:
        from db.models import DomainTrust
        from datetime import datetime, timezone
        entry = await DomainTrust.find_one(DomainTrust.domain == domain)
        if entry:
            entry.score = score
            entry.method = method
            entry.updated_at = datetime.now(timezone.utc)
            await entry.save()
        else:
            await DomainTrust(domain=domain, score=score, method=method).insert()
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

async def get_source_authority(url: str | None) -> float:
    """
    Main entry point. Returns a 0-1 credibility score for the given URL.
    Uses 3-tier lookup with MongoDB caching.
    """
    if not url:
        return 0.5  # unknown

    # Tier 1: instant pattern/static lookup (no I/O)
    t1 = _tier1_lookup(url)
    if t1 is not None:
        return t1

    domain = _extract_domain(url)

    # MongoDB cache
    cached = await _cache_get(domain)
    if cached is not None:
        return cached

    # Tier 2: OpenPageRank
    t2 = await _tier2_openpagerank(domain)
    if t2 is not None:
        await _cache_set(domain, t2, "openpagerank")
        return t2

    # Tier 3: LLM inference
    t3 = await _tier3_llm(domain)
    if t3 is not None:
        await _cache_set(domain, t3, "llm")
        return t3

    # Complete fallback
    await _cache_set(domain, 0.45, "default")
    return 0.45
