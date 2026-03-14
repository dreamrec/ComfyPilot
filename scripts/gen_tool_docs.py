#!/usr/bin/env python3
"""Extract registered MCP tool names from runtime and compare against README."""

import re
import sys
from pathlib import Path


def get_registered_tools():
    """Import the MCP server and extract all registered tool names."""
    from comfy_mcp.server import mcp
    import comfy_mcp.tool_registry  # noqa: F401

    # FastMCP may store tools in different internal structures
    if hasattr(mcp, '_tools'):
        return sorted(mcp._tools.keys())
    elif hasattr(mcp, '_tool_manager') and hasattr(mcp._tool_manager, '_tools'):
        return sorted(t.name for t in mcp._tool_manager._tools.values())
    return []


def get_readme_tools():
    """Extract tool names from README.md backtick references."""
    readme = Path(__file__).parent.parent / "README.md"
    content = readme.read_text()
    return sorted(set(re.findall(r"`(comfy_\w+)`", content)))


def main():
    registered = get_registered_tools()
    documented = get_readme_tools()

    reg_set = set(registered)
    doc_set = set(documented)

    undocumented = reg_set - doc_set
    phantom = doc_set - reg_set

    print(f"Registered tools: {len(registered)}")
    print(f"Documented tools: {len(documented)}")

    if undocumented:
        print(f"\nRegistered but NOT in README ({len(undocumented)}):")
        for t in sorted(undocumented):
            print(f"  - {t}")

    if phantom:
        print(f"\nIn README but NOT registered ({len(phantom)}):")
        for t in sorted(phantom):
            print(f"  - {t}")

    if not undocumented and not phantom:
        print("\nAll tool names match.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
