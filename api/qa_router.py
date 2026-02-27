"""
Q&A Router — allows users to ask freeform questions about documents in a report.
Uses the document text as context and OpenAI to generate grounded answers.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from db.models import SummaryReport, DocumentRecord
from api.schemas import QARequest, QAResponse
from config import settings

router = APIRouter()


@router.post("/qa", response_model=QAResponse)
async def ask_question(req: QARequest) -> QAResponse:
    """Answer a question about a report's documents using RAG context."""
    # Fetch report
    report = await SummaryReport.find_one(SummaryReport.report_id == req.report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Fetch associated documents
    docs = []
    for did in report.doc_ids:
        doc = await DocumentRecord.find_one(DocumentRecord.doc_id == did)
        if doc:
            docs.append(doc)

    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this report")

    # Build context from document text (prefer condensed text if available)
    doc_contexts = []
    for i, doc in enumerate(docs, 1):
        text = doc.metadata.get("condensed_text") or doc.raw_text
        title = doc.title or f"Document {i}"
        # Truncate per doc to fit context window (first 6000 chars each)
        truncated = text[:6000]
        doc_contexts.append(f"[Document {i}: {title}]\n{truncated}")

    full_context = "\n\n---\n\n".join(doc_contexts)

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="Q&A requires an OpenAI API key. Please configure OPENAI_API_KEY."
        )

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    system_prompt = (
        "You are a precise document analysis assistant. "
        "You will be given one or more document excerpts followed by a user question. "
        "Answer the question accurately and concisely based ONLY on the provided documents. "
        "If the answer is not found in the documents, say so clearly. "
        "When citing information, reference which document it came from (e.g. 'According to Document 1...'). "
        "Format citations naturally within your answer."
    )

    user_msg = (
        f"DOCUMENTS:\n\n{full_context[:12000]}\n\n"
        f"QUESTION: {req.question}"
    )

    try:
        resp = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=1000,
        )
        answer = resp.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate answer: {e}")

    # Extract document titles as citation hints
    citations = [doc.title or f"Document {i+1}" for i, doc in enumerate(docs)]

    return QAResponse(
        question=req.question,
        answer=answer,
        citations=citations,
    )
