"""
The Mechanic — Autonomous Tool & Query Self-Correction Interceptor.

Sits between MCP tool runners and database engines (Neo4j / PostgreSQL).
When a database query fails with a syntax, schema, or directional error,
The Mechanic intercepts the exception, introspects active schema definitions,
generates a corrected read-only query (via heuristic repair and/or AI Gateway),
validates the repaired query through Guardrails AST checks, and retries execution
seamlessly without exhausting the primary agent's reasoning step budget.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Optional

from guardrails.tool_safety import ToolSafetyGuard, ToolSafetyViolation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Common Cypher / SQL Keyword Corrections
# ---------------------------------------------------------------------------
CYPHER_KEYWORD_TYPOS = {
    r"\bRETRUN\b": "RETURN",
    r"\bRETUN\b": "RETURN",
    r"\bMACTH\b": "MATCH",
    r"\bMATCh\b": "MATCH",
    r"\bWHER\b": "WHERE",
    r"\bWHRE\b": "WHERE",
    r"\bOERDER\s+BY\b": "ORDER BY",
    r"\bODER\s+BY\b": "ORDER BY",
    r"\bLIMT\b": "LIMIT",
    r"\bDISITNCT\b": "DISTINCT",
    r"\bDISTINT\b": "DISTINCT",
    r"\bOPTINAL\s+MATCH\b": "OPTIONAL MATCH",
}

SQL_KEYWORD_TYPOS = {
    r"\bSELETC\b": "SELECT",
    r"\bSEELCT\b": "SELECT",
    r"\bSLCT\b": "SELECT",
    r"\bFORM\b": "FROM",
    r"\bFRM\b": "FROM",
    r"\bWHER\b": "WHERE",
    r"\bWHRE\b": "WHERE",
    r"\bGRUP\s+BY\b": "GROUP BY",
    r"\bOERDER\s+BY\b": "ORDER BY",
    r"\bLIMT\b": "LIMIT",
}


class TheMechanic:
    """
    Autonomous Query Repair Agent & Interceptor.

    Handles error interception, heuristic and LLM-assisted schema-aware repairs,
    Guardrails AST validation, and transparent retry orchestration.
    """

    def __init__(
        self,
        guard: Optional[ToolSafetyGuard] = None,
        gateway_client: Any = None,
        max_retries: int = 2,
        enable_llm: bool = True,
    ) -> None:
        self.guard = guard or ToolSafetyGuard()
        self.gateway_client = gateway_client
        self.max_retries = max_retries
        self.enable_llm = enable_llm
        self.repair_history: list[dict[str, Any]] = []

    def _strip_markdown_fences(self, text: str) -> str:
        """Strip markdown code fences and extraneous leading/trailing markers."""
        cleaned = text.strip()
        # Remove ```cypher ... ``` or ```sql ... ``` or ``` ... ```
        cleaned = re.sub(r"^```(?:cypher|sql)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()
        # Strip wrapping single/double quotes if LLM wrapped whole query in quotes
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()
        return cleaned

    def heuristic_repair_cypher(
        self,
        query: str,
        error_message: str,
        schema_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Deterministic, AST-aware heuristic repair for common Cypher syntax & schema mistakes.

        Applies regex corrections, structural balance fixes, directional normalization,
        and schema entity remapping.
        """
        repaired = self._strip_markdown_fences(query)

        # 1. Strip trailing semicolons (Neo4j driver throws syntax error on trailing semicolon in some contexts)
        repaired = repaired.rstrip(";").strip()

        # 2. Fix common Cypher keyword typos
        for typo_pat, fix in CYPHER_KEYWORD_TYPOS.items():
            repaired = re.sub(typo_pat, fix, repaired, flags=re.IGNORECASE)

        # 3. Fix directional mismatch or relationship syntax errors
        # If error indicates relationship direction mismatch or syntax error near arrow:
        # e.g., `(a)-[r:TYPE]->>` or `(a)->[r:TYPE]->(b)`
        repaired = re.sub(r"-\[([^\]]+)\]->>", r"-[\1]->", repaired)
        repaired = re.sub(r"->\[([^\]]+)\]->", r"-[\1]->", repaired)
        repaired = re.sub(r"-\[([^\]]+)\]--", r"-[\1]->", repaired)

        # If error explicitly mentions relationship type or direction issues:
        err_lower = error_message.lower()
        if "direction" in err_lower or "relationship" in err_lower or "type" in err_lower:
            # Change directed relationship `-[r:TYPE]->` to bidirectional `-[r:TYPE]-` to resolve directionality bugs
            repaired = re.sub(r"-\[([^\]]+)\]->", r"-[\1]-", repaired)
            repaired = re.sub(r"<-\[([^\]]+)\]-", r"-[\1]-", repaired)

        # 4. Check parenthesis balance on node patterns
        # Example bug: MATCH (p:Patient WHERE p.id = '123' -> missing closing parenthesis
        if "WHERE" in repaired.upper():
            parts = re.split(r"\bWHERE\b", repaired, flags=re.IGNORECASE, maxsplit=1)
            before_where = parts[0]
            open_parens = before_where.count("(")
            close_parens = before_where.count(")")
            if open_parens > close_parens:
                # Add missing closing parenthesis before WHERE
                missing = open_parens - close_parens
                repaired = before_where.rstrip() + (")" * missing) + " WHERE " + parts[1].strip()

        # 5. Schema entity remapping (labels, relationship types, property keys)
        if schema_context:
            known_labels: list[str] = schema_context.get("node_labels", [])
            known_rels: list[str] = schema_context.get("relationship_types", [])
            known_props: list[str] = schema_context.get("property_keys", [])

            # Map node labels (e.g. `:patient` -> `:Patient`, `:patients` -> `:Patient`)
            for label in known_labels:
                # Case-insensitive label replacement in `:(label)`
                pat = rf":\s*({re.escape(label)}s?)\b"
                repaired = re.sub(
                    pat,
                    f":{label}",
                    repaired,
                    flags=re.IGNORECASE,
                )

            # Map relationship types (e.g. `[:has_condition]` -> `[:HAS_CONDITION]`)
            for rel in known_rels:
                pat = rf":\s*({re.escape(rel)}s?)\b"
                repaired = re.sub(
                    pat,
                    f":{rel}",
                    repaired,
                    flags=re.IGNORECASE,
                )

            # Map property keys (e.g. `.patientId` -> `.patient_id` or vice versa)
            for prop in known_props:
                # Try underscore vs camelCase mapping
                prop_norm = prop.replace("_", "").lower()
                # Find `.some_prop`
                matches = re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)", repaired)
                for m in matches:
                    if m.replace("_", "").lower() == prop_norm and m != prop:
                        repaired = re.sub(rf"\.{re.escape(m)}\b", f".{prop}", repaired)

        # 6. Ensure query has a RETURN clause
        if "RETURN" not in repaired.upper() and "MATCH" in repaired.upper():
            # Extract first node alias if possible: MATCH (p:Patient) -> RETURN p
            node_alias_match = re.search(r"MATCH\s*\(([a-zA-Z_]\w*):?", repaired, flags=re.IGNORECASE)
            alias = node_alias_match.group(1) if node_alias_match else "n"
            repaired = f"{repaired} RETURN {alias} LIMIT 25"

        return repaired.strip()

    def heuristic_repair_sql(
        self,
        query: str,
        error_message: str,
        schema_context: Optional[dict[str, Any]] = None,
    ) -> str:
        """Deterministic heuristic repair for SQL queries."""
        repaired = self._strip_markdown_fences(query)
        repaired = repaired.rstrip(";").strip()

        for typo_pat, fix in SQL_KEYWORD_TYPOS.items():
            repaired = re.sub(typo_pat, fix, repaired, flags=re.IGNORECASE)

        # Ensure query starts with SELECT or WITH
        tokens = repaired.strip().split()
        if tokens and tokens[0].upper() not in ("SELECT", "WITH", "EXPLAIN", "DESCRIBE"):
            repaired = f"SELECT {repaired}"

        return repaired.strip()

    async def llm_repair_cypher(
        self,
        query: str,
        error_message: str,
        schema_context: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> Optional[str]:
        """
        Use AI Gateway model to intelligently diagnose and repair a complex Cypher query.
        """
        if not self.enable_llm:
            return None

        has_keys = any(
            os.getenv(k)
            for k in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY")
        )
        if not has_keys and not self.gateway_client:
            return None

        if not self.gateway_client:
            try:
                from ai_gateway import GatewayClient
                self.gateway_client = GatewayClient()
            except Exception as e:
                logger.debug(f"Could not initialize GatewayClient for The Mechanic: {e}")
                return None

        schema_str = ""
        if schema_context:
            labels = schema_context.get("node_labels", [])
            rels = schema_context.get("relationship_types", [])
            props = schema_context.get("property_keys", [])
            schema_str = (
                f"\nACTIVE NEO4J GRAPH SCHEMA:\n"
                f"- Node Labels: {', '.join(labels[:25])}\n"
                f"- Relationship Types: {', '.join(rels[:25])}\n"
                f"- Property Keys: {', '.join(props[:30])}\n"
            )

        system_prompt = (
            "You are 'The Mechanic', an autonomous Cypher repair specialist for the Cognitive Knowledge Platform.\n"
            "A read-only Cypher query failed with a database error.\n"
            "Your task: Analyze the error and schema, and output ONLY the corrected, syntactically valid Cypher query.\n"
            "STRICT CONSTRAINTS:\n"
            "1. Output ONLY the raw Cypher query string. NO markdown fences (no ``` or ```cypher), NO commentary.\n"
            "2. The query MUST be strictly read-only (MATCH, WHERE, RETURN, WITH, ORDER BY, LIMIT).\n"
            "3. Correct any syntax errors, invalid relationship directions, incorrect casing, or unknown labels.\n"
        )

        user_content = (
            f"Failed Cypher Query:\n{query}\n\n"
            f"Neo4j Error Message:\n{error_message}\n"
            f"{schema_str}\n"
            f"Corrected Query:"
        )

        try:
            target_model = model or "gemini-2.5-flash"
            coro = self.gateway_client.completion(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=500,
            )
            resp = await asyncio.wait_for(coro, timeout=5.0)
            raw_text = resp.choices[0].message.content if resp.choices else ""
            cleaned = self._strip_markdown_fences(raw_text)
            if cleaned and "MATCH" in cleaned.upper():
                return cleaned
        except Exception as e:
            logger.warning(f"[The Mechanic] LLM repair call failed: {e}")

        return None

    async def repair_cypher(
        self,
        query: str,
        error_message: str,
        schema_context: Optional[dict[str, Any]] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        Orchestrate Cypher repair: Try LLM repair first if available, otherwise heuristic.
        Validates repaired query with Guardrails AST check before returning.
        """
        repaired: Optional[str] = None

        # 1. Attempt LLM repair if gateway client is configured and available
        try:
            repaired = await self.llm_repair_cypher(
                query=query,
                error_message=error_message,
                schema_context=schema_context,
                model=model,
            )
        except Exception as e:
            logger.debug(f"[The Mechanic] LLM repair skipped: {e}")

        # 2. Fall back to or refine with deterministic heuristic repair
        if not repaired:
            repaired = self.heuristic_repair_cypher(
                query=query,
                error_message=error_message,
                schema_context=schema_context,
            )

        # 3. Validate with Guardrails AST check
        try:
            self.guard.validate_cypher(repaired)
        except ToolSafetyViolation as tsv:
            logger.error(f"[The Mechanic] Repaired query violated safety guardrails: {tsv}. Falling back.")
            # Fall back to pure heuristic
            repaired = self.heuristic_repair_cypher(query, error_message, schema_context)
            self.guard.validate_cypher(repaired)

        return repaired

    async def intercept_and_execute(
        self,
        executor_fn: Callable[[str, Any], Awaitable[Any]],
        query: str,
        params: Any = None,
        query_type: str = "cypher",
        schema_provider: Optional[Callable[[], Awaitable[dict[str, Any]]]] = None,
    ) -> tuple[Any, dict[str, Any]]:
        """
        Execute a query with autonomous self-correction interceptor.

        1. Validates original query using Guardrails AST check.
        2. Executes query via executor_fn.
        3. If database exception occurs, intercepts the error, fetches active schema,
           and runs up to self.max_retries repair attempts.
        4. Seamlessly returns valid results without raising exceptions to primary agent.
        """
        # Validate initial query
        if query_type == "cypher":
            self.guard.validate_cypher(query)
        elif query_type == "sql":
            self.guard.validate_sql(query)

        current_query = query
        last_error: Optional[Exception] = None
        error_history: list[str] = []
        schema_context: Optional[dict[str, Any]] = None

        for attempt in range(self.max_retries + 1):
            try:
                t0 = time.monotonic()
                records = await executor_fn(current_query, params)
                duration_ms = (time.monotonic() - t0) * 1000

                # Record telemetry if this was a repaired query
                was_repaired = attempt > 0
                repair_entry = {
                    "timestamp": time.time(),
                    "was_repaired": was_repaired,
                    "attempts": attempt,
                    "original_query": query,
                    "final_query": current_query,
                    "error_history": error_history,
                    "duration_ms": duration_ms,
                    "status": "success",
                }
                self.repair_history.append(repair_entry)

                if was_repaired:
                    logger.info(
                        f"🔧 [The Mechanic] Query successfully repaired and executed on attempt {attempt}! "
                        f"Original: '{query}' -> Repaired: '{current_query}'"
                    )

                return records, repair_entry

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                error_history.append(err_str)
                logger.warning(
                    f"⚠️ [The Mechanic] Intercepted {query_type} execution error (attempt {attempt}/{self.max_retries}): {exc}"
                )

                if attempt >= self.max_retries:
                    break

                # Fetch schema context on demand
                if schema_provider and schema_context is None:
                    try:
                        schema_context = await schema_provider()
                    except Exception as s_err:
                        logger.debug(f"[The Mechanic] Schema introspection failed: {s_err}")
                        schema_context = {}

                # Attempt repair
                try:
                    if query_type == "cypher":
                        current_query = await self.repair_cypher(
                            query=current_query,
                            error_message=err_str,
                            schema_context=schema_context,
                        )
                    else:
                        current_query = self.heuristic_repair_sql(
                            query=current_query,
                            error_message=err_str,
                            schema_context=schema_context,
                        )
                    logger.info(f"🔧 [The Mechanic] Generated repaired query (attempt {attempt + 1}): {current_query}")
                except Exception as repair_exc:
                    logger.error(f"[The Mechanic] Repair generation failed: {repair_exc}")
                    break

        # If all repair attempts exhausted, record failure and raise
        fail_entry = {
            "timestamp": time.time(),
            "was_repaired": True,
            "attempts": self.max_retries,
            "original_query": query,
            "final_query": current_query,
            "error_history": error_history,
            "duration_ms": 0.0,
            "status": "exhausted",
        }
        self.repair_history.append(fail_entry)
        raise RuntimeError(
            f"[The Mechanic] Query execution failed after {self.max_retries} self-correction attempts. "
            f"Original query: '{query}'. Errors: {error_history}"
        ) from last_error


# Singleton instance
_GLOBAL_MECHANIC: Optional[TheMechanic] = None


def get_mechanic() -> TheMechanic:
    """Get or instantiate the global TheMechanic singleton."""
    global _GLOBAL_MECHANIC
    if _GLOBAL_MECHANIC is None:
        _GLOBAL_MECHANIC = TheMechanic()
    return _GLOBAL_MECHANIC
