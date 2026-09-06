"""
Prompt Registry — Load, store, and look up versioned prompt templates.

Manages a library of PromptTemplate objects loaded from YAML files.
Supports lookup by name, filtering by tags, and versioning.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from agent_harness.prompts.models import PromptTemplate, PromptVariable

logger = logging.getLogger(__name__)

# Default directory for built-in templates
DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptRegistry:
    """
    Registry for prompt templates.

    Loads templates from YAML files and provides lookup by name,
    filtering by tags, and listing.

    Usage:
        registry = PromptRegistry()
        registry.load_directory(Path("templates/"))

        template = registry.get("grounded_qa")
        qa_templates = registry.find_by_tag("qa")
    """

    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate] = {}

    def load_directory(self, directory: Optional[Path] = None) -> int:
        """
        Load all YAML templates from a directory.

        Args:
            directory: Path to the templates directory.
                       Defaults to the built-in templates/ folder.

        Returns:
            Number of templates loaded.
        """
        target_dir = directory or DEFAULT_TEMPLATES_DIR

        if not target_dir.exists():
            logger.warning(f"Templates directory not found: {target_dir}")
            return 0

        count = 0
        for yaml_file in sorted(target_dir.glob("*.yaml")):
            try:
                template = self._load_template_file(yaml_file)
                self._templates[template.name] = template
                count += 1
                logger.debug(f"Loaded template: {template.name} v{template.version}")
            except Exception as e:
                logger.error(f"Failed to load template {yaml_file.name}: {e}")

        logger.info(f"Loaded {count} prompt templates from {target_dir}")
        return count

    def register(self, template: PromptTemplate) -> None:
        """
        Register a template programmatically.

        Overwrites any existing template with the same name.
        """
        self._templates[template.name] = template
        logger.debug(f"Registered template: {template.name} v{template.version}")

    def get(self, name: str) -> Optional[PromptTemplate]:
        """Look up a template by name."""
        return self._templates.get(name)

    def find_by_tag(self, tag: str) -> list[PromptTemplate]:
        """Find all templates that have a specific tag."""
        return [t for t in self._templates.values() if tag in t.tags]

    def list_all(self) -> list[dict]:
        """List all registered templates with metadata."""
        return [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
                "tags": t.tags,
                "variables": [v.name for v in t.variables],
            }
            for t in self._templates.values()
        ]

    def save_template(
        self,
        template: PromptTemplate,
        directory: Optional[Path] = None,
    ) -> Path:
        """
        Save a template to a YAML file in the given directory.

        Also registers the template in-memory.

        Args:
            template: The PromptTemplate to save.
            directory: Target directory. Defaults to built-in templates/.

        Returns:
            Path to the saved YAML file.
        """
        target_dir = directory or DEFAULT_TEMPLATES_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"{template.name}.yaml"

        # Serialize to dict
        data = {
            "name": template.name,
            "version": template.version,
            "description": template.description,
            "tags": template.tags,
            "author": template.author,
            "template": template.template,
            "variables": [
                {
                    "name": v.name,
                    "type": v.type.value,
                    "required": v.required,
                    "description": v.description,
                    **({"default": v.default} if v.default is not None else {}),
                }
                for v in template.variables
            ],
        }

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        # Register in-memory
        self.register(template)
        logger.info(f"Saved template '{template.name}' to {file_path}")
        return file_path

    def _load_template_file(self, path: Path) -> PromptTemplate:
        """Load a single template from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse variables
        variables = []
        for var_data in data.get("variables", []):
            variables.append(
                PromptVariable(
                    name=var_data["name"],
                    type=var_data.get("type", "string"),
                    required=var_data.get("required", True),
                    default=var_data.get("default"),
                    description=var_data.get("description", ""),
                )
            )

        return PromptTemplate(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            author=data.get("author", "system"),
            template=data["template"],
            variables=variables,
        )
