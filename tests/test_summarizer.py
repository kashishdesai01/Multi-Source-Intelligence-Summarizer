"""Tests for BART summarizer (no API key required)."""
import pytest
from db.models import Claim, Conflict


SAMPLE_CLAIMS = [
    Claim(text="Regular exercise reduces risk of cardiovascular disease.", source_doc_id="doc-1"),
    Claim(text="High-intensity interval training is more effective than steady-state cardio.", source_doc_id="doc-2"),
    Claim(text="30 minutes of moderate exercise daily significantly improves mental health.", source_doc_id="doc-1"),
]

SAMPLE_CONFLICT = Conflict(
    claims=[
        Claim(text="Coffee consumption increases heart disease risk.", source_doc_id="doc-1"),
        Claim(text="Moderate coffee consumption is linked to lower heart disease risk.", source_doc_id="doc-2"),
    ],
    topic="Coffee and heart disease",
    resolution="Moderate coffee consumption is linked to lower heart disease risk.",
    status="resolved",
    confidence=0.82,
)


@pytest.mark.asyncio
async def test_bart_summarizer_returns_nonempty():
    """BART summarizer should produce non-empty output without an API key."""
    from summarizer.bart_summarizer import BartSummarizer
    summarizer = BartSummarizer()
    full, sections = await summarizer.summarize(SAMPLE_CLAIMS, [SAMPLE_CONFLICT], ["research_paper"])
    assert isinstance(full, str)
    assert len(full) > 50, "Summary should be non-trivially long"
    assert len(sections) >= 2, "Should produce at least Key Findings and Conflicts sections"


@pytest.mark.asyncio
async def test_bart_summarizer_conflict_in_output():
    """Conflict information should appear in the Conflicts section."""
    from summarizer.bart_summarizer import BartSummarizer
    summarizer = BartSummarizer()
    _, sections = await summarizer.summarize(SAMPLE_CLAIMS, [SAMPLE_CONFLICT], ["news_article"])
    conflict_section = next((s for s in sections if "conflict" in s.title.lower()), None)
    assert conflict_section is not None
    assert len(conflict_section.content) > 10


@pytest.mark.asyncio
async def test_bart_summarizer_research_adds_methodology():
    from summarizer.bart_summarizer import BartSummarizer
    method_claim = Claim(
        text="We used a randomized controlled trial methodology with 500 participants over 12 months.",
        source_doc_id="doc-1"
    )
    summarizer = BartSummarizer()
    _, sections = await summarizer.summarize([method_claim], [], ["research_paper"])
    titles = [s.title for s in sections]
    assert "Methodology" in titles, f"Research docs should have Methodology section. Got: {titles}"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not __import__("os").environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set — skipping RAG test"
)
async def test_rag_summarizer_returns_sections():
    from db.models import DocumentRecord
    from summarizer.rag_summarizer import RAGSummarizer
    doc = DocumentRecord(
        doc_id="rag-test-doc",
        raw_text="Exercise improves mental health significantly. Studies show 30 minutes daily reduces anxiety.",
        doc_type="news_article",
    )
    summarizer = RAGSummarizer()
    summarizer.build_index([doc])
    full, sections = await summarizer.summarize(SAMPLE_CLAIMS, [], ["news_article"])
    assert len(full) > 50
    assert len(sections) >= 1
