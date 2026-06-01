"""
BroccoliDB tool module loader — imports submodules that register Hermes tools.

Loaded exclusively by ``plugins/dietcode/tools_loader.py`` (not ``tools/`` auto-discovery).
"""

import plugins.dietcode.lib.tools.broccolidb_tools.core_tools        # noqa: F401
import plugins.dietcode.lib.tools.broccolidb_tools.joyzoning_tools    # noqa: F401
import plugins.dietcode.lib.tools.broccolidb_tools.graph_tools        # noqa: F401
import plugins.dietcode.lib.tools.broccolidb_tools.structural_tools   # noqa: F401
import plugins.dietcode.lib.tools.broccolidb_tools.queue_tools        # noqa: F401

from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements  # noqa: F401
