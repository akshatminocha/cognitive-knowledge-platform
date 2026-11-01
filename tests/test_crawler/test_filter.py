"""
Unit tests for DomainFilter and FileIntegrityGate.
"""

import asyncio
from pathlib import Path
import pytest

from backend.crawler.filter import DomainFilter, FileIntegrityGate, FilterResult


def test_file_integrity_gate_non_existent(tmp_path: Path):
    gate = FileIntegrityGate()
    valid, reason, size = gate.check_integrity(tmp_path / "missing.txt")
    assert not valid
    assert "does not exist" in reason


def test_file_integrity_gate_empty_file(tmp_path: Path):
    gate = FileIntegrityGate()
    empty_file = tmp_path / "empty.txt"
    empty_file.touch()
    valid, reason, size = gate.check_integrity(empty_file)
    assert not valid
    assert "empty" in reason


def test_file_integrity_gate_unsupported_extension(tmp_path: Path):
    gate = FileIntegrityGate()
    bad_file = tmp_path / "binary.exe"
    bad_file.write_bytes(b"content")
    valid, reason, size = gate.check_integrity(bad_file)
    assert not valid
    assert "Unsupported file extension" in reason


def test_file_integrity_gate_valid_file(tmp_path: Path):
    gate = FileIntegrityGate()
    good_file = tmp_path / "notes.md"
    good_file.write_text("# Medical Clinical Trial")
    valid, reason, size = gate.check_integrity(good_file)
    assert valid
    assert size > 0


@pytest.mark.asyncio
async def test_file_integrity_gate_stability(tmp_path: Path):
    gate = FileIntegrityGate()
    test_file = tmp_path / "stable.txt"
    test_file.write_text("Stable content")
    # File already has size, second check sees identical size -> stable
    is_stable = await gate.wait_for_stability(test_file, check_interval=0.1, max_wait_seconds=1.0)
    assert is_stable


def test_domain_filter_healthtech_classification():
    d_filter = DomainFilter()
    domain, conf = d_filter.classify_text("Patient clinical trial with oncology medication dosage", "patient_ehr.pdf")
    assert domain == "healthtech"
    assert conf > 0.3


def test_domain_filter_fintech_classification():
    d_filter = DomainFilter()
    domain, conf = d_filter.classify_text("Ledger quarterly revenue invoice and transaction settlement", "q3_audit.csv")
    assert domain == "fintech"
    assert conf > 0.3


def test_domain_filter_edtech_classification():
    d_filter = DomainFilter()
    domain, conf = d_filter.classify_text("Student curriculum syllabus and semester exam grading", "course_outline.docx")
    assert domain == "edtech"
    assert conf > 0.3


def test_domain_filter_enterprise_ops_classification():
    d_filter = DomainFilter()
    domain, conf = d_filter.classify_text("Kubernetes cluster deployment pod latency and Prometheus alerts", "incident_rca.md")
    assert domain == "enterprise_ops"
    assert conf > 0.3


def test_domain_filter_fallback_on_empty():
    d_filter = DomainFilter(default_domain="healthtech")
    domain, conf = d_filter.classify_text("", "unknown.txt")
    assert domain == "healthtech"
    assert conf == 0.0


def test_domain_filter_evaluate_file(tmp_path: Path):
    d_filter = DomainFilter()
    sample = tmp_path / "patient_discharge.txt"
    sample.write_text("Patient John Doe discharged after successful cardiology diagnosis and treatment.")
    res: FilterResult = d_filter.evaluate_file(sample)
    assert res.valid
    assert res.detected_domain == "healthtech"
    assert res.size_bytes > 0
