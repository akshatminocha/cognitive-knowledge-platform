"""
Tests for The Mechanic — Autonomous Tool & Query Self-Correction Interceptor.
"""

import pytest
from guardrails.tool_safety import ToolSafetyGuard, ToolSafetyViolation
from mcp_servers.mechanic import TheMechanic, get_mechanic


class TestMechanicHeuristicRepair:
    """Tests for deterministic AST-aware heuristic query repair."""

    def test_cypher_keyword_typo_repair(self):
        mechanic = TheMechanic()
        bad_query = "MACTH (p:Patient) WHER p.age > 30 RETRUN p.name LIMT 10"
        repaired = mechanic.heuristic_repair_cypher(
            bad_query,
            error_message="Invalid input 'MACTH': expected <init>",
        )
        assert "MATCH (p:Patient)" in repaired
        assert "WHERE p.age > 30" in repaired
        assert "RETURN p.name" in repaired
        assert "LIMIT 10" in repaired

    def test_missing_parenthesis_repair(self):
        mechanic = TheMechanic()
        bad_query = "MATCH (p:Patient WHERE p.id = 'PAT-001' RETURN p"
        repaired = mechanic.heuristic_repair_cypher(
            bad_query,
            error_message="SyntaxError: Invalid input 'WHERE': expected ')'",
        )
        assert "MATCH (p:Patient) WHERE p.id = 'PAT-001' RETURN p" in repaired

    def test_directional_mismatch_repair(self):
        mechanic = TheMechanic()
        directed_query = "MATCH (p:Patient)-[r:TREATED_BY]->(d:Doctor) RETURN p, d"
        repaired = mechanic.heuristic_repair_cypher(
            directed_query,
            error_message="Relationship direction mismatch: Relationship TREATED_BY not found in given direction",
        )
        # Should convert to undirected traversal
        assert "-[r:TREATED_BY]-" in repaired
        assert "->" not in repaired

    def test_schema_aware_label_and_property_remapping(self):
        mechanic = TheMechanic()
        bad_query = "MATCH (p:patient)-[r:prescribed]->(m:medication) WHERE p.patientId = '123' RETURN p, m"
        schema_context = {
            "node_labels": ["Patient", "Medication", "Doctor"],
            "relationship_types": ["PRESCRIBED", "TREATED_BY"],
            "property_keys": ["patient_id", "name", "dosage"],
        }
        repaired = mechanic.heuristic_repair_cypher(
            bad_query,
            error_message="Unknown label 'patient'",
            schema_context=schema_context,
        )
        assert ":Patient" in repaired
        assert ":PRESCRIBED" in repaired
        assert "p.patient_id" in repaired

    def test_sql_keyword_typo_repair(self):
        mechanic = TheMechanic()
        bad_sql = "SEELCT patient_id, name FRM patients WHER age > 40 LIMT 5"
        repaired = mechanic.heuristic_repair_sql(
            bad_sql,
            error_message="syntax error at or near 'SEELCT'",
        )
        assert "SELECT patient_id, name" in repaired
        assert "FROM patients" in repaired
        assert "WHERE age > 40" in repaired
        assert "LIMIT 5" in repaired


class TestMechanicGuardrailsIntegration:
    """Tests ensuring repaired queries strictly comply with read-only guardrails."""

    @pytest.mark.asyncio
    async def test_guardrails_blocks_destructive_repair(self):
        mechanic = TheMechanic(enable_llm=False)
        # Even if a bad repair somehow introduced a write operation, guardrail must block it
        malicious_query = "MATCH (p:Patient) DELETE p"
        with pytest.raises(ToolSafetyViolation):
            await mechanic.repair_cypher(
                malicious_query,
                error_message="Some error",
            )


class TestMechanicExecutionInterceptor:
    """Tests for the seamless retry interceptor loop."""

    @pytest.mark.asyncio
    async def test_intercept_and_execute_success_on_repair(self):
        mechanic = TheMechanic()
        call_count = 0

        async def mock_cypher_executor(q: str, p=None):
            nonlocal call_count
            call_count += 1
            if "RETRUN" in q:
                raise Exception("SyntaxError: Invalid input 'RETRUN'")
            return [{"name": "John Doe", "patient_id": "PAT-001"}]

        failing_query = "MATCH (p:Patient) RETRUN p.name, p.patient_id"
        records, meta = await mechanic.intercept_and_execute(
            executor_fn=mock_cypher_executor,
            query=failing_query,
            query_type="cypher",
        )

        assert call_count == 2
        assert len(records) == 1
        assert records[0]["name"] == "John Doe"
        assert meta["was_repaired"] is True
        assert meta["attempts"] == 1
        assert "RETURN" in meta["final_query"]

    @pytest.mark.asyncio
    async def test_intercept_and_execute_exhausted_retries(self):
        mechanic = TheMechanic(max_retries=2)

        async def always_failing_executor(q: str, p=None):
            raise Exception("Persistent database connection error")

        with pytest.raises(RuntimeError) as exc_info:
            await mechanic.intercept_and_execute(
                executor_fn=always_failing_executor,
                query="MATCH (n) RETURN n",
                query_type="cypher",
            )

        assert "Query execution failed after 2 self-correction attempts" in str(exc_info.value)

    def test_global_singleton(self):
        m1 = get_mechanic()
        m2 = get_mechanic()
        assert m1 is m2
