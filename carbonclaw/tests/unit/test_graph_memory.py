import pytest
import json
from pathlib import Path
from carbonclaw.memory.graph import KnowledgeGraphMemory

@pytest.mark.asyncio
async def test_graph_memory_analysis(tmp_path):
    db_path = tmp_path / "graph.json"
    memory = KnowledgeGraphMemory(db_path=db_path)
    
    # Create a dummy python file
    test_file = tmp_path / "dummy.py"
    test_file.write_text("import os\ndef test_func(): pass\nclass TestClass: pass")
    
    memory.analyze_file(test_file)
    
    assert str(test_file) in memory.graph
    data = memory.graph[str(test_file)]
    assert "test_func" in data["functions"]
    assert "TestClass" in data["classes"]
    assert "os" in data["imports"]
    
    # Test retrieval
    results = await memory.retrieve("test_func", namespace="graph")
    assert len(results) > 0
    assert "dummy.py" in results[0].content
