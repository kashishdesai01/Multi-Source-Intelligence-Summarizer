"""
RAG Summarizer: OpenAI embeddings + FAISS retrieval + GPT-4o-mini generation.
Uses OpenAI text-embedding-3-small (no local model download needed).
Falls back to simple keyword retrieval if no API key.
Supports summary depth levels: brief | standard | detailed | deep_research.
"""
from __future__ import annotations
import re
import numpy as np
import faiss
from openai import AsyncOpenAI
from db.models import Claim, Conflict, SummarySection, DocumentRecord
from summarizer.base import BaseSummarizer
from config import settings


def _chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i: i + chunk_size])
        chunks.append(chunk)
        i += chunk_size - overlap
    return chunks


def _keyword_retrieve(chunks: list[str], query: str, top_k: int = 5) -> list[str]:
    """Simple keyword-overlap retrieval when no embeddings available."""
    query_words = set(re.findall(r"\w+", query.lower()))
    scored = []
    for chunk in chunks:
        chunk_words = set(re.findall(r"\w+", chunk.lower()))
        overlap = len(query_words & chunk_words)
        scored.append((overlap, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


# ── Depth-specific prompt builders ────────────────────────────────────────────

def _build_system_prompt(doc_types: list[str], depth: str, single_doc: bool) -> str:
    has_research = "research_paper" in doc_types
    has_legal = "legal_document" in doc_types

    base_rules = (
        "\nRules:\n"
        "- Be objective and evidence-based.\n"
        "- Do not fabricate facts.\n"
        "- Use clear, professional language.\n"
        "- Output plain text with section headers preceded by ##.\n"
    )

    if depth == "brief":
        return (
            "You are an expert document summarizer. Produce a concise TL;DR summary. "
            "Include only the most critical 2–3 findings and the overall conclusion. "
            "Keep the entire response under 200 words. "
            "Use exactly two sections: ## Key Findings and ## Conclusion."
            + base_rules
        )

    if depth == "standard":
        if single_doc:
            sections = "1. Key Findings\n2. Analysis\n3. Conclusion\n"
            if has_research:
                sections = "1. Key Findings\n2. Methodology\n3. Analysis\n4. Conclusion\n"
            if has_legal:
                sections = "1. Key Provisions\n2. Obligations & Rights\n3. Summary\n"
        else:
            sections = "1. Key Findings\n2. Conflicts & Disagreements\n3. Conclusion\n"
            if has_research:
                sections += "4. Methodology (brief)\n"
        return (
            "You are an expert multi-document summarizer. "
            "Produce a structured analytical summary with these sections:\n"
            + sections + base_rules
        )

    if depth == "detailed":
        if single_doc:
            sections = "1. Key Findings\n2. Detailed Analysis\n3. Limitations & Caveats\n4. Implications\n5. Conclusion\n"
            if has_legal:
                sections += "6. Key Clauses & Obligations\n"
        else:
            sections = (
                "1. Key Findings\n2. Detailed Analysis\n"
                "3. Conflicts & Disagreements\n4. Limitations & Caveats\n"
                "5. Implications\n6. Conclusion\n"
            )
            if has_legal:
                sections += "7. Key Clauses & Obligations\n"
        return (
            "You are an expert multi-document analyst. "
            "Produce a thorough, detailed analytical report with these sections:\n"
            + sections
            + "Aim for comprehensive coverage — use 400–700 words total."
            + base_rules
        )

    if depth == "deep_research":
        conflict_section = "5. Cross-Paper Conflicts & Disagreements\n" if not single_doc else ""
        n = 6 if not single_doc else 5
        return (
            "You are an expert scientific research analyst. "
            "Produce a deep, structured research analysis report with these sections:\n"
            "1. Executive Summary\n"
            "2. Research Problem & Objectives\n"
            "3. Methodology & Experimental Design\n"
            "4. Key Results & Statistical Highlights\n"
            + conflict_section
            + f"{n}. Limitations & Threats to Validity\n"
            + f"{n+1}. Future Research Directions\n"
            + f"{n+2}. Conclusion\n\n"
            "Aim for rigorous academic depth — use 600–900 words. "
            "If only one document, still provide full depth based on its content."
            + base_rules
        )

    # Fallback to standard
    return _build_system_prompt(doc_types, "standard", single_doc)


class RAGSummarizer(BaseSummarizer):
    def __init__(self, docs: list[DocumentRecord] | None = None):
        self._docs = docs or []
        self._index: faiss.IndexFlatIP | None = None
        self._chunks: list[str] = []
        self._use_embeddings = bool(settings.openai_api_key)
        self._client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def build_index(self, docs: list[DocumentRecord]) -> None:
        self._docs = docs
        self._chunks = []
        for doc in docs:
            text_for_index = doc.metadata.get("condensed_text") or doc.raw_text
            self._chunks.extend(_chunk_text(text_for_index))

        if not self._chunks or not self._use_embeddings:
            return

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, self._build_faiss_index())
                    future.result(timeout=30)
            else:
                loop.run_until_complete(self._build_faiss_index())
        except Exception:
            self._index = None

    async def _build_faiss_index(self) -> None:
        """Build FAISS index using OpenAI embeddings (batched)."""
        if not self._client:
            return
        batch_size = 100
        all_embeddings = []
        for i in range(0, len(self._chunks), batch_size):
            batch = self._chunks[i: i + batch_size]
            resp = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=batch,
            )
            vecs = [e.embedding for e in resp.data]
            all_embeddings.extend(vecs)

        if not all_embeddings:
            return
        arr = np.array(all_embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / np.clip(norms, 1e-9, None)
        dim = arr.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(arr)

    async def _retrieve(self, query: str, top_k: int = 5) -> list[str]:
        if not self._chunks:
            return []
        if self._index is None or not self._use_embeddings:
            return _keyword_retrieve(self._chunks, query, top_k)
        try:
            resp = await self._client.embeddings.create(
                model="text-embedding-3-small",
                input=[query],
            )
            qvec = np.array(resp.data[0].embedding, dtype=np.float32)
            qvec = qvec / (np.linalg.norm(qvec) + 1e-9)
            qvec = qvec.reshape(1, -1)
            _, indices = self._index.search(qvec, min(top_k, len(self._chunks)))
            return [self._chunks[i] for i in indices[0] if i < len(self._chunks)]
        except Exception:
            return _keyword_retrieve(self._chunks, query, top_k)

    async def summarize(
        self,
        resolved_claims: list[Claim],
        conflicts: list[Conflict],
        doc_types: list[str],
        depth: str = "standard",
        single_doc: bool = False,
    ) -> tuple[str, list[SummarySection]]:
        if not self._client:
            claims_text = "\n".join(f"• {c.text}" for c in resolved_claims[:20])
            full_summary = f"## Key Findings\n{claims_text}\n\n## Conclusion\nSummary generated without LLM (no OpenAI API key configured)."
            return full_summary, _parse_sections(full_summary)

        query = " ".join(c.text for c in resolved_claims[:10])
        retrieved = await self._retrieve(query, top_k=settings.rag_top_k)
        context_block = "\n---\n".join(retrieved)

        max_claims = 10 if depth == "brief" else 30 if depth in ("detailed", "deep_research") else 20
        max_conflicts = 0 if depth == "brief" else 15 if depth in ("detailed", "deep_research") else 10
        max_tokens = 500 if depth == "brief" else 3000 if depth == "deep_research" else 2000

        claims_text = "\n".join(f"• {c.text}" for c in resolved_claims[:max_claims])
        conflict_text = ""
        if not single_doc and conflicts:
            for conf in conflicts[:max_conflicts]:
                if conf.status == "resolved":
                    conflict_text += f"\n[RESOLVED] {conf.topic}\n  → Winner: {conf.resolution}\n"
                else:
                    all_sides = "\n    ".join(f"- {c.text}" for c in conf.claims[:3])
                    conflict_text += f"\n[UNRESOLVED] {conf.topic}\n  Conflicting claims:\n    {all_sides}\n"

        user_msg = (
            f"RESOLVED CLAIMS:\n{claims_text}\n\n"
            + (f"CONFLICTS:\n{conflict_text or 'None detected.'}\n\n" if not single_doc else "")
            + f"RETRIEVED CONTEXT PASSAGES:\n{context_block}"
        )

        resp = await self._client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": _build_system_prompt(doc_types, depth, single_doc)},
                {"role": "user", "content": user_msg[:14000]},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
        )

        full_summary = resp.choices[0].message.content.strip()
        sections = _parse_sections(full_summary)
        return full_summary, sections


def _parse_sections(text: str) -> list[SummarySection]:
    """Parse ## Section headers from LLM output into SummarySection objects."""
    parts = re.split(r"^##\s*", text, flags=re.MULTILINE)
    sections = []
    for part in parts:
        if not part.strip():
            continue
        lines = part.strip().splitlines()
        title = lines[0].strip()
        content = "\n".join(lines[1:]).strip()
        if title:
            sections.append(SummarySection(title=title, content=content))
    if not sections:
        sections = [SummarySection(title="Summary", content=text)]
    return sections
