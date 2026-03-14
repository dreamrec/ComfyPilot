"""Central tool registration.

Imports all tools/ modules so their @mcp.tool() decorators execute at startup.
This file is imported by server._register_tools().
"""

# Tools will be imported here as they are implemented.
# Each import triggers the @mcp.tool() decorators in that module.

from comfy_mcp.tools import system      # noqa: F401  -- Task 5
from comfy_mcp.tools import models      # noqa: F401  -- Task 6
from comfy_mcp.tools import workflow    # noqa: F401  -- Task 7
from comfy_mcp.tools import nodes       # noqa: F401  -- Task 8
from comfy_mcp.tools import images      # noqa: F401  -- Task 9
from comfy_mcp.tools import history     # noqa: F401  -- Task 11
from comfy_mcp.tools import monitoring  # noqa: F401  -- Task 13
from comfy_mcp.tools import snapshots   # noqa: F401  -- Task 15
from comfy_mcp.tools import memory      # noqa: F401  -- Task 16
from comfy_mcp.tools import safety      # noqa: F401  -- Task 17
from comfy_mcp.tools import builder     # noqa: F401  -- Task 18
# from comfy_mcp.tools import output_routing  # noqa: F401 -- Task 19
