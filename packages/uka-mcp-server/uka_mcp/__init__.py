"""
Universal Knowledge Artifact (UKA) FastMCP Server Package.
"""

from uka_mcp.server import (
    mcp,
    uka_inspect,
    uka_export_context,
    uka_get_schema,
    uka_search,
    uka_query_graph,
    uka_list_entities,
    uka_get_media,
)

__all__ = [
    "mcp",
    "uka_inspect",
    "uka_export_context",
    "uka_get_schema",
    "uka_search",
    "uka_query_graph",
    "uka_list_entities",
    "uka_get_media",
]
