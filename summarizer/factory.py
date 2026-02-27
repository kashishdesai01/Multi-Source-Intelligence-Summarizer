from config import settings
from summarizer.base import BaseSummarizer


def get_summarizer() -> BaseSummarizer:
    if settings.summarizer_backend == "rag" and settings.openai_api_key:
        from summarizer.rag_summarizer import RAGSummarizer
        return RAGSummarizer()
    from summarizer.bart_summarizer import BartSummarizer
    return BartSummarizer()
