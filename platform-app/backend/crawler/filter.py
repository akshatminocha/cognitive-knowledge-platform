"""
Domain Relevance & File Integrity Gate.

Validates file integrity (non-zero size, MIME/format compatibility, debounce stability)
and classifies text/metadata into domain schemas (healthtech, fintech, edtech, enterprise_ops).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Supported file extensions for multimodal and text ingestion
SUPPORTED_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".csv", ".json", ".docx",
    ".pptx", ".png", ".jpg", ".jpeg", ".mp3", ".wav", ".mp4",
}

# Domain keyword taxonomy for fast heuristic classification
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "healthtech": [
        "patient", "clinical", "diagnosis", "symptom", "treatment", "medication",
        "doctor", "hospital", "dosage", "oncology", "cardiology", "biomarker",
        "prescription", "ehr", "emr", "trial", "pathology", "vital", "blood",
        "adverse event", "physician", "radiology", "therapy",
    ],
    "fintech": [
        "transaction", "account", "balance", "ledger", "invoice", "payment",
        "credit", "debit", "portfolio", "asset", "equity", "dividend", "yield",
        "interest", "audit", "fraud", "settlement", "revenue", "quarterly", "finra",
        "sec filing", "treasury", "liquidity", "tax",
    ],
    "edtech": [
        "student", "course", "curriculum", "syllabus", "exam", "grade",
        "instructor", "lecture", "faculty", "enrollment", "assignment",
        "degree", "semester", "academic", "scholarship", "pedagogy", "accreditation",
    ],
    "enterprise_ops": [
        "incident", "kubernetes", "k8s", "cluster", "deployment", "service",
        "latency", "uptime", "downtime", "sla", "slo", "devops", "container",
        "docker", "pipeline", "outage", "firewall", "cpu", "memory", "grafana",
        "prometheus", "telemetry", "pod", "node",
    ],
}


@dataclass
class FilterResult:
    """Result from evaluating file integrity and domain relevance."""
    valid: bool
    detected_domain: str
    confidence: float
    file_type: str
    size_bytes: int
    reason: str = ""
    metadata: Optional[dict] = None


class FileIntegrityGate:
    """Validates physical file integrity and write completion."""

    def __init__(
        self,
        max_size_bytes: int = 200 * 1024 * 1024,  # 200 MB
        allowed_extensions: Optional[set[str]] = None,
    ) -> None:
        self.max_size_bytes = max_size_bytes
        self.allowed_extensions = allowed_extensions or SUPPORTED_EXTENSIONS

    def check_integrity(self, file_path: Path) -> tuple[bool, str, int]:
        """
        Check if file exists, is non-empty, within size bounds, and has supported extension.
        Returns: (is_valid, reason, size_bytes)
        """
        if not file_path.exists():
            return False, f"File does not exist: {file_path}", 0

        if not file_path.is_file():
            return False, f"Path is not a regular file: {file_path}", 0

        try:
            size = file_path.stat().st_size
        except OSError as e:
            return False, f"Failed to read file stat: {e}", 0

        if size == 0:
            return False, "File is empty (0 bytes)", 0

        if size > self.max_size_bytes:
            return False, f"File exceeds maximum size limit ({size} > {self.max_size_bytes} bytes)", size

        ext = file_path.suffix.lower()
        if ext not in self.allowed_extensions:
            return False, f"Unsupported file extension: {ext}", size

        return True, "Integrity check passed", size

    async def wait_for_stability(
        self,
        file_path: Path,
        check_interval: float = 0.5,
        max_wait_seconds: float = 5.0,
    ) -> bool:
        """
        Debounce file writes: ensures file size is stable before ingestion triggers.
        Returns True if stable, False if file keeps changing or disappears.
        """
        start_time = asyncio.get_event_loop().time()
        last_size = -1

        while (asyncio.get_event_loop().time() - start_time) < max_wait_seconds:
            if not file_path.exists():
                return False
            try:
                current_size = file_path.stat().st_size
                if current_size > 0 and current_size == last_size:
                    return True
                last_size = current_size
            except OSError:
                pass
            await asyncio.sleep(check_interval)

        return last_size > 0


class DomainFilter:
    """Fast heuristic classifier for domain schema assignment."""

    def __init__(
        self,
        default_domain: str = "healthtech",
        min_confidence: float = 0.15,
        allowed_domains: Optional[list[str]] = None,
    ) -> None:
        self.default_domain = default_domain
        self.min_confidence = min_confidence
        self.allowed_domains = allowed_domains or list(DOMAIN_KEYWORDS.keys())

    def classify_text(self, text: str, filename: str = "") -> tuple[str, float]:
        """
        Classify text and filename hints into the best matching domain.
        Returns: (domain_name, confidence_score)
        """
        target = f"{filename} {text}".lower()
        scores: dict[str, int] = {dom: 0 for dom in self.allowed_domains}

        for domain, keywords in DOMAIN_KEYWORDS.items():
            if domain not in scores:
                continue
            for kw in keywords:
                # Fast regex whole-word match
                matches = len(re.findall(r"\b" + re.escape(kw) + r"\b", target))
                scores[domain] += matches

        total_matches = sum(scores.values())
        if total_matches == 0:
            return self.default_domain, 0.0

        best_domain = max(scores, key=lambda d: scores[d])
        confidence = round(scores[best_domain] / total_matches, 3)

        if confidence < self.min_confidence:
            return self.default_domain, confidence

        return best_domain, confidence

    def evaluate_file(self, file_path: Path, sample_bytes: int = 16384) -> FilterResult:
        """
        Read a sample of the file (or filename if binary) and produce a FilterResult.
        """
        gate = FileIntegrityGate()
        is_valid, reason, size = gate.check_integrity(file_path)
        ext = file_path.suffix.lstrip(".").lower()

        if not is_valid:
            return FilterResult(
                valid=False,
                detected_domain=self.default_domain,
                confidence=0.0,
                file_type=ext,
                size_bytes=size,
                reason=reason,
            )

        # Attempt to read text snippet for classification
        sample_text = ""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                sample_text = f.read(sample_bytes)
        except Exception:
            sample_text = ""

        domain, confidence = self.classify_text(sample_text, filename=file_path.name)

        return FilterResult(
            valid=True,
            detected_domain=domain,
            confidence=confidence,
            file_type=ext,
            size_bytes=size,
            reason="Validated and classified",
            metadata={"sample_length": len(sample_text)},
        )
