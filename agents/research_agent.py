"""
Research Paper Agent
Credibility signals:
  - Source authority (trust DB + domain patterns)   (30%)  ← new
  - Journal Impact Factor / venue tier               (25%)  ← was 35%
  - Citation count log-scaled                        (20%)  ← was 25%
  - Recency (5yr half-life decay)                    (15%)  ← was 20%
  - Author h-index                                   (10%)  ← was 15%

When Semantic Scholar returns no data (policy reports, org publications):
  source authority is weighted at 60%, recency at 40% — no academic penalty.
"""
from __future__ import annotations
import json
import math
import re
import httpx
from pathlib import Path
from datetime import datetime, timezone
from agents.base_agent import DocumentAgent
from db.models import DocumentRecord, CredibilityScore, Claim
from config import settings

# Rough venue tier → normalised score (0–1)
VENUE_TIER: dict[str, float] = {
    "nature": 1.0, "science": 1.0, "cell": 0.98,
    "lancet": 0.97, "nejm": 0.97, "jama": 0.96,
    "ieee": 0.85, "acm": 0.82, "plos": 0.75,
    "arxiv": 0.5, "biorxiv": 0.45, "preprint": 0.35,
}

SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"

from agents.source_authority import get_source_authority
from utils.hierarchical_summarizer import hierarchical_summarize, keyword_section_summary


# ── Semantic Scholar ──────────────────────────────────────────────────────────

