"""
Ontology Schema — Pydantic models for declarative domain schemas.

Defines the data model for industry-agnostic ontology schemas:
- Entity types with their properties and labels
- Relationship types with source/target constraints
- Document-to-entity extraction rules
- Embedding configuration per entity type

Schemas are defined in YAML and loaded into these models at runtime.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class PropertyType(str, Enum):
    """Supported property types for entity and relationship properties."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    LIST_STRING = "list[string]"
    JSON = "json"


class PropertyDef(BaseModel):
    """Definition of a single property on an entity or relationship."""

    name: str = Field(description="Property name (e.g., 'date_of_birth')")
    type: PropertyType = Field(default=PropertyType.STRING, description="Data type")
    description: str = Field(default="", description="Human-readable description")
    required: bool = Field(default=False, description="Whether this property is required")
    unique: bool = Field(default=False, description="Whether this property must be unique")
    indexed: bool = Field(default=False, description="Whether to create a DB index")
    example: Optional[str] = Field(default=None, description="Example value for LLM prompts")


class EntityDef(BaseModel):
    """
    Definition of an entity type (node label) in the knowledge graph.

    Example YAML:
        - name: Patient
          label: Patient
          description: "A patient in the healthcare system"
          properties:
            - name: patient_id
              type: string
              required: true
              unique: true
            - name: name
              type: string
              required: true
    """

    name: str = Field(description="Entity type name (e.g., 'Patient', 'Transaction')")
    label: str = Field(description="Neo4j node label")
    description: str = Field(default="", description="What this entity represents")
    properties: list[PropertyDef] = Field(default_factory=list)
    embed_properties: list[str] = Field(
        default_factory=list,
        description="Property names to concatenate for vector embedding",
    )


class RelationshipDef(BaseModel):
    """
    Definition of a relationship type (edge) in the knowledge graph.

    Example YAML:
        - name: TREATED_BY
          description: "Patient is treated by a doctor"
          source: Patient
          target: Doctor
          properties:
            - name: treatment_date
              type: date
    """

    name: str = Field(description="Relationship type name (e.g., 'TREATED_BY')")
    description: str = Field(default="", description="What this relationship represents")
    source: str = Field(description="Source entity type name")
    target: str = Field(description="Target entity type name")
    properties: list[PropertyDef] = Field(default_factory=list)


class ExtractionRule(BaseModel):
    """
    Rules for extracting entities from unstructured documents.

    Guides the LLM on how to identify and extract entity instances
    from text chunks.
    """

    entity_type: str = Field(description="The entity type to extract")
    extraction_prompt: str = Field(
        description="Prompt template for the LLM to extract this entity type",
    )
    required_properties: list[str] = Field(
        default_factory=list,
        description="Properties that must be extracted (others are optional)",
    )


class TabularMapping(BaseModel):
    """
    Mapping from tabular data columns to entity properties.

    Used for structured data ingestion (CSV/Parquet → Graph).
    """

    source_column: str = Field(description="Column name in the source data")
    target_entity: str = Field(description="Target entity type name")
    target_property: str = Field(description="Target property name on the entity")
    transform: Optional[str] = Field(
        default=None,
        description="Optional transformation (e.g., 'uppercase', 'parse_date')",
    )


class DomainSchema(BaseModel):
    """
    Complete domain schema definition.

    This is the top-level model loaded from a YAML file.
    It defines everything the platform needs to know about a specific
    industry domain: entities, relationships, extraction rules, and
    tabular mappings.
    """

    name: str = Field(description="Schema name (e.g., 'healthtech', 'fintech')")
    version: str = Field(default="1.0.0", description="Schema version")
    description: str = Field(default="", description="Schema description")
    entities: list[EntityDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)
    extraction_rules: list[ExtractionRule] = Field(default_factory=list)
    tabular_mappings: list[TabularMapping] = Field(default_factory=list)

    def get_entity(self, name: str) -> Optional[EntityDef]:
        """Look up an entity definition by name."""
        for entity in self.entities:
            if entity.name == name:
                return entity
        return None

    def get_relationship(self, name: str) -> Optional[RelationshipDef]:
        """Look up a relationship definition by name."""
        for rel in self.relationships:
            if rel.name == name:
                return rel
        return None

    def get_entity_names(self) -> list[str]:
        """Return all entity type names."""
        return [e.name for e in self.entities]

    def get_relationship_names(self) -> list[str]:
        """Return all relationship type names."""
        return [r.name for r in self.relationships]

    def to_schema_prompt(self) -> str:
        """
        Generate a natural-language schema description for LLM context.

        This is injected into the system prompt so the LLM understands
        the graph structure and can generate valid Cypher queries.
        """
        lines = [f"# Knowledge Graph Schema: {self.name}\n"]

        if self.entities:
            lines.append("## Entity Types (Node Labels)")
            for entity in self.entities:
                props = ", ".join(
                    f"{p.name} ({p.type.value}{'*' if p.required else ''})"
                    for p in entity.properties
                )
                lines.append(f"- **{entity.label}**: {entity.description}")
                if props:
                    lines.append(f"  Properties: {props}")

        if self.relationships:
            lines.append("\n## Relationship Types (Edges)")
            for rel in self.relationships:
                props = ", ".join(
                    f"{p.name} ({p.type.value})" for p in rel.properties
                )
                lines.append(
                    f"- **({rel.source})-[:{rel.name}]->({rel.target})**: {rel.description}"
                )
                if props:
                    lines.append(f"  Properties: {props}")

        return "\n".join(lines)
