"""Documentation and technical writing agent with AST and Git-aware sync capabilities."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, TYPE_CHECKING

from carbonclaw.agents.base import ReactAgent

if TYPE_CHECKING:
    from carbonclaw.core.base import (
        ApprovalCallback,
        BaseMemory,
        BaseProvider,
        BaseTool,
    )


class DocsAgent(ReactAgent):
    """Agent specialized in documentation, docstrings, and AST auditing."""

    name = "docs"
    description = "Maintains codebase documentation, inline docstrings, and AST synchronization."

    def __init__(
        self,
        provider: BaseProvider,
        tools: list[BaseTool],
        memory: BaseMemory,
        model: str | None = None,
        max_iterations: int = 5,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        """Initialize the DocsAgent."""
        super().__init__(
            provider=provider,
            tools=tools,
            memory=memory,
            system_prompt=(
                "You are a technical writer and documentation expert. "
                "Your goal is to keep the project's documentation clear, accurate, and up-to-date. "
                "1. Read the source code to understand recent changes. "
                "2. Update README.md, ARCHITECTURE.md, and other Markdown files. "
                "3. Ensure all public functions and classes have descriptive docstrings. "
                "4. Use file_read, file_write, and file_patch tools to make updates."
            ),
            model=model,
            max_iterations=max_iterations,
            approval_callback=approval_callback,
        )

    async def audit_docstrings(self, filepath: str) -> list[dict[str, Any]]:
        """Parse AST of a Python file and find functions/classes missing docstrings."""
        path = Path(filepath)
        if not path.exists():
            return []

        content = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(content)
        except Exception:
            return []

        missing = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private methods/functions
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue
                if not ast.get_docstring(node):
                    missing.append({
                        "type": "function",
                        "name": node.name,
                        "lineno": node.lineno,
                        "code": ast.unparse(node)[:500],
                    })
            elif isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                if not ast.get_docstring(node):
                    missing.append({
                        "type": "class",
                        "name": node.name,
                        "lineno": node.lineno,
                        "code": ast.unparse(node)[:500],
                    })
        return missing

    async def generate_docstring(self, name: str, code_snippet: str) -> str:
        """Use the LLM provider to synthesize a high-quality docstring."""
        prompt = (
            f"Generate a concise, professional Python docstring for the following code element '{name}'. "
            "Use triple double-quotes, include parameter descriptions, and return only the raw docstring text "
            "without any markdown code fences:\n\n"
            f"{code_snippet}"
        )
        from carbonclaw.core.models import CompletionRequest, Message
        response = await self.provider.complete(
            CompletionRequest(
                messages=[Message(role="user", content=prompt)],
                model=self.model or "",
                stream=False
            )
        )
        doc = response.message.content or ""
        doc = doc.strip()
        if not doc.startswith('"""'):
            doc = f'"""{doc}"""'
        return doc
