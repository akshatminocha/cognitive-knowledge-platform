"""
Entity Extractor — Schema-guided entity and relationship extraction from text.

Uses the active domain schema to guide LLM-based extraction of entities
and relationships from unstructured text chunks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from ontology_engine.schema import DomainSchema, EntityDef

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """A single entity extracted from text."""

    entity_type: str
    properties: dict[str, Any]
    source_text: str = ""
    confidence: float = 1.0


@dataclass
class ExtractedRelationship:
    """A relationship extracted between two entities."""

    relationship_type: str
    source_entity: str  # Entity identifier (e.g., a unique property value)
    target_entity: str
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    """Complete extraction result from a text chunk."""

    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    source_chunk: str = ""


class EntityExtractor:
    """
    Schema-guided entity extractor.

    Generates extraction prompts from the active domain schema and
    parses structured JSON output from the LLM.

    Note: This class generates prompts and parses results.
    The actual LLM call is made by the Agent Harness or ingestion pipeline.

    Usage:
        extractor = EntityExtractor(schema)

        # Generate extraction prompt for a text chunk:
        prompt = extractor.build_extraction_prompt(chunk_text)

        # Parse LLM's JSON response:
        result = extractor.parse_extraction_response(llm_json_str, chunk_text)
    """

    def __init__(self, schema: DomainSchema) -> None:
        self.schema = schema

    def build_extraction_prompt(self, text: str) -> str:
        """
        Build a structured extraction prompt from the schema.

        The prompt instructs the LLM to extract entities and relationships
        as JSON, guided by the schema's entity definitions and extraction rules.
        """
        # Build entity descriptions
        entity_specs = []
        for entity in self.schema.entities:
            props = []
            for p in entity.properties:
                req = " (REQUIRED)" if p.required else ""
                example = f' e.g. "{p.example}"' if p.example else ""
                props.append(f'    - "{p.name}": {p.type.value}{req}{example}')
            entity_specs.append(
                f'  "{entity.name}": {entity.description}\n'
                f"    Properties:\n" + "\n".join(props)
            )

        # Build relationship descriptions
        rel_specs = []
        for rel in self.schema.relationships:
            rel_specs.append(
                f'  "{rel.name}": ({rel.source}) -> ({rel.target}) — {rel.description}'
            )

        # Use custom extraction rules if defined
        custom_rules = ""
        if self.schema.extraction_rules:
            rule_lines = []
            for rule in self.schema.extraction_rules:
                rule_lines.append(f"  - {rule.entity_type}: {rule.extraction_prompt}")
            custom_rules = "\n\nExtraction hints:\n" + "\n".join(rule_lines)

        prompt = f"""Extract entities and relationships from the following text according to this schema.

Entity Types:
{chr(10).join(entity_specs)}

Relationship Types:
{chr(10).join(rel_specs)}
{custom_rules}

Respond with valid JSON in exactly this format:
{{
  "entities": [
    {{
      "entity_type": "<EntityTypeName>",
      "properties": {{ ... }}
    }}
  ],
  "relationships": [
    {{
      "relationship_type": "<RELATIONSHIP_NAME>",
      "source": "<identifier of source entity>",
      "target": "<identifier of target entity>",
      "properties": {{ ... }}
    }}
  ]
}}

If no entities or relationships are found, return empty arrays.
Only extract entities and relationships defined in the schema above.

Text to extract from:
---
{text}
---"""

        return prompt

    def parse_extraction_response(
        self,
        llm_response: str,
        source_chunk: str = "",
    ) -> ExtractionResult:
        """
        Parse the LLM's JSON extraction response into structured objects.

        Handles common LLM output quirks (markdown code fences, trailing commas).
        """
        # Strip markdown code fences if present
        cleaned = llm_response.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response: {e}")
            return ExtractionResult(source_chunk=source_chunk)

        result = ExtractionResult(source_chunk=source_chunk)

        # Parse entities
        for raw_entity in data.get("entities", []):
            entity_type = raw_entity.get("entity_type", "")
            properties = raw_entity.get("properties", {})

            # Validate entity type exists in schema
            if entity_type and self.schema.get_entity(entity_type):
                result.entities.append(
                    ExtractedEntity(
                        entity_type=entity_type,
                        properties=properties,
                        source_text=source_chunk,
                    )
                )
            else:
                logger.debug(f"Skipping unknown entity type: {entity_type}")

        # Parse relationships
        for raw_rel in data.get("relationships", []):
            rel_type = raw_rel.get("relationship_type", "")

            if rel_type and self.schema.get_relationship(rel_type):
                result.relationships.append(
                    ExtractedRelationship(
                        relationship_type=rel_type,
                        source_entity=raw_rel.get("source", ""),
                        target_entity=raw_rel.get("target", ""),
                        properties=raw_rel.get("properties", {}),
                    )
                )
            else:
                logger.debug(f"Skipping unknown relationship type: {rel_type}")

        logger.info(
            f"Extracted {len(result.entities)} entities and "
            f"{len(result.relationships)} relationships from chunk"
        )

        return result
