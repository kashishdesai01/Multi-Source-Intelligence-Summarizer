from abc import ABC, abstractmethod
from db.models import Claim, Conflict, SummarySection


class BaseSummarizer(ABC):
    """Abstract summarizer interface."""

    @abstractmethod
    async def summarize(
        self,
        resolved_claims: list[Claim],
        conflicts: list[Conflict],
        doc_types: list[str],
    ) -> tuple[str, list[SummarySection]]:
        """
        Returns:
            full_summary: full plain-text summary
            sections: structured section breakdown
        """
