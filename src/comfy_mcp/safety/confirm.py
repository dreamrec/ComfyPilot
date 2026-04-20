"""Elicitation-backed confirmation for destructive tools.

Usage:

    if not await confirm_destructive(ctx, "Really clear the entire queue?", confirm):
        return {"status": "cancelled", "reason": "user_declined"}

`confirm` is the tool's own `confirm: bool = False` param. If the caller
sets confirm=True, elicitation is bypassed (used by agents that have
already verified intent). Otherwise we ask the client/user to explicitly
accept.

Fallback behaviour when the host does not support elicitation:

- Default (`COMFY_STRICT_CONFIRM` unset or 0): fail-OPEN - allow the
  destructive operation. This preserves backward compatibility with
  elicitation-unaware MCP hosts where the gate would otherwise silently
  block every destructive call.

- Strict mode (`COMFY_STRICT_CONFIRM=1`): fail-CLOSED - any path that
  cannot obtain an explicit positive confirmation blocks the operation.
  Use this on shared/automated setups where a failed elicitation round
  trip should never be interpreted as consent.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context


class ConfirmDestructive(BaseModel):
    """Elicitation schema - a single boolean the user must set to True to proceed."""

    confirm: bool = Field(
        default=False,
        description="Type True to confirm this destructive operation, or False to cancel.",
    )


def _strict_mode() -> bool:
    """True when COMFY_STRICT_CONFIRM is set to a truthy value."""
    val = os.environ.get("COMFY_STRICT_CONFIRM", "").strip().lower()
    return val in {"1", "true", "yes", "on"}


async def confirm_destructive(
    ctx: "Context | None",
    message: str,
    already_confirmed: bool,
) -> bool:
    """Return True if the destructive operation should proceed.

    - If the caller passed confirm=True, proceed immediately.
    - If no Context or no elicit capability:
        - strict mode -> block (False)
        - default     -> allow (True, backward compat)
    - If elicit is called but raises:
        - strict mode -> block (False)
        - default     -> allow (True)
    - Otherwise block unless the response is accept + data.confirm=True.
    """
    if already_confirmed:
        return True

    strict = _strict_mode()

    if ctx is None or not hasattr(ctx, "elicit"):
        return not strict

    try:
        result = await ctx.elicit(message, ConfirmDestructive)
    except Exception:
        return not strict

    action = getattr(result, "action", None)
    data = getattr(result, "data", None)

    if action != "accept":
        return False
    if data is None:
        return False
    return bool(getattr(data, "confirm", False))
