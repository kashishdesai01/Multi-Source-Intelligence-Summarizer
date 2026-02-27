"""
utils/paper_chunker.py

Splits a research paper into logical sections (Abstract, Introduction, Methods,
Results, Discussion, Conclusion) using header detection. Falls back to fixed-size
chunking when sections can't be identified.

Designed for:
  - PDF-extracted plaintext (may have all-caps headers, numbered sections)
  - HTML-scraped academic articles (section tags or heading elements stripped to text)
  - Pasted plaintext from papers
"""
from __future__ import annotations
import re
from dataclasses import dataclass

# ── Section definitions ────────────────────────────────────────────────────────

# Ordered list of canonical sections with regex aliases
_SECTIONS: list[tuple[str, str]] = [
    # (canonical name, regex pattern)
    ("abstract",      r"\babstract\b"),
    ("introduction",  r"\b(introduction|background|overview)\b"),
    ("related_work",  r"\b(related\s+work|literature\s+review|prior\s+work|previous\s+work)\b"),
    ("methods",       r"\b(method(?:s|ology)?|approach|model|framework|experimental\s+setup|materials\s+and\s+methods)\b"),
    ("results",       r"\b(result(?:s)?|experiment(?:s)?|evaluation|findings|empirical)\b"),
    ("discussion",    r"\b(discussion|analysis|ablation|limitations?)\b"),
    ("conclusion",    r"\b(conclusion(?:s)?|summary|future\s+work|closing\s+remarks)\b"),
]

# How a section header looks in a paper:
# "3. METHODOLOGY"   "## Methods"   "RESULTS AND DISCUSSION"   "2.1 Related Work"
_HEADER_RE = re.compile(
    r"^(?:"
    r"#{1,4}\s+"                          # Markdown headings
    r"|(?:\d+\.?\s+){0,3}"               # Numbered: 1. / 1.2 / 2.3.1
    r")"
    r"([A-Z][A-Za-z\s&:,/\-]{2,60})"     # Header text (at least 3 chars)
    r"\s*$",
    re.MULTILINE,
)


@dataclass
class PaperSection:
    name: str        # canonical name (e.g. "methods")
    label: str       # as it appeared in the paper (e.g. "3. METHODOLOGY")
    text: str        # raw content of the section
    word_count: int


def _label_to_canonical(label: str) -> str:
    lower = label.lower().strip()
    for canonical, pattern in _SECTIONS:
        if re.search(pattern, lower):
            return canonical
    return "other"


def split_into_sections(text: str, min_section_words: int = 30) -> list[PaperSection]:
    """
    Split `text` into PaperSection objects.

    Returns a list ordered by appearance in the document. Sections shorter than
    `min_section_words` are merged into the previous section (often page headers /
    figure captions).
    """
    # Find all header positions
    headers: list[tuple[int, str]] = []  # (start_char, header_text)
    for m in _HEADER_RE.finditer(text):
        label = m.group(1).strip()
        # Filter out very short headings that are probably page numbers / figure labels
        if len(label.split()) < 2 and not re.search(r"abstract|introduction|conclusion|result|method", label, re.I):
            continue
        headers.append((m.start(), label))

    if not headers:
        # No sections detected — return whole doc as a single "body" section
        return [PaperSection(
            name="body",
            label="Full Text",
            text=text,
            word_count=len(text.split()),
        )]

    sections: list[PaperSection] = []

    # Text before the first header → preamble (title page, cover)
    if headers[0][0] > 0:
        preamble = text[:headers[0][0]].strip()
        if preamble:
            sections.append(PaperSection(
                name="preamble",
                label="Preamble",
                text=preamble,
                word_count=len(preamble.split()),
            ))

    for i, (start, label) in enumerate(headers):
        end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        section_text = text[start:end].strip()
        # Remove the header line itself from the body text
        section_body = "\n".join(section_text.split("\n")[1:]).strip()

        wc = len(section_body.split())
        canonical = _label_to_canonical(label)

        if wc < min_section_words and sections:
            # Merge tiny section into the previous one
            sections[-1].text += "\n\n" + section_body
            sections[-1].word_count += wc
        else:
            sections.append(PaperSection(
                name=canonical,
                label=label,
                text=section_body,
                word_count=wc,
            ))

    return sections


# ── Fallback fixed-size chunker ───────────────────────────────────────────────

def fixed_chunks(text: str, chunk_words: int = 300, overlap_words: int = 50) -> list[str]:
    """
    Simple sliding-window word chunker used when no sections are detected
    or as the primary chunker for the RAG FAISS index.
    """
    words = text.split()
    chunks = []
    step = max(chunk_words - overlap_words, 1)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_words])
        if chunk:
            chunks.append(chunk)
    return chunks


# ── Token-budget truncation ───────────────────────────────────────────────────

def truncate_to_tokens(text: str, max_tokens: int = 3000) -> str:
    """
    Rough truncation (1 token ≈ 0.75 words). Used to cap individual section
    text before sending to GPT.
    """
    max_words = int(max_tokens * 0.75)
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "\n\n[... truncated for length ...]"
