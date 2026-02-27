"""
Classifier agent: determines document type using keyword scoring.
Primary: fast keyword + pattern scoring (no model needed, no downloads)
Fallback: GPT-4o-mini for low-confidence cases (requires OPENAI_API_KEY)
"""
from __future__ import annotations
import re
from config import settings

DOC_TYPES = ["research_paper", "news_article", "blog_post", "legal_document", "unknown"]

# ── Keyword signal tables ─────────────────────────────────────────────────────

_SIGNALS: dict[str, dict] = {
    "research_paper": {
        "keywords": [
            "abstract", "introduction", "methodology", "conclusion", "references",
            "doi", "arxiv", "peer-reviewed", "hypothesis", "experiment", "dataset",
            "literature review", "findings", "results", "figure", "table", "appendix",
            "journal", "proceedings", "citation", "et al", "preprint",
        ],
        "patterns": [
            r"\babstract\b.{0,600}\bintroduction\b",
            r"\breferences\b[\s\S]{0,300}\[\d+\]",
            r"\b\d+\.\s+introduction\b",
            r"doi\.org",
            r"arxiv\.org",
        ],
        "weight": 1.0,
    },
    "news_article": {
        "keywords": [
            "reported", "according to", "said", "spokesperson", "breaking",
            "exclusive", "journalist", "byline", "wire", "AP", "Reuters", "AFP",
            "correspondent", "editor", "bureau", "published", "updated",
            "news", "article", "press", "media",
        ],
        "patterns": [
            r"\bby [A-Z][a-z]+ [A-Z][a-z]+\b",
            r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
            r"\breuters\b|\bap news\b|\bbbc\b|\bcnn\b|\bnpr\b",
            r"\b(hours?|days?|weeks?) ago\b",
        ],
        "weight": 1.0,
    },
    "blog_post": {
        "keywords": [
            "i think", "i believe", "in my opinion", "my experience",
            "subscribe", "newsletter", "follow me", "share this", "comment below",
            "read more", "click here", "posted", "author bio", "about me",
            "substack", "medium", "wordpress", "blogger",
        ],
        "patterns": [
            r"\bsubstack\.com\b",
            r"\bmedium\.com\b",
            r"\bwordpress\b",
            r"subscribe\s+to\s+(my|our|the)",
        ],
        "weight": 1.0,
    },
    "legal_document": {
        "keywords": [
            "whereas", "hereinafter", "pursuant to", "plaintiff", "defendant",
            "jurisdiction", "hereby", "notwithstanding", "shall", "contract",
            "agreement", "liability", "party", "clause", "indemnify",
            "statute", "regulation", "ordinance", "section", "subsection",
        ],
        "patterns": [
            r"\bwhereas\b",
            r"\bhereinafter\b",
            r"\bparty of the first part\b",
            r"\bpursuant to\b",
            r"§\s*\d+",
        ],
        "weight": 1.0,
    },
}


def _keyword_score(text: str, title: str = "") -> dict[str, float]:
    """Score each document type based on keyword and pattern hits."""
    sample = (title + "\n\n" + text).lower()[:3000]
    sample_raw = (title + "\n\n" + text)[:3000]

    scores: dict[str, float] = {}
    for doc_type, signals in _SIGNALS.items():
        kw_hits = sum(1 for kw in signals["keywords"] if kw.lower() in sample)
        pat_hits = sum(
            1 for pat in signals["patterns"]
            if re.search(pat, sample_raw, re.IGNORECASE | re.DOTALL)
        )
        # Normalise: keywords out of total, patterns weighted more
        kw_score = kw_hits / max(len(signals["keywords"]), 1)
        pat_score = pat_hits / max(len(signals["patterns"]), 1)
        scores[doc_type] = (0.4 * kw_score + 0.6 * pat_score) * signals["weight"]

    return scores


async def classify_document(text: str, title: str = "") -> str:
    """Classify a document and return its DocType string."""
    scores = _keyword_score(text, title)
    best_type = max(scores, key=lambda k: scores[k])
    best_score = scores[best_type]

    # High confidence → return immediately (no API call needed)
    if best_score >= 0.15:
        return best_type

    # Low confidence → try GPT if key is available
    return await _classify_with_llm(text, title)


async def _classify_with_llm(text: str, title: str = "") -> str:
    """Fallback GPT classification for ambiguous documents."""
    if not settings.openai_api_key:
        # No key — use rule-based hints as last resort
        return _simple_hint(text) or "unknown"
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    sample = (title + "\n\n" + text)[:2000]
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a document classifier. Classify the document into exactly ONE of: "
                    "research_paper, news_article, blog_post, legal_document, unknown. "
                    "Respond with ONLY the label, nothing else."
                ),
            },
            {"role": "user", "content": sample},
        ],
        temperature=0,
        max_tokens=10,
    )
    label = resp.choices[0].message.content.strip().lower()
    return label if label in DOC_TYPES else "unknown"


def _simple_hint(text: str) -> str | None:
    """Ultra-fast last-resort heuristics."""
    t = text.lower()
    if "abstract" in t and "introduction" in t:
        return "research_paper"
    if re.search(r"\bwhereas\b|\bhereinafter\b|\bpursuant to\b", t):
        return "legal_document"
    if re.search(r"\bby [A-Z][a-z]+ [A-Z][a-z]+\b", text):
        return "news_article"
    return None
