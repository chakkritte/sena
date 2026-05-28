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


@pytest.mark.asyncio
async def test_graph_memory_git_churn(tmp_path):
    from unittest.mock import MagicMock, patch
    db_path = tmp_path / "graph.json"
    memory = KnowledgeGraphMemory(db_path=db_path)
    
    # Create a dummy python file
    test_file = tmp_path / "dummy.py"
    test_file.write_text("import os\ndef test_func(): pass\nclass TestClass: pass")
    memory.analyze_file(test_file)

    # Mock subprocess.run for git commands
    with patch("subprocess.run") as mock_run:
        # Mock responses:
        mock_res1 = MagicMock()
        mock_res1.stdout = "hash1\nhash2\nhash3\nhash4\nhash5\n"
        
        mock_res2 = MagicMock()
        mock_res2.stdout = "Author One\nAuthor Two\nAuthor One\n"
        
        mock_res3 = MagicMock()
        mock_res3.stdout = "50\t10\tdummy.py\n20\t5\tdummy.py\n"
        
        mock_run.side_effect = [mock_res1, mock_res2, mock_res3]
        
        stats = memory.analyze_git_churn(test_file)
        
        assert stats["commits_count"] == 5
        assert stats["author_count"] == 2
        assert stats["lines_added"] == 70
        assert stats["lines_deleted"] == 15
        assert stats["risk_score"] > 0
