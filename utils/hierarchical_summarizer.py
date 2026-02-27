"""
utils/hierarchical_summarizer.py

Summarizes a long research paper section-by-section, then combines the section
summaries into a condensed representation (~1,500–2,500 words) for downstream
RAG retrieval and claim extraction.

GPT budget per run (gpt-4o-mini, $0.15/M input):
    – Each section call:  ~600–1,500 tokens → ~$0.0001
    – Typical 7-section paper: ~$0.001 total
    – 3 papers: ~$0.003
"""
from __future__ import annotations
import asyncio
from utils.paper_chunker import split_into_sections, truncate_to_tokens, PaperSection


# Section-specific prompts tuned to extract the most useful information
_SECTION_PROMPTS: dict[str, str] = {
    "abstract": (
        "Summarize the key contributions and claims of this abstract in 3–5 bullet points. "
        "Focus on: what problem is solved, the approach, and the main result."
    ),
    "introduction": (
        "Extract: (1) The core problem being addressed. "
        "(2) Why existing approaches fall short. "
        "(3) This paper's proposed solution in one sentence."
    ),
    "related_work": (
        "List the 3–5 most closely related prior works mentioned and explain briefly how this "
        "paper differs from them."
    ),
    "methods": (
        "Describe the methodology step-by-step in plain English. "
        "Include: the model/algorithm used, key design choices, datasets, and any equations "
        "mentioned (describe in words). Tables of hyperparameters can be summarized as bullet points."
    ),
    "results": (
        "Extract all quantitative results as bullet points. "
        "Include: metric names, numbers, comparisons to baselines. "
        "Summarize tables as: 'Method X achieved Y score on Dataset Z.'"
    ),
    "discussion": (
        "What do the authors say about: (1) why their method works, "
        "(2) failure cases or limitations, (3) unexpected findings?"
    ),
    "conclusion": (
        "Summarize the conclusions and any stated future work directions in 3–5 bullet points."
    ),
    "other": (
        "Summarize the key points of this section in 3–5 bullet points."
    ),
    "preamble": (
        "Extract the paper title, authors, and any stated affiliation or journal name."
    ),
    "body": (
        "This is a full research paper without clear section headers. "
        "Extract: (1) the main research question, (2) methodology, (3) key results, "
        "(4) conclusions. Provide 6–8 bullet points covering all four areas."
    ),
}


async def _summarize_section(
    section: PaperSection,
    openai_client,
    model: str = "gpt-4o-mini",
    max_section_tokens: int = 2500,
) -> str:
    """Send a single section to GPT with a targeted prompt. Returns summary text."""
    prompt = _SECTION_PROMPTS.get(section.name, _SECTION_PROMPTS["other"])
    section_text = truncate_to_tokens(section.text, max_tokens=max_section_tokens)

    resp = await openai_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scientific research assistant. Be concise and precise. "
                    "Preserve key numbers, model names, and technical terms exactly."
                ),
            },
            {
                "role": "user",
                "content": f"SECTION: {section.label}\n\n{section_text}\n\nTask: {prompt}",
            },
        ],
        temperature=0,
        max_tokens=400,  # keep section summaries tight (~300 words each)
    )
    summary = resp.choices[0].message.content.strip()
    return f"## {section.label}\n\n{summary}"


async def hierarchical_summarize(
    raw_text: str,
    openai_client,
    model: str = "gpt-4o-mini",
    concurrency: int = 4,
) -> dict:
    """
    Split `raw_text` into sections, summarize each in parallel (up to `concurrency`
    concurrent calls), then return a dict with:

        condensed_text:  str  — section summaries joined (≈1,500–2,500 words)
        sections:        list — [{"name": ..., "label": ..., "word_count": ...}]
        was_hierarchical: bool — True if sections were detected
    """
    sections = split_into_sections(raw_text)
    was_hierarchical = not (len(sections) == 1 and sections[0].name in ("body", "preamble"))

    # Skip references section — usually just citation list, not useful for summarization
    sections_to_summarize = [s for s in sections if s.name not in ("references",) and s.word_count > 30]

    # Parallel summarization with concurrency cap
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_summarize(section: PaperSection) -> str:
        async with semaphore:
            return await _summarize_section(section, openai_client, model)

    summaries = await asyncio.gather(*[bounded_summarize(s) for s in sections_to_summarize])

    condensed = "\n\n---\n\n".join(summaries)

    return {
        "condensed_text": condensed,
        "sections": [
            {"name": s.name, "label": s.label, "word_count": s.word_count}
            for s in sections
        ],
        "was_hierarchical": was_hierarchical,
        "section_count": len(sections_to_summarize),
    }


def keyword_section_summary(raw_text: str) -> str:
    """
    Fallback when OpenAI is not available.
    Splits into sections and returns the first 200 words of each section joined.
    Much better than just taking raw_text[:4000].
    """
    sections = split_into_sections(raw_text)
    parts = []
    for s in sections:
        if s.name == "references":
            continue
        snippet = " ".join(s.text.split()[:200])
        parts.append(f"## {s.label}\n{snippet}")
    return "\n\n".join(parts)
