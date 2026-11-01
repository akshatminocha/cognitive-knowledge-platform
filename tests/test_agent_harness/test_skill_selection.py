"""
Tests for In-Agent Native Skill Selection (Approach 2) and SkillRegistry.
Ensures zero pre-flight latency, deterministic catalog assembly, and correct overrides.
"""

import pytest
from unittest.mock import MagicMock
from agent_harness.runner import AgentRunner, RunnerConfig
from agent_harness.skills.registry import SkillRegistry
from agent_harness.skills.models import Skill, SkillGuardrails


def test_skill_registry_load_directory():
    """Verify built-in skill library is properly loaded."""
    registry = SkillRegistry()
    count = registry.load_directory()
    assert count >= 5
    assert registry.get("knowledge_qa") is not None
    assert registry.get("clinical_summary") is not None
    assert registry.get("report_generation") is not None
    assert registry.get("fraud_detection") is not None
    assert registry.get("data_ingestion") is not None


def test_runner_auto_skill_instruction_assembly():
    """Verify in-agent dynamic skill catalog is injected when active_skill is None."""
    registry = SkillRegistry()
    registry.load_directory()

    runner = AgentRunner(
        config=RunnerConfig(active_skill=None),
        skill_registry=registry,
    )

    instruction = runner._build_instruction()

    # Must contain specialized skills
    assert "### Available Specialized Skills:" in instruction
    assert "clinical_summary" in instruction
    assert "report_generation" in instruction
    assert "fraud_detection" in instruction
    assert "knowledge_qa" in instruction

    # Must contain persona directives
    assert "Clinical Patient Profile" in instruction
    assert "Patient Demographics" in instruction
    assert "Active Medications" in instruction
    assert "Structured Reports & Analytical Synthesis" in instruction
    assert "Executive Summary" in instruction
    assert "Tool Calling Efficiency Rule" in instruction


def test_runner_explicit_skill_override():
    """Verify explicit skill selection overrides auto-catalog."""
    registry = SkillRegistry()
    registry.load_directory()

    custom_skill = Skill(
        name="custom_tester",
        version="1.0.0",
        description="A test skill",
        domain="testing",
        system_prompt="You are a dedicated testing persona.",
        tools=[],
        input_schema=[],
        output_schema=[],
        guardrails=SkillGuardrails(),
    )

    runner = AgentRunner(
        config=RunnerConfig(active_skill=custom_skill),
        skill_registry=registry,
    )

    instruction = runner._build_instruction()
    assert "You are a dedicated testing persona." in instruction
    assert "### Available Specialized Skills:" not in instruction


def test_runner_bypass_graph_tools_instruction():
    """Verify open-domain queries append database bypass instruction."""
    runner = AgentRunner(
        config=RunnerConfig(active_skill=None, bypass_graph_tools=True),
    )

    instruction = runner._build_instruction()
    assert "Provide a direct, helpful, and comprehensive answer without querying domain databases." in instruction
