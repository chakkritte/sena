import pytest
from unittest.mock import AsyncMock, MagicMock
from carbonclaw.memory.hybrid import HybridMemory
from carbonclaw.core.models import MemoryEntry

@pytest.mark.asyncio
async def test_hybrid_memory_store_and_retrieve():
    primary = AsyncMock()
    secondary = AsyncMock()
    
    primary.store.return_value = "p1"
    primary.retrieve.return_value = [MemoryEntry(content="hello world", namespace="default")]
    secondary.retrieve.return_value = [MemoryEntry(content="semantic match", namespace="default")]
    
    hybrid = HybridMemory(primary, secondary)
    
    # Test Store
    await hybrid.store("test content")
    assert primary.store.called
    assert secondary.store.called
    
    # Test Retrieve (RRF)
    results = await hybrid.retrieve("query")
    assert len(results) >= 1
    assert primary.retrieve.called
    assert secondary.retrieve.called
