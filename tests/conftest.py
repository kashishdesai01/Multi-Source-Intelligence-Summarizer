import pytest
import asyncio
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from db.models import DocumentRecord, SummaryJob, SummaryReport


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="session")
async def init_test_db():
    """Initialize an in-memory-style test MongoDB database."""
    client = AsyncIOMotorClient("mongodb://localhost:27017/multidoc_test")
    await init_beanie(
        database=client["multidoc_test"],
        document_models=[DocumentRecord, SummaryJob, SummaryReport],
    )
    yield
    # Cleanup test collections
    await DocumentRecord.find_all().delete()
    await SummaryJob.find_all().delete()
    await SummaryReport.find_all().delete()
