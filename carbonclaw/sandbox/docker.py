"""Docker-based execution sandbox for secure shell commands."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


try:
    import docker as docker_py  # type: ignore

    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False


@dataclass
class SandboxResult:
    """Result from sandboxed execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


class DockerSandbox:
    """Execute commands inside a Docker container with configurable isolation."""

    def __init__(
        self,
        image: str = "python:3.12-slim",
        timeout: int = 120,
        network_disabled: bool = False,
        memory_limit: str = "512m",
        cpu_quota: int | None = None,
        working_dir: str = "/workspace",
    ) -> None:
        if not _DOCKER_AVAILABLE:
            raise ImportError(
                "Docker SDK is not installed. Install with: uv add docker"
            )

        self.image = image
        self.timeout = timeout
        self.network_disabled = network_disabled
        self.memory_limit = memory_limit
        self.cpu_quota = cpu_quota
        self.working_dir = working_dir
        self.client = docker_py.from_env()

    async def execute(
        self,
        command: list[str] | str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        volumes: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Run a command inside a transient Docker container."""
        cmd = command if isinstance(command, str) else " ".join(command)
        host_cwd = cwd or "."
        abs_cwd = Path(host_cwd).resolve()

        binds: dict[str, dict[str, str]] = {}
        if volumes:
            for host_path, container_path in volumes.items():
                binds[host_path] = {"bind": container_path, "mode": "rw"}
        # Always mount the working directory
        binds[str(abs_cwd)] = {"bind": self.working_dir, "mode": "rw"}

        container_config: dict[str, Any] = {
            "image": self.image,
            "command": ["sh", "-c", cmd],
            "working_dir": self.working_dir,
            "detach": True,
            "stdin_open": False,
            "tty": False,
            "network_disabled": self.network_disabled,
            "mem_limit": self.memory_limit,
            "volumes": binds,
            "environment": env or {},
        }
        if self.cpu_quota:
            container_config["cpu_quota"] = self.cpu_quota

        loop = asyncio.get_running_loop()
        start = asyncio.get_event_loop().time()

        try:
            # Create container but don't start yet
            container = await loop.run_in_executor(
                None, lambda: self.client.containers.create(**container_config)
            )
            
            # Start and wait for finish
            await loop.run_in_executor(None, container.start)
            
            wait_task = loop.run_in_executor(None, container.wait)
            try:
                await asyncio.wait_for(wait_task, timeout=self.timeout)
            except asyncio.TimeoutError:
                logger.warning("sandbox.timeout", container=container.id[:12])
                await loop.run_in_executor(None, container.kill)
                # Ensure it's removed
                await loop.run_in_executor(None, container.remove, {"force": True})
                return SandboxResult(
                    stdout="",
                    stderr=f"Sandbox execution timed out after {self.timeout}s.",
                    exit_code=-1,
                    duration_ms=(asyncio.get_event_loop().time() - start) * 1000,
                )

            # Retrieve separate stdout and stderr
            # Using socket to stream and separate outputs is the production way
            # For now, we'll use logs with specific flags
            stdout_bytes = await loop.run_in_executor(
                None, lambda: container.logs(stdout=True, stderr=False)
            )
            stderr_bytes = await loop.run_in_executor(
                None, lambda: container.logs(stdout=False, stderr=True)
            )
            
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Final stats
            inspect = await loop.run_in_executor(None, container.reload)
            exit_code = container.attrs["State"]["ExitCode"]

            await loop.run_in_executor(None, container.remove, {"force": True})

        except Exception as e:
            logger.exception("sandbox.error", command=cmd[:50])
            return SandboxResult(
                stdout="",
                stderr=f"Sandbox error: {str(e)}",
                exit_code=-1,
                duration_ms=0.0,
            )

        duration_ms = (asyncio.get_event_loop().time() - start) * 1000

        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )

    def ensure_image(self) -> None:
        """Pull the sandbox image if not present."""
        try:
            self.client.images.get(self.image)
        except docker_py.errors.ImageNotFound:
            logger.info("sandbox.pulling_image", image=self.image)
            self.client.images.pull(self.image)

    def build_sandbox_image(
        self,
        dockerfile: str | None = None,
        tag: str = "carbonclaw-sandbox:latest",
    ) -> str:
        """Build a custom sandbox image with pre-installed tooling."""
        df = dockerfile or (
            "FROM python:3.12-slim\n"
            "RUN apt-get update && apt-get install -y --no-install-recommends "
            "git curl build-essential && rm -rf /var/lib/apt/lists/*\n"
            "WORKDIR /workspace\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".dockerfile", delete=False) as f:
            f.write(df)
            f.flush()
            image, _ = self.client.images.build(path=".", dockerfile=f.name, tag=tag)
            return str(image.id)
