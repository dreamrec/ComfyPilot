"""Elicitation-backed confirmation for destructive tools.

Usage:

    if not await confirm_destructive(ctx, "Really clear the entire queue?", confirm):
        return {"status": "cancelled", "reason": "user_declined"}

confirm is the tool's own `confirm: bool = False` param. If the caller sets
confirm=True, elicitation is bypassed (used by agents that have already
verified intent). Otherwise we ask the client/user to explicitly accept.

If the client does not support elicitation, we degrade to "allow" so the
existing behavior is preserved for non-elicitation-aware hosts.
"""
from __future__ import annotations

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


async def confirm_destructive(
    ctx: "Context | None",
    message: str,
    already_confirmed: bool,
) -> bool:
    """Return True if the destructive operation should proceed.

    - If the caller passed confirm=True, proceed immediately.
    - If no Context or no elicit capability, proceed (graceful fallback).
    - Otherwise ask via ctx.elicit and return True only when user accepts AND
      the submitted schema data has confirm=True.
    """
    if already_confirmed:
        return True
    if ctx is None or not hasattr(ctx, "elicit"):
        return True

    try:
        result = await ctx.elicit(message, ConfirmDestructive)
    except Exception:
        # If elicitation itself errors (client doesn't support it etc.),
        # fall back to allow - we don't want to silently block users on
        # elicitation-unaware hosts.
        return True

    action = getattr(result, "action", None)
    data = getattr(result, "data", None)

    if action != "accept":
        return False
    if data is None:
        return False
    return bool(getattr(data, "confirm", False))
