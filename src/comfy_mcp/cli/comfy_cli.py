"""Async subprocess wrapper for comfy-cli.

We use comfy-cli (the official ComfyUI lifecycle CLI) for tasks that have
no REST API equivalent: installing ComfyUI itself, launching / stopping
the server, installing custom nodes via Comfy Manager, downloading
models. Everything else in ComfyPilot talks over HTTP/WebSocket.

Design notes:
- We never run a shell. asyncio.create_subprocess_exec takes argv directly,
  so injection from a malicious node name is not a concern - the binary
  receives each arg as a separate element of argv.
- comfy-cli prompts for analytics / workspace selection on first run. We
  pass --skip-prompt by default to keep things non-interactive.
- Some operations (notably comfy install) can take 10+ minutes. The
  default timeout is 60 s; callers override per-tool (launch_server uses
  10 s, install_node 600 s, etc.).
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from typing import Sequence


# Candidate names for the comfy-cli binary - the package itself is named
# `comfy-cli` on PyPI but it installs both `comfy` and `comfy-cli` entry
# points. We try the shorter name first.
_CANDIDATE_BINARIES = ("comfy", "comfy-cli")


class ComfyCliError(RuntimeError):
    """Raised for comfy-cli operational failures (missing binary, timeout)."""


@dataclass(slots=True)
class ComfyCliResult:
    """Outcome of a single comfy-cli invocation."""

    returncode: int
    stdout: str
    stderr: str
    argv: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "argv": list(self.argv),
        }


def detect_comfy_cli() -> str | None:
    """Return the resolved path to a comfy-cli binary on PATH, or None."""
    for name in _CANDIDATE_BINARIES:
        path = shutil.which(name)
        if path:
            return path
    return None


async def run_comfy_cli(
    args: Sequence[str],
    *,
    workspace: str | None = None,
    skip_prompt: bool = True,
    timeout: float = 60.0,
) -> ComfyCliResult:
    """Invoke comfy-cli with the given args.

    Args:
        args: Positional CLI args after the comfy binary (e.g. ['node', 'install', 'X']).
        workspace: Optional --workspace prefix.
        skip_prompt: Pass --skip-prompt to bypass first-run analytics prompts (default True).
        timeout: Seconds before SIGKILL. Defaults to 60 s; raise for long-running install/launch.

    Returns:
        ComfyCliResult with returncode + captured stdout/stderr.

    Raises:
        ComfyCliError: If the binary is not on PATH or the call exceeds `timeout`.
    """
    binary = detect_comfy_cli()
    if binary is None:
        raise ComfyCliError(
            "comfy-cli is not on PATH. Install it with one of:\n"
            "  pipx install comfy-cli       (recommended)\n"
            "  uvx --from comfy-cli comfy   (no install)\n"
            "  pip install --user comfy-cli (fallback)"
        )

    argv: list[str] = [binary]
    if workspace:
        argv.extend(["--workspace", workspace])
    if skip_prompt:
        argv.append("--skip-prompt")
    argv.extend(str(a) for a in args)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError as e:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        try:
            await proc.wait()
        except Exception:
            pass
        raise ComfyCliError(
            f"comfy-cli call {' '.join(argv[1:])!r} timed out after {timeout}s"
        ) from e

    return ComfyCliResult(
        returncode=int(proc.returncode or 0),
        stdout=(stdout_bytes or b"").decode("utf-8", errors="replace"),
        stderr=(stderr_bytes or b"").decode("utf-8", errors="replace"),
        argv=tuple(argv),
    )
