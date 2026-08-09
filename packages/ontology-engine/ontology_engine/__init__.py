"""
CKP Ontology Engine — Declarative, Schema-Driven Domain Ontology Manager.

Loads industry-specific YAML schemas (healthtech, fintech, edtech, enterprise_ops)
and provides:
- Schema validation and loading
- Natural language schema descriptions for Text-to-Cypher prompts
- Entity/relationship extraction guidance for ingestion pipelines
- Column-to-entity mapping for structured data import

This is a fully standalone package with zero dependency on Neo4j, Qdrant,
or any other storage backend. It defines WHAT the domain looks like,
not WHERE the data lives.
"""

__version__ = "0.1.0"
