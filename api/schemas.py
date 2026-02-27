from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
from db.models import CredibilityScore, Claim, Conflict, SummarySection


# ─── Request schemas ────────────────────────────────────────────────────────

class DocumentInput(BaseModel):
    text: str = Field(..., min_length=50, description="Raw document text or paste")
    title: Optional[str] = None
    source_url: Optional[str] = None
    doc_type: Optional[Literal["research_paper", "news_article", "blog_post", "legal_document", "unknown"]] = None
    metadata: dict = Field(default_factory=dict)


class SummarizeRequest(BaseModel):
    documents: list[DocumentInput] = Field(..., min_length=1, description="One or more documents")
    summarizer_backend: Literal["rag", "bart"] = "rag"
    conflict_strategy: Literal["auto", "weighted_vote", "majority_vote", "highest_credibility_wins", "conservative"] = "auto"
    summary_depth: Literal["brief", "standard", "detailed", "deep_research"] = "standard"


# ─── Response schemas ────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str = ""


class DocumentSummary(BaseModel):
    doc_id: str
    doc_type: str
    title: Optional[str]
    source_url: Optional[str]
    credibility_score: Optional[CredibilityScore]


class SummaryReportResponse(BaseModel):
    report_id: str
    job_id: str
    status: str
    documents: list[DocumentSummary] = []
    resolved_claims: list[Claim] = []
    conflicts: list[Conflict] = []
    sections: list[SummarySection] = []
    full_summary: str = ""
    doc_types_present: list[str] = []
    summary_depth: str = "standard"
    report_title: Optional[str] = None
    is_saved: bool = False
    created_at: Optional[str] = None


class UpdateReportRequest(BaseModel):
    report_title: Optional[str] = None
    is_saved: Optional[bool] = None


class QARequest(BaseModel):
    report_id: str
    question: str = Field(..., min_length=5)


class QAResponse(BaseModel):
    question: str
    answer: str
    citations: list[str] = []


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    error: Optional[str] = None
    report_id: Optional[str] = None
    created_at: str
    updated_at: str


class DocTypeInfo(BaseModel):
    doc_type: str
    credibility_signals: list[dict]
    default_strategy: str
