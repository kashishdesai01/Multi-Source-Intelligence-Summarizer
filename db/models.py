from beanie import Document, Indexed
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from datetime import datetime, timezone
import uuid


# ─── Sub-models ────────────────────────────────────────────────────────────────

class CredibilityScore(BaseModel):
    overall: float = Field(..., ge=0.0, le=1.0, description="0–1 composite score")
    breakdown: dict[str, float] = Field(default_factory=dict)
    explanations: dict[str, str] = Field(default_factory=dict, description="Human-readable explanation per breakdown key")
    signals: dict[str, Any] = Field(default_factory=dict, description="Raw signal values")


class Claim(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    source_doc_id: str
    confidence: float = 1.0


class Conflict(BaseModel):
    claims: list[Claim]
    topic: str
    resolution: Optional[str] = None          # winning claim text
    status: Literal["resolved", "unresolved"] = "unresolved"
    confidence: float = 0.0


class SummarySection(BaseModel):
    title: str
    content: str


# ─── Top-level Beanie Documents ────────────────────────────────────────────────

DocType = Literal["research_paper", "news_article", "blog_post", "legal_document", "unknown"]
JobStatus = Literal["pending", "running", "done", "failed"]


class DocumentRecord(Document):
    """Stores a single uploaded/submitted document."""

    doc_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    doc_type: DocType = "unknown"
    title: Optional[str] = None
    source_url: Optional[str] = None
    raw_text: str
    credibility_score: Optional[CredibilityScore] = None
    claims: list[Claim] = Field(default_factory=list)
    # Type-specific metadata stored flexibly (journal, publisher, author, etc.)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "documents"


class SummaryJob(Document):
    """Tracks an async summarization job."""

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = "pending"
    doc_ids: list[str] = Field(default_factory=list)
    summarizer_backend: str = "rag"
    conflict_strategy: str = "weighted_vote"
    summary_depth: str = "standard"  # brief | standard | detailed | deep_research
    error: Optional[str] = None
    report_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "jobs"


class SummaryReport(Document):
    """Final output: resolved claims, conflict report, and summary."""

    report_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    doc_ids: list[str]
    resolved_claims: list[Claim] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    sections: list[SummarySection] = Field(default_factory=list)
    full_summary: str = ""
    doc_types_present: list[str] = Field(default_factory=list)
    summary_depth: str = "standard"  # brief | standard | detailed | deep_research
    report_title: Optional[str] = None
    is_saved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "reports"


class DomainTrust(Document):
    """Cached source authority scores, keyed by domain (e.g. 'bbc.com')."""

    domain: Indexed(str, unique=True)  # type: ignore[valid-type]
    score: float = Field(..., ge=0.0, le=1.0)
    method: str = "default"  # "static", "tld_pattern", "openpagerank", "llm", "default"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "domain_trust"

