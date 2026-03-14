"""Tests for ComfyPilot error hierarchy."""

from comfy_mcp.errors import (
    ComfyAPIError,
    ComfyConnectionError,
    ComfyError,
    ComfyTimeoutError,
    ComfyVRAMError,
)


def test_comfy_error_fields():
    err = ComfyError("TEST_CODE", "test message", "try again", True, {"key": "val"})
    assert err.error_code == "TEST_CODE"
    assert err.message == "test message"
    assert err.suggestion == "try again"
    assert err.retry_possible is True
    assert err.details == {"key": "val"}
    assert str(err) == "test message"


def test_comfy_error_defaults():
    err = ComfyError("CODE", "msg")
    assert err.suggestion == ""
    assert err.retry_possible is False
    assert err.details is None


def test_comfy_error_to_dict():
    err = ComfyError("E001", "broke", "fix it", True, {"x": 1})
    d = err.to_dict()
    assert d == {
        "error_code": "E001",
        "message": "broke",
        "suggestion": "fix it",
        "retry_possible": True,
        "details": {"x": 1},
    }


def test_subclasses_inherit_fields():
    for cls in [ComfyConnectionError, ComfyAPIError, ComfyTimeoutError, ComfyVRAMError]:
        err = cls("SUB", "sub msg", "sub suggestion")
        assert isinstance(err, ComfyError)
        assert err.error_code == "SUB"
        assert err.to_dict()["error_code"] == "SUB"


def test_comfy_error_is_exception():
    err = ComfyError("E", "exception test")
    assert isinstance(err, Exception)
    try:
        raise err
    except ComfyError as caught:
        assert caught.error_code == "E"
