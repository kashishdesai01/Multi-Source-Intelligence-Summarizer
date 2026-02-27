from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from config import settings
from db.models import DocumentRecord, SummaryJob, SummaryReport, DomainTrust


async def init_db() -> None:
    """Initialise MongoDB connection and Beanie ODM."""
    client = AsyncIOMotorClient(settings.mongodb_uri)
    database = client[settings.mongodb_db_name]
    await init_beanie(
        database=database,
        document_models=[DocumentRecord, SummaryJob, SummaryReport, DomainTrust],
    )
