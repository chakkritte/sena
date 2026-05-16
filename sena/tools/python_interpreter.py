"""Python code execution tool using Docker sandboxing."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any

from sena.core.base import BaseTool
from sena.core.models import ToolResult
from sena.sandbox.docker import DockerSandbox


class PythonTool(BaseTool):
    """Execute Python code in a transient Docker container."""

    name = "python"
    description = (
        "Execute Python code in a sandboxed Docker container. "
        "Returns stdout, stderr, and any generated images as base64."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Maximum seconds to wait.",
                "default": 60,
            },
            "packages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "pip packages to install before execution.",
                "default": [],
            },
        },
        "required": ["code"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        code = arguments.get("code", "")
        timeout = arguments.get("timeout", 60)
        packages = arguments.get("packages", [])

        if not code:
            return ToolResult(
                tool_call_id="",
                name=self.name,
                content="No code provided.",
                is_error=True,
            )

        # Wrap user code to capture stdout and generate images
        wrapped = self._wrap_code(code)

        with tempfile.TemporaryDirectory() as tmpdir:
            script_path = Path(tmpdir) / "script.py"
            script_path.write_text(wrapped, encoding="utf-8")

            sandbox = DockerSandbox(
                image="python:3.12-slim",
                timeout=timeout,
                memory_limit="512m",
            )

            install_cmd = ""
            if packages:
                install_cmd = f"pip install {' '.join(packages)} && "

            try:
                result = await sandbox.execute(
                    command=f"{install_cmd}python /workspace/script.py",
                    volumes={tmpdir: "/workspace"},
                )
            except Exception as e:
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=f"Sandbox error: {e}",
                    is_error=True,
                )

            output = result.stdout or ""
            if result.stderr:
                output += f"\n\n[stderr]\n{result.stderr}"
            if result.exit_code != 0:
                return ToolResult(
                    tool_call_id="",
                    name=self.name,
                    content=output,
                    is_error=True,
                )

            # Check for generated images
            image_outputs: list[str] = []
            img_dir = Path(tmpdir)
            for img_file in img_dir.glob("sena_output_*.png"):
                b64 = base64.b64encode(img_file.read_bytes()).decode()
                image_outputs.append(f"data:image/png;base64,{b64}")

            if image_outputs:
                output += "\n\n[Generated images]\n" + "\n".join(image_outputs)

            return ToolResult(
                tool_call_id="",
                name=self.name,
                content=output,
                is_error=False,
            )

    @staticmethod
    def _wrap_code(code: str) -> str:
        """Wrap user code to redirect matplotlib output to files."""
        return (
            "import sys\n"
            "import os\n"
            "# Redirect matplotlib to non-interactive backend\n"
            "try:\n"
            "    import matplotlib\n"
            "    matplotlib.use('Agg')\n"
            "    import matplotlib.pyplot as plt\n"
            "    _orig_show = plt.show\n"
            "    def _sena_show(*args, **kwargs):\n"
            "        for i, fig in enumerate(plt.get_fignums()):\n"
            "            plt.figure(fig).savefig(f'sena_output_{i}.png')\n"
            "    plt.show = _sena_show\n"
            "except ImportError:\n"
            "    pass\n"
            "\n"
            "# Run user code\n"
            f"{code}\n"
            "\n"
            "# Auto-save any remaining figures\n"
            "try:\n"
            "    import matplotlib.pyplot as plt\n"
            "    for i, fig in enumerate(plt.get_fignums()):\n"
            "        plt.figure(fig).savefig(f'sena_output_{i}.png')\n"
            "except ImportError:\n"
            "    pass\n"
        )
