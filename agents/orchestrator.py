"""
Orchestrator Agent — the master agentic loop.
Coordinates: Classify → Sub-Agent Process → Conflict Resolution → Summarize → Persist.
Supports single-doc jobs (skips conflict resolution) and summary depth levels.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from db.models import DocumentRecord, SummaryJob, SummaryReport
from agents.classifier import classify_document
from conflict.resolver import resolve_conflicts
from summarizer.factory import get_summarizer
from summarizer.rag_summarizer import RAGSummarizer


def _get_agent_for_type(doc_type: str):
    if doc_type == "research_paper":
        from agents.research_agent import ResearchAgent
        return ResearchAgent()
    elif doc_type == "news_article":
        from agents.news_agent import NewsAgent
        return NewsAgent()
    elif doc_type == "blog_post":
        from agents.blog_agent import BlogAgent
        return BlogAgent()
    elif doc_type == "legal_document":
        from agents.legal_agent import LegalAgent
        return LegalAgent()
    else:
        from agents.news_agent import NewsAgent  # fallback
        return NewsAgent()


class Orchestrator:
    """
    Stateless orchestrator — runs the full pipeline for a SummaryJob.
    Can be called from a FastAPI background task.
    Supports single-doc jobs (skips conflict resolution) and summary depth levels.
    """

    async def run(self, job: SummaryJob, docs: list[DocumentRecord]) -> SummaryReport:
        # ── Step 1: Mark job running ─────────────────────────────────────────
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc)
        await job.save()

        try:
            # ── Step 2: Classify each document ───────────────────────────────
            classify_tasks = [
                classify_document(doc.raw_text, doc.title or "")
                for doc in docs
            ]
            doc_types = await asyncio.gather(*classify_tasks)

            for doc, dt in zip(docs, doc_types):
                doc.doc_type = dt  # type: ignore[assignment]

            # ── Step 3: Score credibility + extract claims (type-specific) ───
            process_tasks = []
            for doc in docs:
                agent = _get_agent_for_type(doc.doc_type)
                process_tasks.append(agent.process(doc))

            processed_docs: list[DocumentRecord] = list(await asyncio.gather(*process_tasks))

            # ── Cap raw_text before MongoDB save (16 MB BSON limit) ──────────
            _MAX_CHARS = 400_000  # ~100k words — safely under 16 MB
            for doc in processed_docs:
                condensed = doc.metadata.get("condensed_text")
                if condensed:
                    doc.raw_text = condensed
                elif len(doc.raw_text) > _MAX_CHARS:
                    doc.raw_text = doc.raw_text[:_MAX_CHARS] + "\n\n[... truncated for storage ...]"
                await doc.save()

            # ── Step 4: Conflict resolution (skipped for single-doc) ─────────
            is_single_doc = len(processed_docs) == 1
            if is_single_doc:
                resolved_claims = processed_docs[0].claims
                conflicts = []
            else:
                resolved_claims, conflicts = resolve_conflicts(
                    processed_docs,
                    strategy_override=job.conflict_strategy if job.conflict_strategy != "auto" else None,
                )

            # ── Step 5: Summarize ─────────────────────────────────────────────
            summary_depth = getattr(job, "summary_depth", "standard")
            summarizer = get_summarizer()
            if isinstance(summarizer, RAGSummarizer):
                summarizer.build_index(processed_docs)

            unique_types = list({d.doc_type for d in processed_docs})
            full_summary, sections = await summarizer.summarize(
                resolved_claims, conflicts, unique_types,
                depth=summary_depth,
                single_doc=is_single_doc,
            )

            # ── Step 6: Persist report ────────────────────────────────────────
            report = SummaryReport(
                job_id=str(job.id),
                doc_ids=[doc.doc_id for doc in processed_docs],
                resolved_claims=resolved_claims,
                conflicts=conflicts,
                sections=sections,
                full_summary=full_summary,
                doc_types_present=unique_types,
                summary_depth=summary_depth,
            )
            await report.insert()

            job.status = "done"
            job.report_id = report.report_id
            job.updated_at = datetime.now(timezone.utc)
            await job.save()

            return report

        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.updated_at = datetime.now(timezone.utc)
            await job.save()
            raise