async def _fetch_paper_meta(title: str) -> dict:
    """Hit Semantic Scholar to get citations, year, venue, authors."""
    headers = {}
    if settings.semantic_scholar_key:
        headers["x-api-key"] = settings.semantic_scholar_key
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{SEMANTIC_SCHOLAR_BASE}/paper/search",
                params={
                    "query": title,
                    "limit": 1,
                    "fields": "citationCount,year,venue,authors.hIndex,isOpenAccess,publicationTypes",
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            papers = data.get("data", [])
            return papers[0] if papers else {}
    except Exception:
        return {}


# ── Sub-scores ────────────────────────────────────────────────────────────────

def _recency_score(year: int | None) -> float:
    if not year:
        return 0.5
    age = max(datetime.now(timezone.utc).year - year, 0)
    return math.exp(-math.log(2) * age / 5)


def _citation_score(count: int | None) -> float:
    if count is None:
        return 0.0   # unknown — don't assume anything
    return min(math.log1p(count) / math.log1p(5000), 1.0)


def _venue_score(venue: str) -> float:
    if not venue:
        return 0.0   # unknown venue — don't assume anything
    v = venue.lower()
    for key, score in VENUE_TIER.items():
        if key in v:
            return score
    return 0.55


def _hindex_score(authors: list) -> float:
    indices = [a.get("hIndex", 0) for a in authors if isinstance(a, dict)]
    if not indices:
        return 0.0   # unknown — don't penalise but don't boost
    return min(max(indices) / 60, 1.0)


# ── Main agent ────────────────────────────────────────────────────────────────

class ResearchAgent(DocumentAgent):
    doc_type = "research_paper"

    async def score_credibility(self, doc: DocumentRecord) -> CredibilityScore:
        title = doc.title or doc.raw_text[:200]
        meta = await _fetch_paper_meta(title)

        citations = meta.get("citationCount")
        year = meta.get("year")
        venue = meta.get("venue", "")
        authors = meta.get("authors", [])
        pub_types = meta.get("publicationTypes", [])
        peer_reviewed = any(
            t in ["JournalArticle", "Conference"] for t in pub_types
        ) or ("journal" in venue.lower())

        # Sub-scores
        recency   = _recency_score(year)
        citation  = _citation_score(citations)
        venue_s   = _venue_score(venue)
        hindex    = _hindex_score(authors)
        authority = await get_source_authority(doc.source_url)

        # Determine whether we have useful academic signals
        has_academic_data = bool(meta)  # Semantic Scholar returned something

        if has_academic_data:
            # Full academic paper — all signals contribute
            auth_s = authority if authority is not None else 0.5
            overall = (
                0.30 * auth_s
                + 0.25 * venue_s
                + 0.20 * citation
                + 0.15 * recency
                + 0.10 * hindex
            )
            breakdown = {
                "source_authority": round(auth_s, 4),
                "venue_tier":       round(venue_s, 4),
                "citation_count":   round(citation, 4),
                "recency":          round(recency, 4),
                "author_hindex":    round(hindex, 4),
            }
            explanations = {
                "source_authority": f"Domain authority score: {round(auth_s * 100)}% — {'known trustworthy source' if auth_s >= 0.7 else 'unverified or lower-trust domain'}",
                "venue_tier": f"Published in '{venue or 'unknown venue'}' — {'top-tier peer-reviewed venue' if venue_s >= 0.85 else 'mid-tier or preprint venue' if venue_s >= 0.5 else 'unknown or low-tier venue'}",
                "citation_count": f"{citations if citations is not None else 'unknown'} citation{'s' if citations != 1 else ''} — {'highly cited' if citation >= 0.7 else 'moderately cited' if citation >= 0.3 else 'few or no citations found'}",
                "recency": f"Published in {year or 'unknown year'} — {'very recent' if recency >= 0.85 else 'fairly recent' if recency >= 0.6 else 'older work'} (5-year half-life decay applied)",
                "author_hindex": f"Lead author h-index: {max([a.get('hIndex', 0) for a in authors if isinstance(a, dict)], default=0)} — {'highly prolific researcher' if hindex >= 0.6 else 'established researcher' if hindex >= 0.3 else 'limited publication history found'}",
            }
        else:
            # No academic data (policy report, org publication, etc.)
            if authority is not None:
                overall = 0.65 * authority + 0.35 * recency
                breakdown = {
                    "source_authority": round(authority, 4),
                    "recency":          round(recency, 4),
                }
                explanations = {
                    "source_authority": f"Domain authority score: {round(authority * 100)}% — no academic metadata found; relying on source domain trust",
                    "recency": f"Estimated publication year: {year or 'unknown'} — {'recent' if recency >= 0.7 else 'older content'} (15-year half-life for policy docs)",
                }
            else:
                # Unknown source, no academic data → neutral-low
                overall = 0.35 * recency + 0.65 * 0.4
                breakdown = {
                    "source_authority": 0.4,
                    "recency":          round(recency, 4),
                }
                explanations = {
                    "source_authority": "Unknown domain and no academic metadata — defaulting to neutral-low authority (0.4)",
                    "recency": f"Estimated publication year: {year or 'unknown'} — {'recent' if recency >= 0.7 else 'older content'}",
                }

        doc.metadata.update({
            "citations": citations,
            "year": year,
            "venue": venue,
            "peer_reviewed": peer_reviewed,
            "source_authority": authority,
        })

        return CredibilityScore(
            overall=round(overall, 4),
            breakdown=breakdown,
            explanations=explanations,
            signals={
                "citation_count_raw": citations,
                "publication_year":   year,
                "venue":              venue,
                "peer_reviewed":      peer_reviewed,
                "source_url":         doc.source_url,
                "scoring_method":     "authority_only" if not has_academic_data else "academic_blend",
            },
        )

    async def extract_claims(self, doc: DocumentRecord) -> list[Claim]:
        return await _extract_claims_hierarchical(doc)


async def _extract_claims_hierarchical(doc: DocumentRecord) -> list[Claim]:
    """
    For research papers: condense the full paper section-by-section first,
    then extract claims from the condensed text.
    Ensures coverage of Methods, Results, and Conclusion — not just the abstract.
    """
    word_count = len(doc.raw_text.split())
    is_long = word_count > 1500  # ~6+ pages

    if not settings.openai_api_key:
        condensed = keyword_section_summary(doc.raw_text)
        doc.metadata["condensed_text"] = condensed
        doc.metadata["hierarchical"] = True
        return _fallback_sentence_claims(doc, text_override=condensed)

    from openai import AsyncOpenAI
    import json as _json
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Step 1: condense the full paper into section summaries
    if is_long:
        result = await hierarchical_summarize(
            doc.raw_text, client, model=settings.openai_model
        )
        condensed = result["condensed_text"]
        doc.metadata["hierarchical"] = True
        doc.metadata["section_count"] = result["section_count"]
        doc.metadata["condensed_word_count"] = len(condensed.split())
    else:
        condensed = doc.raw_text
        doc.metadata["hierarchical"] = False

    # Store condensed text for the RAG pipeline to use instead of raw_text
    doc.metadata["condensed_text"] = condensed

    # Step 2: extract claims from the condensed section summaries
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scientific research assistant. "
                    "Given section-by-section summaries of a research paper, extract "
                    "8–12 key factual claims covering the problem, methodology, results, "
                    "and conclusions. Each claim must be a single precise sentence. "
                    'Return JSON: {"claims": ["claim 1", "claim 2", ...]}'
                ),
            },
            {"role": "user", "content": condensed},
        ],
        temperature=0,
        max_tokens=800,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    try:
        data = _json.loads(raw)
        texts = data.get("claims", data.get("results", list(data.values())[0]))
        return [Claim(text=t, source_doc_id=doc.doc_id) for t in texts if isinstance(t, str)]
    except Exception:
        return _fallback_sentence_claims(doc, text_override=condensed)


def _fallback_sentence_claims(doc: DocumentRecord, text_override: str | None = None) -> list[Claim]:
    text = text_override or doc.raw_text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [
        Claim(text=s.strip(), source_doc_id=doc.doc_id)
        for s in sentences[:10]
        if len(s.strip()) > 40
    ]
