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
from comfy_mcp.tools import output_routing  # noqa: F401 -- Task 19
from comfy_mcp.tools import blueprints  # noqa: F401  -- Phase 1 Task 10
from comfy_mcp.tools import viz         # noqa: F401  -- Phase 3 Task 3
from comfy_mcp.tools import ingest      # noqa: F401  -- Phase 3 Task 4
from comfy_mcp.tools import sweep       # noqa: F401  -- Phase 3 Task 5
from comfy_mcp.tools import hub         # noqa: F401  -- Phase 3 Task 6
from comfy_mcp.tools import partner_apis  # noqa: F401 -- v1.7.0 / Task 13
from comfy_mcp.tools import diagnostics   # noqa: F401 -- v1.8.0 operational toolkit
from comfy_mcp.tools import lifecycle     # noqa: F401 -- v1.8.0 comfy-cli wrappers
from comfy_mcp.tools import auto_fix_deps # noqa: F401 -- v1.8.0 auto-install workflow deps
from comfy_mcp.tools import run_with_inputs  # noqa: F401 -- v1.8.0 upload+inject+queue
from comfy_mcp.tools import randomize_seeds  # noqa: F401 -- v1.8.0 seed sentinel handling
from comfy_mcp.tools import instance      # noqa: F401 -- Desktop/local instance discovery
from comfy_mcp.tools import artifacts     # noqa: F401 -- generic output artifact inventory
from comfy_mcp.tools import workers       # noqa: F401 -- comfy-env worker observability
