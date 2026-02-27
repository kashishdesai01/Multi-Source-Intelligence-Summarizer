"""
Legal Document Agent
Credibility signals:
  - Official/gov source         (35%)
  - Jurisdiction authority      (30%)
  - Statute/case citation       (20%)
  - Recency                     (15%)
"""
from __future__ import annotations
import re
import json
import math
from datetime import datetime, timezone
from agents.base_agent import DocumentAgent
from db.models import DocumentRecord, CredibilityScore, Claim
from config import settings

JURISDICTION_SCORES = {
    "supreme court": 1.0, "court of appeals": 0.88, "district court": 0.80,
    "federal": 0.85, "state": 0.70, "municipal": 0.55,
    "us": 0.85, "eu": 0.82, "uk": 0.80,
}

GOV_DOMAINS = [".gov", ".gov.uk", ".europa.eu", ".un.org", ".court"]


def _official_source_score(url: str | None) -> float:
    if not url:
        return 0.4
    url_lower = url.lower()
    for domain in GOV_DOMAINS:
        if domain in url_lower:
            return 1.0
    return 0.45


def _jurisdiction_score(text: str) -> float:
    text_lower = text.lower()
    best = 0.5
    for keyword, score in JURISDICTION_SCORES.items():
        if keyword in text_lower:
            best = max(best, score)
    return best


def _statute_score(text: str) -> float:
    patterns = [
        r"\b\d+\s+U\.?S\.?C\.?\s+§\s*\d+",          # US Code
        r"\bPub\.?\s*L\.?\s+\d+-\d+",                  # Public Law
        r"\b\d+\s+C\.?F\.?R\.?\s+§\s*\d+",            # CFR
        r"\bArticle\s+\d+\b",
        r"\b(?:Section|§)\s+\d+",
    ]
    found = sum(1 for p in patterns if re.search(p, text))
    return min(found * 0.2, 1.0) if found else 0.25


def _recency_score(text: str, published_date: str | None) -> float:
    if not published_date:
        year_match = re.search(r"\b(19|20)\d{2}\b", text)
        if year_match:
            year = int(year_match.group())
            age = max(datetime.now(timezone.utc).year - year, 0)
            return max(0.2, math.exp(-age / 15))  # 15yr half-life for legal
        return 0.5
    try:
        date = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        age_years = (datetime.now(timezone.utc) - date).days / 365
        return max(0.2, math.exp(-age_years / 15))
    except Exception:
        return 0.5


class LegalAgent(DocumentAgent):
    doc_type = "legal_document"

    async def score_credibility(self, doc: DocumentRecord) -> CredibilityScore:
        url = doc.source_url
        published_date = doc.metadata.get("published_date")

        official = _official_source_score(url)
        jurisdiction = _jurisdiction_score(doc.raw_text)
        statute = _statute_score(doc.raw_text)
        recency = _recency_score(doc.raw_text, published_date)

        overall = (
            0.35 * official
            + 0.30 * jurisdiction
            + 0.20 * statute
            + 0.15 * recency
        )

        return CredibilityScore(
            overall=round(overall, 4),
            breakdown={
                "official_source": round(official, 4),
                "jurisdiction_authority": round(jurisdiction, 4),
                "statute_citations": round(statute, 4),
                "recency": round(recency, 4),
            },
            explanations={
                "official_source": (
                    "Official government or court domain detected (.gov, .gov.uk, etc.) — high authority"
                    if official >= 0.9 else
                    f"No official government domain found (URL: {url or 'none'}) — may be a secondary or unofficial source"
                ),
                "jurisdiction_authority": (
                    f"High-authority jurisdiction language detected in document (e.g. Supreme Court, Federal) — score: {round(jurisdiction * 100)}%"
                    if jurisdiction >= 0.75 else
                    f"Standard or unspecified jurisdiction — score: {round(jurisdiction * 100)}%"
                ),
                "statute_citations": (
                    f"Statute/code references found (U.S.C., C.F.R., Article, Section §) — score: {round(statute * 100)}%"
                    if statute >= 0.4 else
                    "Few or no formal statute citations detected — may reduce legal authority"
                ),
                "recency": (
                    f"Document appears recent — score: {round(recency * 100)}% (15-year half-life for legal documents)"
                    if recency >= 0.7 else
                    f"Document may be older — score: {round(recency * 100)}% (laws may have been amended since publication)"
                ),
            },
            signals={"source_url": url},
        )

    async def extract_claims(self, doc: DocumentRecord) -> list[Claim]:
        if not settings.openai_api_key:
            sentences = re.split(r"(?<=[.;])\s+", doc.raw_text)
            return [Claim(text=s.strip(), source_doc_id=doc.doc_id) for s in sentences[:8] if len(s.strip()) > 40]
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": 'Extract 5–8 key legal provisions or findings. Return JSON: {"claims": [...]}'},
                {"role": "user", "content": doc.raw_text[:4000]},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(resp.choices[0].message.content)
            return [Claim(text=t, source_doc_id=doc.doc_id) for t in data.get("claims", []) if isinstance(t, str)]
        except Exception:
            return []
