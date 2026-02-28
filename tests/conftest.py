import pytest
import asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient
from db.models import DocumentRecord, SummaryJob, SummaryReport


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True, scope="session")
async def init_test_db():
    """Initialize a mock MongoDB database for local testing."""
    client = AsyncMongoMockClient()
    await init_beanie(
        database=client["multidoc_test"],
        document_models=[DocumentRecord, SummaryJob, SummaryReport],
    )
    yield
    # Cleanup unnecessary for mock client
