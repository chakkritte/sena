import pytest
from carbonclaw.tools.vision import VisionTool
from pathlib import Path

@pytest.mark.asyncio
async def test_vision_tool_file_not_found():
    tool = VisionTool()
    result = await tool.execute({"image_path": "non_existent.png"})
    assert result.is_error
    assert "not found" in result.content

@pytest.mark.asyncio
async def test_vision_tool_payload(tmp_path):
    img = tmp_path / "test.png"
    img.write_bytes(b"fake_image_data")
    
    tool = VisionTool()
    result = await tool.execute({"image_path": str(img), "prompt": "Analyze this"})
    
    assert not result.is_error
    assert "[[IMAGE:" in result.content
    assert "Analyze this" in result.content
