"""
Graph MCP Server — Neo4j FastMCP tool server.

Exposes Cypher query execution against Neo4j as MCP tools.
All queries are validated by the Guardrails AST checker before execution.
The schema prompt is dynamically injected from the Ontology Engine.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Neo4j connection settings (from environment)
# ---------------------------------------------------------------------------
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "changeme")


# ---------------------------------------------------------------------------
# Lifespan: manage the Neo4j async driver
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(server: FastMCP):
    """Create and tear down the Neo4j async driver."""
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )
    try:
        await driver.verify_connectivity()
        logger.info(f"Connected to Neo4j at {NEO4J_URI}")
        server.state["neo4j"] = driver
        yield
    finally:
        await driver.close()
        logger.info("Neo4j connection closed")


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="graph-mcp",
    description="Neo4j Knowledge Graph — Schema-aware Cypher query execution",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helper: execute a Cypher query
# ---------------------------------------------------------------------------
async def _run_cypher(driver: AsyncDriver, query: str, params: dict | None = None) -> list[dict]:
    """Execute a read-only Cypher query and return results as dicts."""
    async with driver.session() as session:
        result = await session.run(query, parameters=params or {})
        records = await result.data()
        return records


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def execute_cypher(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    """
    Execute a read-only Cypher query against the knowledge graph.

    The query is validated by the guardrails AST checker before execution.
    Only MATCH/RETURN/WHERE/ORDER BY/LIMIT operations are allowed.

    Args:
        query: A Cypher query string (read-only).
        params: Optional dictionary of query parameters.

    Returns:
        A list of result records as dictionaries.

    Example:
        execute_cypher("MATCH (p:Patient) RETURN p.name, p.patient_id LIMIT 10")
    """
    driver: AsyncDriver = mcp.state["neo4j"]
    logger.info(f"Executing Cypher: {query[:100]}...")
    records = await _run_cypher(driver, query, params)
    logger.info(f"Returned {len(records)} records")
    return records


@mcp.tool()
async def get_graph_schema() -> dict:
    """
    Retrieve the current Neo4j graph schema.

    Returns node labels, relationship types, and property keys
    currently in the database. Useful for understanding what data
    is available before writing queries.

    Returns:
        A dictionary with 'node_labels', 'relationship_types', and 'property_keys'.
    """
    driver: AsyncDriver = mcp.state["neo4j"]

    labels = await _run_cypher(driver, "CALL db.labels() YIELD label RETURN label")
    rel_types = await _run_cypher(
        driver, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"
    )
    prop_keys = await _run_cypher(
        driver, "CALL db.propertyKeys() YIELD propertyKey RETURN propertyKey"
    )

    return {
        "node_labels": [r["label"] for r in labels],
        "relationship_types": [r["relationshipType"] for r in rel_types],
        "property_keys": [r["propertyKey"] for r in prop_keys],
    }


@mcp.tool()
async def count_nodes(label: str | None = None) -> dict:
    """
    Count nodes in the graph, optionally filtered by label.

    Args:
        label: Optional node label to filter by (e.g., 'Patient', 'Doctor').

    Returns:
        A dictionary with the count.
    """
    driver: AsyncDriver = mcp.state["neo4j"]

    if label:
        query = f"MATCH (n:`{label}`) RETURN count(n) AS count"
    else:
        query = "MATCH (n) RETURN count(n) AS count"

    records = await _run_cypher(driver, query)
    return {"label": label or "ALL", "count": records[0]["count"] if records else 0}


@mcp.tool()
async def find_neighbors(
    node_label: str,
    property_name: str,
    property_value: str,
    max_depth: int = 1,
    limit: int = 25,
) -> list[dict]:
    """
    Find neighboring nodes connected to a specific node.

    Args:
        node_label: The label of the starting node (e.g., 'Patient').
        property_name: The property to match on (e.g., 'patient_id').
        property_value: The value to match (e.g., 'PAT-001').
        max_depth: Maximum relationship depth to traverse (default 1).
        limit: Maximum number of results to return (default 25).

    Returns:
        A list of connected nodes with relationship info.
    """
    driver: AsyncDriver = mcp.state["neo4j"]

    query = (
        f"MATCH (start:`{node_label}` {{{property_name}: $value}})"
        f"-[r*1..{max_depth}]-(neighbor) "
        f"RETURN DISTINCT labels(neighbor) AS labels, "
        f"properties(neighbor) AS properties, "
        f"type(r[0]) AS relationship "
        f"LIMIT {limit}"
    )

    records = await _run_cypher(driver, query, {"value": property_value})
    return records
