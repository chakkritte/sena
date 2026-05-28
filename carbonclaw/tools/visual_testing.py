"""Playwright Visual Regression Testing tool."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import structlog

from carbonclaw.core.base import BaseTool
from carbonclaw.core.models import ToolResult

try:
    from PIL import Image, ImageChops
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

logger = structlog.get_logger(__name__)


class PlaywrightVisualTestingTool(BaseTool):
    """Executes visual regression testing via Playwright and PIL."""

    name = "visual_regression_test"
    description = (
        "Launch Playwright Chromium, navigate to a URL, take a screenshot, "
        "and compare it against a baseline image to detect visual regression differences."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to capture and verify.",
            },
            "baseline_path": {
                "type": "string",
                "description": "The path to the baseline/reference image.",
            },
            "candidate_path": {
                "type": "string",
                "description": "The path to save the new screenshot.",
            },
            "threshold": {
                "type": "number",
                "description": "Visual difference RMS threshold above which the test fails.",
                "default": 1.0,
            },
        },
        "required": ["url", "baseline_path", "candidate_path"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the visual regression test."""
        if not _PIL_AVAILABLE:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="PIL/Pillow is not installed. Install with: uv add pillow",
                is_error=True,
            )

        url = arguments.get("url", "")
        baseline_path = Path(arguments.get("baseline_path", ""))
        candidate_path = Path(arguments.get("candidate_path", ""))
        threshold = float(arguments.get("threshold", 1.0))

        # Ensure directories exist
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Launch Playwright and capture screenshot
            from playwright.async_api import async_playwright

            logger.info("visual_test.capturing", url=url, path=str(candidate_path))
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 800})
                await page.goto(url, wait_until="networkidle")
                await page.screenshot(path=str(candidate_path))
                await browser.close()

            # 2. Check if baseline exists. If not, save candidate as baseline and exit
            if not baseline_path.exists():  # noqa: ASYNC240
                import shutil
                shutil.copy(candidate_path, baseline_path)
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=(
                        f"🌱 Created baseline screenshot at {baseline_path}. "
                        "Subsequent runs will compare screenshots against this baseline."
                    ),
                )

            # 3. Perform image comparison
            logger.info(
                "visual_test.comparing",
                baseline=str(baseline_path),
                candidate=str(candidate_path),
            )
            img_baseline = Image.open(baseline_path).convert("RGB")
            img_candidate = Image.open(candidate_path).convert("RGB")

            # Match size if slightly off
            if img_baseline.size != img_candidate.size:
                img_candidate = img_candidate.resize(img_baseline.size)

            diff = ImageChops.difference(img_baseline, img_candidate)
            histogram = diff.histogram()

            # Root-Mean-Square calculation
            sq = (value * ((idx % 256) ** 2) for idx, value in enumerate(histogram))
            sum_of_squares = sum(sq)
            rms = math.sqrt(sum_of_squares / float(img_baseline.size[0] * img_baseline.size[1]))

            # Normalize RMS to 0-100 score
            diff_percentage = min(100.0, (rms / 255.0) * 100.0)
            passed = diff_percentage <= threshold

            if passed:
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=(
                        f"✅ Visual Regression test passed! "
                        f"Diff: {diff_percentage:.3f}% (Threshold: {threshold}%)"
                    ),
                )
            else:
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=(
                        f"🔴 Visual Regression test failed! Visual deviation detected. "
                        f"Diff: {diff_percentage:.3f}% (Threshold: {threshold}%). "
                        f"Review screenshot differences at {candidate_path}."
                    ),
                    is_error=True,
                )

        except Exception as e:
            logger.exception("visual_test.error", error=str(e))
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=f"Visual regression test failed due to error: {e}",
                is_error=True,
            )
