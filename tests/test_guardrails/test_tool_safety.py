"""Tests for ToolSafetyGuard — Cypher/SQL AST validation."""

from __future__ import annotations

import pytest

from guardrails.tool_safety import ToolSafetyGuard, ToolSafetyViolation


class TestCypherValidation:
    """Verify Cypher query validation (read-only enforcement)."""

    def test_read_query_allowed(self):
        """MATCH queries should pass validation."""
        guard = ToolSafetyGuard()
        guard.validate_cypher("MATCH (n:Patient) RETURN n LIMIT 10")

    def test_write_query_blocked(self):
        """CREATE queries should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_cypher("CREATE (n:Patient {name: 'Test'})")

    def test_delete_query_blocked(self):
        """DELETE queries should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_cypher("MATCH (n) DELETE n")

    def test_detach_delete_blocked(self):
        """DETACH DELETE should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_cypher("MATCH (n) DETACH DELETE n")

    def test_merge_blocked(self):
        """MERGE (write operation) should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_cypher("MERGE (n:Patient {name: 'Test'})")

    def test_set_blocked(self):
        """SET (property mutation) should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_cypher("MATCH (n:Patient) SET n.name = 'New'")


class TestSQLValidation:
    """Verify SQL query validation (read-only enforcement)."""

    def test_select_allowed(self):
        """SELECT queries should pass validation."""
        guard = ToolSafetyGuard()
        guard.validate_sql("SELECT * FROM patients WHERE id = 1")

    def test_insert_blocked(self):
        """INSERT should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_sql("INSERT INTO patients VALUES (1, 'Test')")

    def test_update_blocked(self):
        """UPDATE should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_sql("UPDATE patients SET name = 'Test' WHERE id = 1")

    def test_delete_blocked(self):
        """DELETE should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_sql("DELETE FROM patients WHERE id = 1")

    def test_drop_blocked(self):
        """DROP TABLE should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_sql("DROP TABLE patients")

    def test_truncate_blocked(self):
        """TRUNCATE should raise ToolSafetyViolation."""
        guard = ToolSafetyGuard()
        with pytest.raises(ToolSafetyViolation):
            guard.validate_sql("TRUNCATE TABLE patients")
