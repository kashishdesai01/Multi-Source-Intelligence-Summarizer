"""
Blog Post Agent
Credibility signals:
  - Domain authority (static DB)  (30%)
  - Author credentials via LLM    (25%)
  - External references cited     (25%)
  - Recency                       (20%)
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

_DOMAIN_DB_PATH = Path(__file__).parent.parent / "data" / "domain_authority_db.json"
_DOMAIN_DB: dict[str, float] = {}


def _load_domain_db() -> dict[str, float]:
    global _DOMAIN_DB
    if _DOMAIN_DB:
        return _DOMAIN_DB
    if _DOMAIN_DB_PATH.exists():
        with open(_DOMAIN_DB_PATH) as f:
            _DOMAIN_DB = json.load(f)
    else:
        _DOMAIN_DB = {
            "medium.com": 0.72, "substack.com": 0.65, "wordpress.com": 0.55,
            "towardsdatascience.com": 0.82, "hackernoon.com": 0.75,
            "techcrunch.com": 0.88, "wired.com": 0.87, "ycombinator.com": 0.90,
        }
    return _DOMAIN_DB


def _domain_score(url: str | None) -> float:
    if not url:
        return 0.4
    db = _load_domain_db()
    for domain, score in db.items():
        if domain in url:
            return score
    return 0.45


def _references_score(text: str) -> float:
    """Count external links and named references."""
    links = len(re.findall(r"https?://[^\s)>\"]+", text))
    return min(links * 0.08, 1.0) if links else 0.2


def _recency_score(published_date: str | None) -> float:
    if not published_date:
        return 0.4
    try:
        date = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - date).days
        return max(0.1, math.exp(-age_days / 730))  # 2yr half-life for blogs
    except Exception:
        return 0.4


async def _author_credentials_score(text: str) -> float:
    """Ask GPT to assess author authority from bio/intro text."""
    if not settings.openai_api_key:
        return 0.5
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Based on any author bio, introduction, or writing style in the text, "
                    "rate the author's apparent expertise and credentials on a scale of 0.0 to 1.0. "
                    "Return ONLY a JSON object: {\"score\": <float>}"
                ),
            },
            {"role": "user", "content": text[:2000]},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        data = json.loads(resp.choices[0].message.content)
        return float(data.get("score", 0.5))
    except Exception:
        return 0.5


class BlogAgent(DocumentAgent):
    doc_type = "blog_post"

    async def score_credibility(self, doc: DocumentRecord) -> CredibilityScore:
        url = doc.source_url
        published_date = doc.metadata.get("published_date")

        domain = _domain_score(url)
        references = _references_score(doc.raw_text)
        recency = _recency_score(published_date)
        author = await _author_credentials_score(doc.raw_text)

        overall = (
            0.30 * domain
            + 0.25 * author
            + 0.25 * references
            + 0.20 * recency
        )

        links = len(re.findall(r"https?://[^\s)<\"]+", doc.raw_text))
        return CredibilityScore(
            overall=round(overall, 4),
            breakdown={
                "domain_authority": round(domain, 4),
                "author_credentials": round(author, 4),
                "external_references": round(references, 4),
                "recency": round(recency, 4),
            },
            explanations={
                "domain_authority": (
                    f"{'High-authority domain' if domain >= 0.8 else 'Moderate-authority domain' if domain >= 0.55 else 'Low or unknown domain authority'} — score: {round(domain * 100)}%"
                    + (f" (source: {url})" if url else " (no URL provided)")
                ),
                "author_credentials": (
                    f"{'Strong author credentials detected' if author >= 0.75 else 'Some author credentials detected' if author >= 0.45 else 'Limited or no author credentials found'} via LLM assessment — score: {round(author * 100)}%"
                ),
                "external_references": (
                    f"{links} external link{'s' if links != 1 else ''} found in document — "
                    + ('well-referenced' if references >= 0.5 else 'moderately referenced' if references >= 0.25 else 'few or no external sources cited')
                ),
                "recency": (
                    f"{'Recent' if recency >= 0.7 else 'Somewhat dated' if recency >= 0.4 else 'Older'} post — score: {round(recency * 100)}% (2-year half-life for blog content)"
                ),
            },
            signals={"source_url": url, "published_date": published_date},
        )

    async def extract_claims(self, doc: DocumentRecord) -> list[Claim]:
        if not settings.openai_api_key:
            sentences = re.split(r"(?<=[.!?])\s+", doc.raw_text)
            return [Claim(text=s.strip(), source_doc_id=doc.doc_id) for s in sentences[:6] if len(s) > 40]
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": 'Extract 4–6 key factual claims. Return JSON: {"claims": [...]}'},
                {"role": "user", "content": doc.raw_text[:3000]},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(resp.choices[0].message.content)
            return [Claim(text=t, source_doc_id=doc.doc_id) for t in data.get("claims", []) if isinstance(t, str)]
        except Exception:
            return []
