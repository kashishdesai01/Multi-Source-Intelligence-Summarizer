"""Tests for document classifier."""
import pytest
from unittest.mock import patch, AsyncMock


RESEARCH_TEXT = """
Abstract: This study investigates the effects of transformer architectures on natural
language processing tasks. Introduction: Recent advances in deep learning have led to
significant improvements in text classification. Methods: We evaluated BERT, GPT, and
T5 on a suite of benchmark datasets. Results show a 15% improvement over baselines.
References: [1] Vaswani et al., 2017. Attention is all you need.
"""

NEWS_TEXT = """
By John Smith, Staff Writer | Reuters
The Federal Reserve raised interest rates by 25 basis points on Wednesday, according to
officials who spoke to reporters after the meeting. Fed Chair Jerome Powell said the
decision was unanimous, citing persistent inflation. Market indices fell sharply following
the announcement.
"""

BLOG_TEXT = """
I've been building web apps for 10 years and I want to share my thoughts on the latest
JavaScript frameworks. In my opinion, React still wins for large teams but SvelteKit 
is catching up fast. Here are https://example.com/svelte my favorite resources for
learning https://github.com/example modern frontend development.
"""

LEGAL_TEXT = """
WHEREAS, the Party of the First Part agrees to provide services pursuant to Section 4
of the Commercial Code, 15 U.S.C. § 1051, hereinafter referred to as the Agreement.
The Party of the Second Part shall comply with all applicable federal regulations.
Article 3: Termination. Either party may terminate this agreement with 30 days notice.
"""


@pytest.mark.asyncio
async def test_classify_research_paper():
    from agents.classifier import _rule_based_hints
    result = _rule_based_hints(RESEARCH_TEXT)
    assert result == "research_paper"


@pytest.mark.asyncio
async def test_classify_legal_document():
    from agents.classifier import _rule_based_hints
    result = _rule_based_hints(LEGAL_TEXT)
    assert result == "legal_document"


@pytest.mark.asyncio
async def test_classify_with_model_research():
    """Integration test: BART zero-shot on research text."""
    from agents.classifier import classify_document
    result = await classify_document(RESEARCH_TEXT, "Transformer Study")
    assert result in ("research_paper", "unknown"), f"Unexpected: {result}"


@pytest.mark.asyncio
async def test_classify_with_model_news():
    from agents.classifier import classify_document
    result = await classify_document(NEWS_TEXT, "Fed Rate Hike")
    assert result in ("news_article", "unknown"), f"Unexpected: {result}"


@pytest.mark.asyncio
async def test_classify_blog():
    from agents.classifier import classify_document
    result = await classify_document(BLOG_TEXT, "My thoughts on JS")
    assert result in ("blog_post", "unknown"), f"Unexpected: {result}"
