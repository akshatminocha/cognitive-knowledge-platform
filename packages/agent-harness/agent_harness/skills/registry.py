"""
Skill Registry — Load, store, validate, and look up agent skills.

Manages a library of Skill objects loaded from YAML files.
Supports lookup by name, filtering by domain/tags, and saving new skills.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml

from agent_harness.skills.models import (
    Skill,
    SkillExample,
    SkillGuardrails,
    SkillInputField,
    SkillOutputField,
)

logger = logging.getLogger(__name__)

# Default directory for built-in skills
DEFAULT_LIBRARY_DIR = Path(__file__).parent / "library"


class SkillRegistry:
    """
    Registry for agent skills.

    Loads skills from YAML files and provides lookup by name,
    filtering by domain, and listing.

    Usage:
        registry = SkillRegistry()
        registry.load_directory(Path("library/"))

        skill = registry.get("clinical_summary")
        health_skills = registry.find_by_domain("healthtech")
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def load_directory(self, directory: Optional[Path] = None) -> int:
        """
        Load all YAML skill definitions from a directory.

        Args:
            directory: Path to the skills library directory.
                       Defaults to the built-in library/ folder.

        Returns:
            Number of skills loaded.
        """
        target_dir = directory or DEFAULT_LIBRARY_DIR

        if not target_dir.exists():
            logger.warning(f"Skills library directory not found: {target_dir}")
            return 0

        count = 0
        for yaml_file in sorted(target_dir.glob("*.yaml")):
            try:
                skill = self._load_skill_file(yaml_file)
                self._skills[skill.name] = skill
                count += 1
                logger.debug(f"Loaded skill: {skill.name} v{skill.version}")
            except Exception as e:
                logger.error(f"Failed to load skill {yaml_file.name}: {e}")

        logger.info(f"Loaded {count} skills from {target_dir}")
        return count

    def register(self, skill: Skill) -> None:
        """Register a skill programmatically."""
        self._skills[skill.name] = skill
        logger.debug(f"Registered skill: {skill.name} v{skill.version}")

    def get(self, name: str) -> Optional[Skill]:
        """Look up a skill by name."""
        return self._skills.get(name)

    def find_by_domain(self, domain: str) -> list[Skill]:
        """Find all skills for a specific domain."""
        return [
            s for s in self._skills.values()
            if s.domain == domain or s.domain == "general"
        ]

    def find_by_tag(self, tag: str) -> list[Skill]:
        """Find all skills that have a specific tag."""
        return [s for s in self._skills.values() if tag in s.tags]

    def list_all(self) -> list[dict]:
        """List all registered skills with metadata."""
        return [
            {
                "name": s.name,
                "version": s.version,
                "domain": s.domain,
                "description": s.description,
                "tags": s.tags,
                "tools": s.tools,
                "inputs": [f.name for f in s.input_schema],
                "outputs": [f.name for f in s.output_schema],
            }
            for s in self._skills.values()
        ]

    def save_skill(
        self,
        skill: Skill,
        directory: Optional[Path] = None,
    ) -> Path:
        """
        Save a skill to a YAML file and register it.

        Args:
            skill: The Skill to save.
            directory: Target directory. Defaults to built-in library/.

        Returns:
            Path to the saved YAML file.
        """
        target_dir = directory or DEFAULT_LIBRARY_DIR
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"{skill.name}.yaml"

        # Serialize to dict
        data = {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "domain": skill.domain,
            "tags": skill.tags,
            "author": skill.author,
            "system_prompt": skill.system_prompt,
            "tools": skill.tools,
            "input_schema": [
                {
                    "name": f.name,
                    "type": f.type,
                    "required": f.required,
                    "description": f.description,
                    **({"default": f.default} if f.default is not None else {}),
                }
                for f in skill.input_schema
            ],
            "output_schema": [
                {
                    "name": f.name,
                    "type": f.type,
                    "description": f.description,
                }
                for f in skill.output_schema
            ],
            "guardrails": {
                "pii_masking": skill.guardrails.pii_masking.value,
                "max_steps": skill.guardrails.max_steps,
                "max_tokens": skill.guardrails.max_tokens,
                "require_grounding": skill.guardrails.require_grounding,
            },
            "examples": [
                {"input": ex.input, "output": ex.output}
                for ex in skill.examples
            ],
        }

        if skill.prompt_template:
            data["prompt_template"] = skill.prompt_template

        with open(file_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        self.register(skill)
        logger.info(f"Saved skill '{skill.name}' to {file_path}")
        return file_path

    def _load_skill_file(self, path: Path) -> Skill:
        """Load a single skill from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        # Parse input schema
        input_schema = [
            SkillInputField(
                name=f["name"],
                type=f.get("type", "string"),
                required=f.get("required", True),
                default=f.get("default"),
                description=f.get("description", ""),
            )
            for f in data.get("input_schema", [])
        ]

        # Parse output schema
        output_schema = [
            SkillOutputField(
                name=f["name"],
                type=f.get("type", "string"),
                description=f.get("description", ""),
            )
            for f in data.get("output_schema", [])
        ]

        # Parse guardrails
        gr_data = data.get("guardrails", {})
        guardrails = SkillGuardrails(
            pii_masking=gr_data.get("pii_masking", "standard"),
            max_steps=gr_data.get("max_steps", 10),
            max_tokens=gr_data.get("max_tokens", 4096),
            require_grounding=gr_data.get("require_grounding", True),
        )

        # Parse examples
        examples = [
            SkillExample(input=ex["input"], output=ex["output"])
            for ex in data.get("examples", [])
        ]

        return Skill(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            domain=data.get("domain", "general"),
            tags=data.get("tags", []),
            author=data.get("author", "system"),
            system_prompt=data.get("system_prompt", ""),
            prompt_template=data.get("prompt_template"),
            tools=data.get("tools", []),
            input_schema=input_schema,
            output_schema=output_schema,
            guardrails=guardrails,
            examples=examples,
        )
