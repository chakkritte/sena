"""Advanced research agent with Map-Reduce pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog

from carbonclaw.agents.base import ReactAgent
from carbonclaw.core.base import ApprovalCallback, BaseMemory, BaseProvider, BaseTool
from carbonclaw.core.models import CompletionRequest, Message, ToolResult
from carbonclaw.tools.web_search import WebSearchTool
from carbonclaw.tools.browser import BrowserTool

logger = structlog.get_logger(__name__)


@dataclass
class SourceInfo:
    """Metadata for a research source."""
    title: str
    url: str
    snippet: str
    content: str | None = None
    summary: str | None = None


@dataclass
class ResearchResult:
    """Output of the research pipeline."""
    query: str
    sources: list[SourceInfo]
    report: str
    map_model_used: str
    reduce_model_used: str
    total_tokens: int = 0


class ResearchAgent(ReactAgent):
    """Agent that performs multi-step research using Map-Reduce."""

    name = "research"
    description = "Performs deep web research and generates comprehensive reports."

    async def research(
        self,
        query: str,
        num_sources: int = 5,
        map_model: str | None = None,
        reduce_model: str | None = None,
    ) -> ResearchResult:
        """Execute the Map-Reduce research pipeline."""
        from carbonclaw.config.settings import CarbonClawConfig
        config = CarbonClawConfig()
        
        m_model = map_model or config.routing_models.get("general", "llama3.2:3b")
        r_model = reduce_model or config.routing_models.get("research", "qwen2.5:32b")

        # Step 1: Search
        logger.info("research.search", query=query)
        search_tool = WebSearchTool()
        search_result = await search_tool.execute({"query": query, "max_results": num_sources})
        
        import json
        try:
            raw_sources = json.loads(search_result.content)
            sources = [
                SourceInfo(title=s["title"], url=s["href"], snippet=s["body"])
                for s in raw_sources
            ]
        except (json.JSONDecodeError, KeyError):
            logger.error("research.search_failed", content=search_result.content)
            return ResearchResult(query, [], "Failed to parse search results.", m_model, r_model)

        # Step 2: Fetch & Clean
        logger.info("research.fetch", count=len(sources))
        browser = BrowserTool()
        import trafilatura
        
        async def fetch_one(source: SourceInfo) -> None:
            try:
                # Use Playwright for best rendering
                res = await browser.execute({"url": source.url, "action": "goto"})
                if res.is_error:
                    return
                
                html_res = await browser.execute({"action": "html"})
                # Clean with trafilatura
                clean_content = trafilatura.extract(html_res.content)
                if clean_content:
                    source.content = clean_content[:3000] # Truncate for local LLM context
            except Exception as e:
                logger.warning("research.fetch_failed", url=source.url, error=str(e))

        await asyncio.gather(*(fetch_one(s) for s in sources))
        
        # Filter out failed fetches
        active_sources = [s for s in sources if s.content]
        if not active_sources:
            return ResearchResult(query, sources, "Failed to fetch any relevant content.", m_model, r_model)

        # Step 3: Map (Summarize each)
        logger.info("research.map", count=len(active_sources), model=m_model)

        async def summarize_one(source: SourceInfo) -> None:
            prompt = (
                f"Summarize the key facts relevant to: {query}\n\n"
                f"Content from {source.url}:\n{source.content}"
            )
            try:
                resp = await self.provider.complete(
                    CompletionRequest(
                        messages=[Message(role="user", content=prompt)],
                        model=m_model,
                        temperature=0.3,
                    )
                )
                source.summary = resp.message.content
            except Exception as e:
                logger.warning("research.map_failed", url=source.url, error=str(e))

        await asyncio.gather(*(summarize_one(s) for s in active_sources))

        # Step 4: Reduce (Synthesize)
        logger.info("research.reduce", model=r_model)
        
        summaries_block = "\n\n".join(
            f"Source [{i+1}] ({s.url}):\n{s.summary}"
            for i, s in enumerate(active_sources) if s.summary
        )
        
        reduce_prompt = (
            "You are a professional research writer. Using ONLY the sources below, "
            f"write a comprehensive, well-structured report on: {query}\n\n"
            "Cite sources by number [1], [2], etc. in your text.\n\n"
            f"Sources:\n{summaries_block}"
        )
        
        try:
            final_resp = await self.provider.complete(
                CompletionRequest(
                    messages=[Message(role="user", content=reduce_prompt)],
                    model=r_model,
                    temperature=0.5,
                )
            )
            report = final_resp.message.content or "Failed to generate report."
            total_tokens = final_resp.usage.total_tokens if final_resp.usage else 0
        except Exception as e:
            logger.exception("research.reduce_failed")
            report = f"Error during synthesis: {str(e)}"
            total_tokens = 0

        return ResearchResult(
            query=query,
            sources=active_sources,
            report=report,
            map_model_used=m_model,
            reduce_model_used=r_model,
            total_tokens=total_tokens
        )
