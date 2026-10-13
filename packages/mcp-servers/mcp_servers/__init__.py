"""
CKP MCP Servers — Model Context Protocol Tool Servers.

Exposes three FastMCP servers for agent tool access:
- Graph MCP Server: Schema-introspecting Cypher queries against Neo4j
- Retrieval MCP Server: Hybrid (dense + sparse) search against Qdrant
- Tabular MCP Server: Text-to-SQL against PostgreSQL

All tool inputs are validated by the Guardrails AST checker before execution.
Graph queries are grounded by the Ontology Engine's dynamic schema.
"""

__version__ = "0.1.0"
