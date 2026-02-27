from abc import ABC, abstractmethod
from db.models import DocumentRecord, CredibilityScore, Claim


class DocumentAgent(ABC):
    """Abstract base for all document-type sub-agents."""

    doc_type: str = "unknown"

    @abstractmethod
    async def score_credibility(self, doc: DocumentRecord) -> CredibilityScore:
        """Return a 0–1 credibility score with per-signal breakdown."""

    @abstractmethod
    async def extract_claims(self, doc: DocumentRecord) -> list[Claim]:
        """Extract atomic factual claims from the document text."""

    async def process(self, doc: DocumentRecord) -> DocumentRecord:
        """Score + extract claims and mutate the doc record in place."""
        doc.credibility_score = await self.score_credibility(doc)
        doc.claims = await self.extract_claims(doc)
        return doc
