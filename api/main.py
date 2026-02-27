from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup
from db.connection import init_db
from db.models import DocumentRecord, SummaryJob, SummaryReport
from api.schemas import (
    SummarizeRequest, JobResponse, JobStatusResponse,
    SummaryReportResponse, DocumentSummary, DocTypeInfo,
    UpdateReportRequest,
)
from conflict.strategies import DEFAULT_STRATEGY_BY_TYPE
from agents.orchestrator import Orchestrator
from api import qa_router as _qa_module


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="MultiDoc Summarizer API",
    description="Agentic multi-document summarization with type-specific credibility routing.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()

app.include_router(_qa_module.router)


# ─── Background task runner ───────────────────────────────────────────────────

async def _run_job(job_id: str, doc_ids: list[str]):
    job = await SummaryJob.find_one(SummaryJob.job_id == job_id)
    docs = []
    for did in doc_ids:
        doc = await DocumentRecord.find_one(DocumentRecord.doc_id == did)
        if doc:
            docs.append(doc)
    if job and docs:
        await orchestrator.run(job, docs)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/fetch-url")
async def fetch_url(url: str = Query(..., description="URL to fetch article content from")):
    """Fetch and extract article text from a URL using BeautifulSoup."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; MultiDocSummarizer/1.0)"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=422, detail=f"URL returned HTTP {e.response.status_code}: {url}")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")

    try:
        soup = BeautifulSoup(html, "lxml")

        # Extract title
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"]
        elif soup.find("title"):
            title = soup.find("title").get_text(strip=True)
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # Remove boilerplate tags
        for tag in soup(["script", "style", "nav", "footer", "header",
                        "aside", "form", "noscript", "iframe"]):
            tag.decompose()

        # Try article tag first, then main, then body
        content_root = soup.find("article") or soup.find("main") or soup.find("body") or soup
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in content_root.find_all(["p", "li"])
            if len(p.get_text(strip=True)) > 40
        ]
        text = "\n\n".join(paragraphs)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse page content: {e}")

    if len(text) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the URL. Try pasting the text directly."
        )

    return {"title": title, "text": text, "source_url": url}


@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """Extract text from an uploaded PDF or DOCX file."""
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in ("pdf", "docx", "doc"):
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '.{ext}'. Please upload a PDF or DOCX file."
        )

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:  # 50 MB cap
        raise HTTPException(status_code=422, detail="File too large. Maximum size is 50 MB.")

    title = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip()
    text = ""

    try:
        if ext == "pdf":
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contents))
            pages = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.append(page_text)
            text = "\n\n".join(pages)

            # Try to get title from PDF metadata
            meta = reader.metadata
            if meta and meta.title:
                title = meta.title.strip() or title

        elif ext in ("docx", "doc"):
            import io
            from docx import Document
            doc = Document(io.BytesIO(contents))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            text = "\n\n".join(paragraphs)

            # First non-empty paragraph is often the title
            if paragraphs and not title:
                title = paragraphs[0][:120]

    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse file: {e}")

    text = text.strip()
    if len(text) < 50:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough text from the file. The file may be scanned/image-based or empty."
        )

    return {"title": title, "text": text, "source_url": None, "word_count": len(text.split())}



@app.get("/doc-types", response_model=list[DocTypeInfo])
async def get_doc_types():
    return [
        DocTypeInfo(
            doc_type="research_paper",
            credibility_signals=[
                {"signal": "Journal Impact Factor", "weight": "35%"},
                {"signal": "Citation count (log-scaled)", "weight": "25%"},
                {"signal": "Recency (5yr half-life)", "weight": "20%"},
                {"signal": "Author h-index", "weight": "15%"},
                {"signal": "Peer-review status", "weight": "5%"},
            ],
            default_strategy=DEFAULT_STRATEGY_BY_TYPE["research_paper"],
        ),
        DocTypeInfo(
            doc_type="news_article",
            credibility_signals=[
                {"signal": "Source trust score (Media Bias DB)", "weight": "40%"},
                {"signal": "Recency", "weight": "20%"},
                {"signal": "Primary source citations", "weight": "15%"},
                {"signal": "Cross-source corroboration", "weight": "15%"},
                {"signal": "Author byline", "weight": "10%"},
            ],
            default_strategy=DEFAULT_STRATEGY_BY_TYPE["news_article"],
        ),
        DocTypeInfo(
            doc_type="blog_post",
            credibility_signals=[
                {"signal": "Domain authority", "weight": "30%"},
                {"signal": "Author credentials (LLM)", "weight": "25%"},
                {"signal": "External references cited", "weight": "25%"},
                {"signal": "Recency", "weight": "20%"},
            ],
            default_strategy=DEFAULT_STRATEGY_BY_TYPE["blog_post"],
        ),
        DocTypeInfo(
            doc_type="legal_document",
            credibility_signals=[
                {"signal": "Official/gov source", "weight": "35%"},
                {"signal": "Jurisdiction authority", "weight": "30%"},
                {"signal": "Statute citations", "weight": "20%"},
                {"signal": "Recency", "weight": "15%"},
            ],
            default_strategy=DEFAULT_STRATEGY_BY_TYPE["legal_document"],
        ),
    ]


@app.post("/summarize", response_model=JobResponse, status_code=202)
async def submit_summarize(request: SummarizeRequest, background_tasks: BackgroundTasks):
    """Submit documents for summarization. Returns a job_id to poll status."""
    # Persist raw documents
    doc_records = []
    _MAX_RAW_CHARS = 400_000  # ~100k words, safely under MongoDB's 16 MB BSON limit
    for inp in request.documents:
        stored_text = inp.text if len(inp.text) <= _MAX_RAW_CHARS else inp.text[:_MAX_RAW_CHARS] + "\n\n[... truncated for storage ...]"
        rec = DocumentRecord(
            raw_text=stored_text,
            title=inp.title,
            source_url=inp.source_url,
            doc_type=inp.doc_type or "unknown",
            metadata=inp.metadata,
        )
        await rec.insert()
        doc_records.append(rec)


    job = SummaryJob(
        doc_ids=[d.doc_id for d in doc_records],
        summarizer_backend=request.summarizer_backend,
        conflict_strategy=request.conflict_strategy,
        summary_depth=request.summary_depth,
    )
    await job.insert()

    background_tasks.add_task(_run_job, job.job_id, [d.doc_id for d in doc_records])

    return JobResponse(
        job_id=job.job_id,
        status="pending",
        message="Job queued. Poll /jobs/{job_id} for status.",
    )


@app.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    job = await SummaryJob.find_one(SummaryJob.job_id == job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        error=job.error,
        report_id=job.report_id,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


@app.get("/reports", response_model=list[SummaryReportResponse])
async def list_reports(
    skip: int = 0,
    limit: int = 20,
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    has_conflicts: Optional[bool] = Query(None, description="Filter by presence of conflicts"),
    is_saved: Optional[bool] = Query(None, description="Filter by saved status"),
    date_from: Optional[str] = Query(None, description="ISO date string, start of date range"),
    date_to: Optional[str] = Query(None, description="ISO date string, end of date range"),
    search: Optional[str] = Query(None, description="Full-text search in summary"),
):
    query = SummaryReport.find()

    if doc_type:
        query = query.find(SummaryReport.doc_types_present == doc_type)
    if has_conflicts is not None:
        if has_conflicts:
            # Reports that have at least one conflict
            query = query.find({"conflicts": {"$exists": True, "$not": {"$size": 0}}})
        else:
            query = query.find({"$or": [{"conflicts": {"$size": 0}}, {"conflicts": {"$exists": False}}]})
    if is_saved is not None:
        query = query.find(SummaryReport.is_saved == is_saved)
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.find(SummaryReport.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.find(SummaryReport.created_at <= dt_to)
        except ValueError:
            pass
    if search:
        query = query.find({"full_summary": {"$regex": search, "$options": "i"}})

    reports = await query.skip(skip).limit(limit).to_list()
    return [_format_report(r, []) for r in reports]


@app.get("/reports/{report_id}", response_model=SummaryReportResponse)
async def get_report(report_id: str):
    report = await SummaryReport.find_one(SummaryReport.report_id == report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    docs = []
    for did in report.doc_ids:
        doc = await DocumentRecord.find_one(DocumentRecord.doc_id == did)
        if doc:
            docs.append(doc)
    return _format_report(report, docs)


@app.patch("/reports/{report_id}", response_model=SummaryReportResponse)
async def update_report(report_id: str, body: UpdateReportRequest):
    """Update a report's title or saved status."""
    report = await SummaryReport.find_one(SummaryReport.report_id == report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if body.report_title is not None:
        report.report_title = body.report_title
    if body.is_saved is not None:
        report.is_saved = body.is_saved
    await report.save()
    docs = []
    for did in report.doc_ids:
        doc = await DocumentRecord.find_one(DocumentRecord.doc_id == did)
        if doc:
            docs.append(doc)
    return _format_report(report, docs)


@app.delete("/reports/{report_id}", status_code=204)
async def delete_report(report_id: str):
    report = await SummaryReport.find_one(SummaryReport.report_id == report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await report.delete()


def _format_report(report: SummaryReport, docs: list[DocumentRecord]) -> SummaryReportResponse:
    return SummaryReportResponse(
        report_id=report.report_id,
        job_id=report.job_id,
        status="done",
        documents=[
            DocumentSummary(
                doc_id=d.doc_id,
                doc_type=d.doc_type,
                title=d.title,
                source_url=d.source_url,
                credibility_score=d.credibility_score,
            )
            for d in docs
        ],
        resolved_claims=report.resolved_claims,
        conflicts=report.conflicts,
        sections=report.sections,
        full_summary=report.full_summary,
        doc_types_present=report.doc_types_present,
        created_at=report.created_at.isoformat(),
        summary_depth=getattr(report, "summary_depth", "standard"),
        report_title=getattr(report, "report_title", None),
        is_saved=getattr(report, "is_saved", False),
    )
