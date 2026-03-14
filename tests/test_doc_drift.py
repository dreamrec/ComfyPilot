"""Test that documented tool names match runtime registry."""
import re
from pathlib import Path


def _get_readme_tool_names():
    readme = Path(__file__).parent.parent / "README.md"
    content = readme.read_text(encoding="utf-8")
    return set(re.findall(r"`(comfy_\w+)`", content))


def _get_registered_tool_names():
    from comfy_mcp.server import mcp
    import comfy_mcp.tool_registry  # noqa: F401
    # FastMCP may store tools in different internal structures
    if hasattr(mcp, '_tools'):
        return set(mcp._tools.keys())
    elif hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        return {t.name for t in mcp._tool_manager._tools.values()}
    return set()


def test_no_phantom_tools_in_readme():
    """Every tool name in README must exist in the runtime registry."""
    documented = _get_readme_tool_names()
    registered = _get_registered_tool_names()
    phantom = documented - registered
    assert not phantom, f"README references tools that don't exist: {phantom}"


def test_no_undocumented_tools():
    """Every registered tool should appear in README."""
    documented = _get_readme_tool_names()
    registered = _get_registered_tool_names()
    undocumented = registered - documented
    assert not undocumented, f"Tools registered but not in README: {undocumented}"
