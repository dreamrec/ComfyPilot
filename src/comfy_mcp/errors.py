"""Structured error hierarchy for ComfyPilot.

Every error carries: error_code, message, suggestion, retry_possible, details.
Tools catch these and return structured error responses to the agent.
"""

from __future__ import annotations


class ComfyError(Exception):
    """Base error with structured fields for actionable error reporting."""

    def __init__(
        self,
        error_code: str,
        message: str,
        suggestion: str = "",
        retry_possible: bool = False,
        details: dict | None = None,
    ):
        self.error_code = error_code
        self.message = message
        self.suggestion = suggestion
        self.retry_possible = retry_possible
        self.details = details
        super().__init__(message)

    def to_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "suggestion": self.suggestion,
            "retry_possible": self.retry_possible,
            "details": self.details,
        }


class ComfyConnectionError(ComfyError):
    """Cannot reach the ComfyUI instance."""


class ComfyAPIError(ComfyError):
    """ComfyUI returned an HTTP 4xx/5xx error."""


class ComfyTimeoutError(ComfyError):
    """Execution or request timed out."""


class ComfyVRAMError(ComfyError):
    """VRAM exhausted or below safety threshold."""
