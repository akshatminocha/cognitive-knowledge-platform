"""Tests for EntityExtractor — schema-guided extraction."""

from __future__ import annotations

import json
import pytest

from ontology_engine.schema import DomainSchema, EntityDef, PropertyDef, PropertyType
from ontology_engine.extractor import EntityExtractor, ExtractionResult


@pytest.fixture
def sample_schema() -> DomainSchema:
    """Fixture providing a basic domain schema for testing."""
    return DomainSchema(
        name="TestDomain",
        version="1.0.0",
        entities=[
            EntityDef(
                name="Person",
                label="Person",
                description="A human being",
                properties=[
                    PropertyDef(name="name", type=PropertyType.STRING, required=True),
                    PropertyDef(name="age", type=PropertyType.INTEGER),
                ]
            )
        ],
        relationships=[]
    )


class TestEntityExtractor:
    """Verify EntityExtractor prompt generation and JSON parsing."""

    def test_build_extraction_prompt(self, sample_schema: DomainSchema):
        """Prompt should include schema definitions and the target text."""
        extractor = EntityExtractor(sample_schema)
        text = "Alice is 30 years old."
        prompt = extractor.build_extraction_prompt(text)
        
        assert "Alice is 30 years old." in prompt
        assert "Person" in prompt
        assert "A human being" in prompt
        assert "name" in prompt

    def test_parse_extraction_response_valid(self, sample_schema: DomainSchema):
        """Valid JSON response should be parsed into an ExtractionResult."""
        extractor = EntityExtractor(sample_schema)
        
        mock_llm_json = json.dumps({
            "entities": [
                {
                    "entity_type": "Person",
                    "properties": {"name": "Alice", "age": 30},
                    "source_text": "Alice is 30"
                }
            ],
            "relationships": []
        })

        result = extractor.parse_extraction_response(mock_llm_json, "Alice is 30")
        
        assert isinstance(result, ExtractionResult)
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "Person"
        assert result.entities[0].properties["name"] == "Alice"
        assert result.entities[0].properties["age"] == 30

    def test_parse_extraction_response_invalid_json(self, sample_schema: DomainSchema):
        """Malformed JSON should gracefully return an empty result."""
        extractor = EntityExtractor(sample_schema)
        
        bad_json = "```json\n{ missing quotes }\n```"
        result = extractor.parse_extraction_response(bad_json, "test text")
        
        assert isinstance(result, ExtractionResult)
        assert len(result.entities) == 0
        assert len(result.relationships) == 0
