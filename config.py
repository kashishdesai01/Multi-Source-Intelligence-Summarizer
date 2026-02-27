from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017/multidoc"
    mongodb_db_name: str = "multidoc"

    # Summarizer
    summarizer_backend: Literal["rag", "bart"] = "rag"
    bart_model: str = "facebook/bart-large-cnn"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_top_k: int = 5

    # External APIs (optional)
    newsapi_key: str = ""
    semantic_scholar_key: str = ""
    open_pagerank_key: str = ""  # https://www.domcop.com/openpagerank/


    # AWS
    aws_region: str = "us-east-1"


settings = Settings()
