"""Tests for credibility scorers."""
import pytest
from unittest.mock import patch, AsyncMock
from db.models import DocumentRecord


RESEARCH_TEXT = """
Abstract: We present a novel approach to protein folding. Introduction: Understanding
protein structure is critical. Methods: We used AlphaFold variants with custom training data.
Results: Our model achieves 92% accuracy on benchmark sets. Conclusion: This demonstrates
significant improvement over prior state of the art. References: [1] Jumper et al. 2021.
"""

NEWS_TEXT = """
By Jane Doe, Senior Reporter. According to the White House spokesperson, the President
signed the executive order this morning. "This will benefit millions of Americans," 
the spokesperson said. Multiple officials confirmed the announcement, which was expected
following last week's congressional vote. Published: 2024-06-01.
"""


@pytest.mark.asyncio
async def test_research_credibility_no_meta():
    """Research agent without Semantic Scholar connection should still return a score."""
    from agents.research_agent import ResearchAgent
    agent = ResearchAgent()

    doc = DocumentRecord(
        doc_id="test-research-001",
        raw_text=RESEARCH_TEXT,
        title="Novel Protein Folding Approach",
        doc_type="research_paper",
    )

    with patch("agents.research_agent._fetch_paper_meta", new_callable=AsyncMock, return_value={}):
        score = await agent.score_credibility(doc)

    assert 0.0 <= score.overall <= 1.0
    assert "source_authority" in score.breakdown
    assert "recency" in score.breakdown


@pytest.mark.asyncio
async def test_research_credibility_with_meta():
    """Score should improve with good Semantic Scholar metadata."""
    from agents.research_agent import ResearchAgent
    agent = ResearchAgent()

    doc = DocumentRecord(
        doc_id="test-research-002",
        raw_text=RESEARCH_TEXT,
        title="AlphaFold",
        doc_type="research_paper",
        source_url="https://nature.com/article"
    )

    mock_meta = {
        "citationCount": 15000,
        "year": 2022,
        "venue": "Nature",
        "authors": [{"hIndex": 55}],
        "isOpenAccess": True,
        "publicationTypes": ["JournalArticle"],
    }

    with patch("agents.research_agent._fetch_paper_meta", new_callable=AsyncMock, return_value=mock_meta):
        score = await agent.score_credibility(doc)

    assert score.overall >= 0.85, f"Expected high score for Nature+15k citations, got {score.overall}"


@pytest.mark.asyncio
async def test_news_credibility_high_trust_source():
    from agents.news_agent import NewsAgent
    from datetime import datetime, timezone, timedelta
    agent = NewsAgent()
    recent_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    doc = DocumentRecord(
        doc_id="test-news-001",
        raw_text=NEWS_TEXT,
        source_url="https://reuters.com/article/xyz",
        doc_type="news_article",
        metadata={"published_date": recent_date},
    )
    score = await agent.score_credibility(doc)
    assert score.overall >= 0.70, f"Reuters should score high, got {score.overall}"
    assert score.breakdown["source_trust"] >= 0.85


@pytest.mark.asyncio
async def test_news_credibility_low_trust_source():
    from agents.news_agent import NewsAgent
    agent = NewsAgent()
    doc = DocumentRecord(
        doc_id="test-news-002",
        raw_text="Some article without byline or citations.",
        source_url="https://infowars.com/story",
        doc_type="news_article",
        metadata={},
    )
    score = await agent.score_credibility(doc)
    assert score.overall <= 0.35, f"Infowars should score low, got {score.overall}"
