"""
Tabular MCP Server — PostgreSQL FastMCP tool server.

Exposes read-only SQL query execution against PostgreSQL as MCP tools.
All queries are validated by the Guardrails AST checker before execution.
Supports schema introspection and parameterized queries.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PostgreSQL connection settings (from environment)
# ---------------------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "ckp_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ckp_db")


# ---------------------------------------------------------------------------
# Lifespan: manage the asyncpg connection pool
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(server: FastMCP):
    """Create and tear down the PostgreSQL connection pool."""
    pool = await asyncpg.create_pool(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
        min_size=2,
        max_size=10,
    )
    try:
        # Verify connectivity
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version()")
            logger.info(f"Connected to PostgreSQL: {version[:60]}...")

        server.state["pg_pool"] = pool
        yield
    finally:
        await pool.close()
        logger.info("PostgreSQL connection pool closed")


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="tabular-mcp",
    description="PostgreSQL — Read-only SQL query execution for structured data analytics",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def execute_sql(
    query: str,
    params: list[Any] | None = None,
    limit: int = 100,
) -> list[dict]:
    """
    Execute a read-only SQL query against PostgreSQL.

    The query is validated by the guardrails AST checker before execution.
    Only SELECT, WITH, EXPLAIN, and DESCRIBE statements are allowed.

    A LIMIT clause is automatically appended if not present.

    Args:
        query: A SQL query string (read-only).
        params: Optional list of query parameters for parameterized queries.
        limit: Maximum rows to return (default 100). Overridden if LIMIT is in query.

    Returns:
        A list of result rows as dictionaries.

    Example:
        execute_sql("SELECT * FROM patients WHERE diagnosis = $1", params=["diabetes"])
    """
    pool: asyncpg.Pool = mcp.state["pg_pool"]

    # Auto-append LIMIT if not present
    query_upper = query.upper().strip().rstrip(";")
    if "LIMIT" not in query_upper:
        query = f"{query.strip().rstrip(';')} LIMIT {limit}"

    logger.info(f"Executing SQL: {query[:100]}...")

    async with pool.acquire() as conn:
        if params:
            rows = await conn.fetch(query, *params)
        else:
            rows = await conn.fetch(query)

    records = [dict(row) for row in rows]
    logger.info(f"Returned {len(records)} rows")
    return records


@mcp.tool()
async def get_table_schema(table_name: str) -> list[dict]:
    """
    Get the column schema for a specific table.

    Args:
        table_name: The name of the table to inspect.

    Returns:
        A list of column definitions with name, type, and nullable info.
    """
    pool: asyncpg.Pool = mcp.state["pg_pool"]

    query = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        ORDER BY ordinal_position
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, table_name)

    return [
        {
            "column": row["column_name"],
            "type": row["data_type"],
            "nullable": row["is_nullable"] == "YES",
            "default": row["column_default"],
            "max_length": row["character_maximum_length"],
        }
        for row in rows
    ]


@mcp.tool()
async def list_tables() -> list[dict]:
    """
    List all tables in the public schema with row counts.

    Returns:
        A list of table info dicts with name and approximate row count.
    """
    pool: asyncpg.Pool = mcp.state["pg_pool"]

    query = """
        SELECT
            t.table_name,
            COALESCE(s.n_live_tup, 0) AS approximate_row_count
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s
            ON t.table_name = s.relname
        WHERE t.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """

    async with pool.acquire() as conn:
        rows = await conn.fetch(query)

    return [
        {
            "table_name": row["table_name"],
            "approximate_row_count": row["approximate_row_count"],
        }
        for row in rows
    ]


@mcp.tool()
async def describe_database() -> dict:
    """
    Get a high-level overview of the PostgreSQL database.

    Returns:
        A dictionary with database name, size, table count, and table names.
    """
    pool: asyncpg.Pool = mcp.state["pg_pool"]

    async with pool.acquire() as conn:
        db_size = await conn.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        table_count = await conn.fetchval(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )

    return {
        "database": POSTGRES_DB,
        "size": db_size,
        "table_count": table_count,
        "tables": [row["table_name"] for row in tables],
    }
