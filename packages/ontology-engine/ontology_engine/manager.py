"""
Ontology Manager — Schema loader and provider.

Loads domain schemas from YAML files, validates them, and provides
schema context to other components (MCP servers, ingestion pipeline,
agent harness).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from ontology_engine.schema import DomainSchema

logger = logging.getLogger(__name__)

# Default schemas directory (relative to package)
DEFAULT_SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"


class SchemaNotFoundError(Exception):
    """Raised when a requested schema is not found."""

    def __init__(self, schema_name: str, search_path: Path):
        self.schema_name = schema_name
        self.search_path = search_path
        super().__init__(
            f"Schema '{schema_name}' not found in {search_path}. "
            f"Available: {', '.join(OntologyManager.list_available(search_path))}"
        )


class OntologyManager:
    """
    Manages loading and access to domain schemas.

    Usage:
        manager = OntologyManager()
        schema = manager.load("healthtech")

        # Get schema prompt for LLM system instructions:
        prompt = schema.to_schema_prompt()

        # Get entity names for validation:
        entities = schema.get_entity_names()
    """

    def __init__(self, schemas_dir: Optional[Path] = None) -> None:
        self.schemas_dir = schemas_dir or DEFAULT_SCHEMAS_DIR
        self._cache: dict[str, DomainSchema] = {}

    def load(self, schema_name: str) -> DomainSchema:
        """
        Load a domain schema by name from the schemas directory.

        Caches loaded schemas for repeated access.
        """
        # Return from cache if available
        if schema_name in self._cache:
            return self._cache[schema_name]

        schema_path = self.schemas_dir / f"{schema_name}.yaml"
        if not schema_path.exists():
            # Try .yml extension
            schema_path = self.schemas_dir / f"{schema_name}.yml"

        if not schema_path.exists():
            raise SchemaNotFoundError(schema_name, self.schemas_dir)

        logger.info(f"Loading schema: {schema_path}")

        with open(schema_path, "r") as f:
            raw = yaml.safe_load(f)

        schema = DomainSchema(**raw)
        self._cache[schema_name] = schema

        logger.info(
            f"Loaded schema '{schema.name}' v{schema.version}: "
            f"{len(schema.entities)} entities, {len(schema.relationships)} relationships"
        )

        return schema

    def load_from_dict(self, data: dict) -> DomainSchema:
        """Load a schema from a dictionary (useful for testing or dynamic schemas)."""
        schema = DomainSchema(**data)
        self._cache[schema.name] = schema
        return schema

    @staticmethod
    def list_available(schemas_dir: Optional[Path] = None) -> list[str]:
        """List all available schema names in the schemas directory."""
        search_dir = schemas_dir or DEFAULT_SCHEMAS_DIR
        if not search_dir.exists():
            return []

        schemas = []
        for f in search_dir.iterdir():
            if f.suffix in (".yaml", ".yml") and not f.name.startswith("_"):
                schemas.append(f.stem)
        return sorted(schemas)

    def get_schema_prompt(self, schema_name: str) -> str:
        """Load a schema and return its LLM-ready prompt string."""
        schema = self.load(schema_name)
        return schema.to_schema_prompt()

    def reload(self, schema_name: str) -> DomainSchema:
        """Force-reload a schema from disk (clears cache for that schema)."""
        if schema_name in self._cache:
            del self._cache[schema_name]
        return self.load(schema_name)

    def clear_cache(self) -> None:
        """Clear all cached schemas."""
        self._cache.clear()
