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

from ontology_engine.schema import (
    DomainSchema,
    EntityDef,
    PropertyDef,
    PropertyType,
    RelationshipDef,
)
from ontology_engine.manager import OntologyManager, SchemaNotFoundError
from ontology_engine.extractor import (
    EntityExtractor,
    ExtractedEntity,
    ExtractedRelationship,
    ExtractionResult,
)
from ontology_engine.evolution import (
    CandidateConcept,
    ConceptCluster,
    EvolutionProposal,
    EvolutionService,
    EvolutionStore,
    GraphImpactAnalyzer,
    SchemaEvolutionGenerator,
    SemanticConceptClusterer,
)

__all__ = [
    "DomainSchema",
    "EntityDef",
    "PropertyDef",
    "PropertyType",
    "RelationshipDef",
    "OntologyManager",
    "SchemaNotFoundError",
    "EntityExtractor",
    "ExtractedEntity",
    "ExtractedRelationship",
    "ExtractionResult",
    "CandidateConcept",
    "ConceptCluster",
    "EvolutionProposal",
    "EvolutionService",
    "EvolutionStore",
    "GraphImpactAnalyzer",
    "SchemaEvolutionGenerator",
    "SemanticConceptClusterer",
]
