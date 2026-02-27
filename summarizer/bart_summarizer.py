"""BART-based offline summarizer using facebook/bart-large-cnn."""
from __future__ import annotations
from transformers import pipeline, Pipeline
from db.models import Claim, Conflict, SummarySection
from summarizer.base import BaseSummarizer
from config import settings

_pipe: Pipeline | None = None


def _get_pipe() -> Pipeline:
    global _pipe
    if _pipe is None:
        _pipe = pipeline("summarization", model=settings.bart_model, device=-1)
    return _pipe


class BartSummarizer(BaseSummarizer):

    def _build_input_text(self, resolved_claims: list[Claim], conflicts: list[Conflict]) -> str:
        parts = ["KEY CLAIMS:"]
        parts += [f"- {c.text}" for c in resolved_claims[:30]]
        if conflicts:
            parts.append("\nCONFLICTS:")
            for conf in conflicts[:5]:
                parts.append(f"- CONFLICT: {conf.topic}")
                if conf.resolution:
                    parts.append(f"  RESOLUTION: {conf.resolution}")
                else:
                    parts.append("  STATUS: Unresolved — multiple sources disagree.")
        return "\n".join(parts)

    async def summarize(
        self,
        resolved_claims: list[Claim],
        conflicts: list[Conflict],
        doc_types: list[str],
    ) -> tuple[str, list[SummarySection]]:
        input_text = self._build_input_text(resolved_claims, conflicts)
        pipe = _get_pipe()

        # Chunk if too long
        max_input = 1024
        chunks = [input_text[i: i + max_input] for i in range(0, len(input_text), max_input)]
        summaries = []
        for chunk in chunks[:3]:
            result = pipe(
                chunk,
                max_length=200,
                min_length=60,
                do_sample=False,
                truncation=True,
            )
            summaries.append(result[0]["summary_text"])

        full_summary = " ".join(summaries)

        conflict_text = ""
        if conflicts:
            lines = []
            for c in conflicts:
                if c.status == "resolved":
                    lines.append(f"• {c.topic} — resolved in favour of: {c.resolution}")
                else:
                    lines.append(f"• {c.topic} — UNRESOLVED (sources disagree, reader discretion advised)")
            conflict_text = "\n".join(lines)

        sections = [
            SummarySection(title="Key Findings", content=full_summary),
            SummarySection(
                title="Conflicts Detected",
                content=conflict_text if conflict_text else "No significant conflicts found.",
            ),
        ]

        if "research_paper" in doc_types:
            method_text = " ".join(
                c.text for c in resolved_claims if any(
                    w in c.text.lower() for w in ["method", "approach", "experiment", "study", "analysis"]
                )
            )[:1000]
            sections.append(SummarySection(title="Methodology", content=method_text or "See original papers for methodology."))

        sections.append(SummarySection(title="Conclusion", content=full_summary.split(".")[-2].strip() + "."))

        return full_summary, sections
