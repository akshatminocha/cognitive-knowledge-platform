"""
Tool Safety — Cypher and SQL AST-level read-only validation.

Parses query strings and validates that they contain only read operations.
Blocks destructive operations (CREATE, DELETE, DROP, SET, etc.) before
the query reaches the database.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Optional

from guardrails.config import ToolSafetyConfig

logger = logging.getLogger(__name__)


@dataclass
class ToolSafetyViolation(Exception):
    """Raised when a tool input violates safety constraints."""

    tool_name: str
    query: str
    violation_type: str
    detail: str
    blocked_keyword: Optional[str] = None

    def __str__(self) -> str:
        return (
            f"Tool safety violation [{self.violation_type}] in {self.tool_name}: "
            f"{self.detail}"
        )


def _tokenize_query(query: str) -> list[str]:
    """
    Tokenize a query into uppercase keywords, stripping strings and comments.

    This is a lightweight tokenizer — not a full parser, but sufficient
    for detecting dangerous keywords outside of string literals.
    """
    # Remove single-line comments
    cleaned = re.sub(r"//.*$", "", query, flags=re.MULTILINE)
    cleaned = re.sub(r"--.*$", "", cleaned, flags=re.MULTILINE)
    # Remove multi-line comments
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)
    # Remove string literals (single and double quoted)
    cleaned = re.sub(r"'[^']*'", "''", cleaned)
    cleaned = re.sub(r'"[^"]*"', '""', cleaned)
    # Tokenize: extract word-like tokens
    tokens = re.findall(r"\b[A-Za-z_]\w*\b", cleaned)
    return [t.upper() for t in tokens]


class ToolSafetyGuard:
    """
    Validates Cypher and SQL queries for read-only safety.

    Usage:
        guard = ToolSafetyGuard()

        # Validate a Cypher query:
        guard.validate_cypher("MATCH (n:Patient) RETURN n LIMIT 10")  # OK

        guard.validate_cypher("CREATE (n:Patient {name: 'test'})")
        # Raises ToolSafetyViolation

        # Validate a SQL query:
        guard.validate_sql("SELECT * FROM patients LIMIT 10")  # OK

        guard.validate_sql("DROP TABLE patients")
        # Raises ToolSafetyViolation
    """

    def __init__(self, config: Optional[ToolSafetyConfig] = None) -> None:
        self.config = config or ToolSafetyConfig()

    def validate_cypher(self, query: str) -> None:
        """
        Validate a Cypher query is read-only.

        Raises ToolSafetyViolation if any blocked keyword is found.
        """
        if not self.config.enforce_read_only:
            return

        tokens = _tokenize_query(query)

        for token in tokens:
            if token in [kw.upper() for kw in self.config.blocked_cypher_clauses]:
                raise ToolSafetyViolation(
                    tool_name="graph_mcp",
                    query=query,
                    violation_type="WRITE_OPERATION",
                    detail=(
                        f"Blocked Cypher keyword '{token}' detected. "
                        f"Only read operations (MATCH, RETURN, WHERE, etc.) are allowed."
                    ),
                    blocked_keyword=token,
                )

        # Additional check: CALL with write procedures
        if "CALL" in tokens:
            write_procs = ["db.create", "db.drop", "apoc.create", "apoc.refactor"]
            query_lower = query.lower()
            for proc in write_procs:
                if proc in query_lower:
                    raise ToolSafetyViolation(
                        tool_name="graph_mcp",
                        query=query,
                        violation_type="WRITE_PROCEDURE",
                        detail=f"Write procedure '{proc}' is not allowed.",
                        blocked_keyword=proc,
                    )

        logger.debug(f"Cypher query validated: {query[:80]}...")

    def validate_sql(self, query: str) -> None:
        """
        Validate a SQL query is read-only.

        Raises ToolSafetyViolation if any blocked keyword is found.
        """
        if not self.config.enforce_read_only:
            return

        tokens = _tokenize_query(query)

        for token in tokens:
            if token in [kw.upper() for kw in self.config.blocked_sql_keywords]:
                raise ToolSafetyViolation(
                    tool_name="tabular_mcp",
                    query=query,
                    violation_type="WRITE_OPERATION",
                    detail=(
                        f"Blocked SQL keyword '{token}' detected. "
                        f"Only SELECT queries are allowed."
                    ),
                    blocked_keyword=token,
                )

        # Must start with SELECT or WITH (CTEs)
        if tokens and tokens[0] not in ("SELECT", "WITH", "EXPLAIN", "DESCRIBE", "SHOW", "PRAGMA"):
            raise ToolSafetyViolation(
                tool_name="tabular_mcp",
                query=query,
                violation_type="NON_SELECT_QUERY",
                detail=(
                    f"Query must start with SELECT, WITH, EXPLAIN, or DESCRIBE. "
                    f"Found: '{tokens[0]}'"
                ),
            )

        logger.debug(f"SQL query validated: {query[:80]}...")

    def validate_tool_call(self, tool_name: str, tool_input: dict) -> None:
        """
        Validate any tool call based on the tool name.

        Dispatches to the appropriate validator based on tool_name.
        """
        query = tool_input.get("query", "")
        if not query:
            return

        if tool_name in ("execute_cypher", "graph_query", "graph_mcp"):
            self.validate_cypher(query)
        elif tool_name in ("execute_sql", "sql_query", "tabular_mcp"):
            self.validate_sql(query)
