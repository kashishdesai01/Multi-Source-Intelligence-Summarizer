"""
News Article Agent
Credibility signals:
  - Source trust score (Media Bias/Fact Check)  (40%)
  - Cross-source corroboration                  (15%)
  - Primary source citations/quotes             (15%)
  - Recency                                     (20%)
  - Author byline present                       (10%)
"""
from __future__ import annotations
import re
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from agents.base_agent import DocumentAgent
from db.models import DocumentRecord, CredibilityScore, Claim
from config import settings

# Bundled trust score database (0.0 – 1.0)
_TRUST_DB_PATH = Path(__file__).parent.parent / "data" / "news_trust_db.json"
_TRUST_DB: dict[str, float] = {}


def _load_trust_db() -> dict[str, float]:
    global _TRUST_DB
    if _TRUST_DB:
        return _TRUST_DB
    if _TRUST_DB_PATH.exists():
        with open(_TRUST_DB_PATH) as f:
            raw = json.load(f)
        # Strip comment keys (keys starting with _)
        _TRUST_DB = {k: v for k, v in raw.items() if not k.startswith("_")}
    else:
        _TRUST_DB = {
            "reuters.com": 0.94, "apnews.com": 0.94, "bbc.com": 0.91,
            "theguardian.com": 0.87, "nytimes.com": 0.86, "npr.org": 0.88,
            "unep.org": 0.97, "who.int": 0.97, "un.org": 0.97,
            "cdc.gov": 0.96, "nih.gov": 0.97, "nature.com": 0.97,
            "foxnews.com": 0.65, "breitbart.com": 0.35, "infowars.com": 0.10,
        }
    return _TRUST_DB


# TLD/domain patterns for authoritative sources not requiring an exact DB entry
_AUTHORITATIVE_PATTERNS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"\.gov(\/|$|\.)"),         0.93),  # Any .gov domain
    (re.compile(r"\.gov\.[a-z]{2}(\/|$)"),  0.92),  # .gov.uk, .gov.au etc.
    (re.compile(r"\.int(\/|$|\.)"),          0.94),  # .int (WHO, NATO, etc.)
    (re.compile(r"\.un\.org"),               0.97),  # UN agencies
    (re.compile(r"\.edu(\/|$|\.)"),          0.88),  # University/academic
    (re.compile(r"\.ac\.[a-z]{2}(\/|$)"),   0.87),  # UK/AU academic
    (re.compile(r"\.edu\.[a-z]{2}(\/|$)"),  0.87),  # International academic
]


def _source_trust_score(url: str | None, publisher: str | None) -> float:
    db = _load_trust_db()

    if url:
        # Exact/substring match against DB first
        for domain, score in db.items():
            if domain in url:
                return score
        # Pattern-based TLD matching for authoritative domains
        for pattern, score in _AUTHORITATIVE_PATTERNS:
            if pattern.search(url):
                return score

    if publisher:
        pub_lower = publisher.lower()
        for domain, score in db.items():
            if any(part in pub_lower for part in domain.split(".")):
                return score

    return 0.5  # unknown source gets middle score


def _recency_score(published_date: str | None) -> float:
    if not published_date:
        return 0.5
    try:
        date = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - date).days
        return max(0.1, math.exp(-age_days / 365))
    except Exception:
        return 0.5


def _byline_score(text: str) -> float:
    has_byline = bool(re.search(
        r"\bBy\s+[A-Z][a-z]+\s+[A-Z][a-z]+|\bReported\s+by\b|\bStaff\s+Writer\b",
        text
    ))
    return 0.9 if has_byline else 0.3


def _citation_score_news(text: str) -> float:
    """Check for quoted officials, named sources, statistics with citations."""
    quoted = len(re.findall(r'"[^"]{20,}"', text))
    named_sources = len(re.findall(
        r'(?:said|told|according\s+to|stated|confirmed)\s+[A-Z]', text
    ))
    score = min((quoted * 0.1 + named_sources * 0.08), 1.0)
    return max(score, 0.2)


from agents.source_authority import get_source_authority


class NewsAgent(DocumentAgent):
    doc_type = "news_article"

    async def score_credibility(self, doc: DocumentRecord) -> CredibilityScore:
        url = doc.source_url
        publisher = doc.metadata.get("publisher")
        published_date = doc.metadata.get("published_date")

        # Tier-1/2/3 dynamic lookup with MongoDB caching
        source_trust = await get_source_authority(url)
        recency = _recency_score(published_date)
        byline = _byline_score(doc.raw_text)
        citation = _citation_score_news(doc.raw_text)
        corroboration = doc.metadata.get("corroboration_score", 0.5)

        overall = (
            0.40 * source_trust
            + 0.20 * recency
            + 0.15 * citation
            + 0.15 * corroboration
            + 0.10 * byline
        )

        doc.metadata.update({
            "source_trust_score": source_trust,
            "publisher": publisher,
            "published_date": published_date,
        })

        return CredibilityScore(
            overall=round(overall, 4),
            breakdown={
                "source_trust": round(source_trust, 4),
                "recency": round(recency, 4),
                "primary_citations": round(citation, 4),
                "corroboration": round(corroboration, 4),
                "byline": round(byline, 4),
            },
            explanations={
                "source_trust": (
                    f"{'High-trust outlet' if source_trust >= 0.85 else 'Moderate-trust outlet' if source_trust >= 0.6 else 'Low-trust or unverified outlet'} — domain trust score: {round(source_trust * 100)}%"
                ),
                "recency": (
                    f"{'Very recent' if recency >= 0.8 else 'Fairly recent' if recency >= 0.5 else 'Older article'} — score: {round(recency * 100)}% (1-year decay applied)"
                ),
                "primary_citations": (
                    f"{'Good number of' if citation >= 0.5 else 'Some' if citation >= 0.3 else 'Few'} named sources and direct quotes detected — score: {round(citation * 100)}%"
                ),
                "corroboration": (
                    f"Cross-source corroboration score: {round(corroboration * 100)}%"
                ),
                "byline": (
                    "Named author byline detected — increases accountability"
                    if byline >= 0.8 else
                    "No clear author byline found — reduces accountability signal"
                ),
            },
            signals={
                "source_url": url,
                "publisher": publisher,
                "published_date": published_date,
            },
        )


    async def extract_claims(self, doc: DocumentRecord) -> list[Claim]:
        return await _extract_news_claims(doc)


async def _extract_news_claims(doc: DocumentRecord) -> list[Claim]:
    if not settings.openai_api_key:
        return _fallback(doc)
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract 5–8 key factual claims from this news article. "
                    "Each claim must be a single assertive sentence. "
                    'Return a JSON object with key "claims" containing an array of strings.'
                ),
            },
            {"role": "user", "content": doc.raw_text[:4000]},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        texts = data.get("claims", [])
        return [Claim(text=t, source_doc_id=doc.doc_id) for t in texts if isinstance(t, str)]
    except Exception:
        return _fallback(doc)


def _fallback(doc: DocumentRecord) -> list[Claim]:
    sentences = re.split(r"(?<=[.!?])\s+", doc.raw_text)
    return [
        Claim(text=s.strip(), source_doc_id=doc.doc_id)
        for s in sentences[:8]
        if len(s.strip()) > 40
    ]
