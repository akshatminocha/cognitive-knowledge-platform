"""
Data Protection — Dynamic PII/PHI/PCI masking using Microsoft Presidio.

Domain-aware entity detection with custom recognizers for:
- Healthtech: MRN, Insurance ID, ICD codes
- Fintech: IBAN, SWIFT, Credit Card, Account Numbers
- General: Email, Phone, SSN, DOB, Address

Uses reversible pseudonymization via TokenMap so original values can be
re-hydrated for authorized users.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from guardrails.config import CustomEntityPattern, DataProtectionConfig, DomainType
from guardrails.token_map import TokenMap

logger = logging.getLogger(__name__)

# Try to import Presidio — graceful fallback if not installed
try:
    from presidio_analyzer import (
        AnalyzerEngine,
        PatternRecognizer,
        Pattern,
        RecognizerResult,
    )
    from presidio_anonymizer import AnonymizerEngine

    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False
    logger.warning(
        "presidio-analyzer/presidio-anonymizer not installed. "
        "PII masking will use regex fallback only."
    )


# ---- Domain-Specific Entity Patterns ----

HEALTHTECH_PATTERNS: list[CustomEntityPattern] = [
    CustomEntityPattern(
        entity_type="MEDICAL_RECORD_NUMBER",
        patterns=[r"\bMRN[-:]?\s*\d{6,10}\b", r"\bMR[-#]\d{6,10}\b"],
        score=0.9,
        context_words=["mrn", "medical record", "patient id", "chart number"],
    ),
    CustomEntityPattern(
        entity_type="INSURANCE_ID",
        patterns=[r"\b[A-Z]{2,3}\d{8,12}\b"],
        score=0.7,
        context_words=["insurance", "policy", "member id", "subscriber", "coverage"],
    ),
    CustomEntityPattern(
        entity_type="ICD_CODE",
        patterns=[r"\b[A-TV-Z]\d{2}\.?\d{0,4}\b"],
        score=0.6,
        context_words=["icd", "diagnosis", "code", "icd-10", "icd-11"],
    ),
]

FINTECH_PATTERNS: list[CustomEntityPattern] = [
    CustomEntityPattern(
        entity_type="IBAN",
        patterns=[r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"],
        score=0.95,
        context_words=["iban", "account", "transfer", "wire"],
    ),
    CustomEntityPattern(
        entity_type="SWIFT_CODE",
        patterns=[r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b"],
        score=0.8,
        context_words=["swift", "bic", "bank", "routing"],
    ),
    CustomEntityPattern(
        entity_type="ACCOUNT_NUMBER",
        patterns=[r"\b\d{8,17}\b"],
        score=0.5,
        context_words=["account", "acct", "checking", "savings", "balance"],
    ),
]

DOMAIN_PATTERNS: dict[DomainType, list[CustomEntityPattern]] = {
    DomainType.HEALTHTECH: HEALTHTECH_PATTERNS,
    DomainType.FINTECH: FINTECH_PATTERNS,
    DomainType.EDTECH: [],  # Student IDs covered by general patterns
    DomainType.ADTECH: [],  # Device fingerprints handled separately
    DomainType.ENTERPRISE_OPS: [],
    DomainType.GENERAL: [],
}

# Default entities Presidio already detects
DEFAULT_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
    "US_SSN", "US_DRIVER_LICENSE", "DATE_TIME", "IP_ADDRESS",
    "LOCATION", "NRP", "MEDICAL_LICENSE", "URL",
]


class DataProtector:
    """
    PII/PHI/PCI detection and masking engine.

    Uses Presidio for NER-based detection with domain-specific custom
    recognizers, and a TokenMap for reversible pseudonymization.

    Usage:
        protector = DataProtector(config)
        masked_text, token_map = protector.mask_text(
            "Patient John Doe (MRN: 123456789) has diabetes."
        )
        # masked_text: "Patient [PERSON_1] (MRN: [MEDICAL_RECORD_NUMBER_1]) has diabetes."

        # Later, for authorized users:
        original = token_map.restore_text(masked_text)
    """

    def __init__(self, config: Optional[DataProtectionConfig] = None) -> None:
        self.config = config or DataProtectionConfig()
        self._analyzer: Optional[AnalyzerEngine] = None  # type: ignore[assignment]
        self._token_map = TokenMap(format=self.config.mask_format)
        self._fallback_patterns = self._build_fallback_patterns()

        if PRESIDIO_AVAILABLE:
            self._init_presidio()

    def _init_presidio(self) -> None:
        """Initialize Presidio analyzer with custom domain recognizers."""
        self._analyzer = AnalyzerEngine()

        # Add domain-specific custom recognizers
        domain_patterns = DOMAIN_PATTERNS.get(self.config.active_domain, [])
        all_custom = domain_patterns + self.config.custom_entities

        for entity_def in all_custom:
            patterns = [
                Pattern(
                    name=f"{entity_def.entity_type}_pattern_{i}",
                    regex=p,
                    score=entity_def.score,
                )
                for i, p in enumerate(entity_def.patterns)
            ]
            recognizer = PatternRecognizer(
                supported_entity=entity_def.entity_type,
                patterns=patterns,
                context=entity_def.context_words if entity_def.context_words else None,
            )
            self._analyzer.registry.add_recognizer(recognizer)
            logger.debug(f"Registered custom recognizer: {entity_def.entity_type}")

    def _build_fallback_patterns(self) -> list[tuple[str, re.Pattern]]:
        """Build regex fallback patterns for when Presidio is not available."""
        return [
            ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
            ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
            ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
            ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
            ("IP_ADDRESS", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
        ]

    def mask_text(self, text: str, token_map: Optional[TokenMap] = None) -> tuple[str, TokenMap]:
        """
        Detect and mask PII/PHI entities in the text.

        Returns (masked_text, token_map) where token_map enables re-hydration.
        """
        if not self.config.enabled:
            return text, token_map or TokenMap()

        tmap = token_map or TokenMap(format=self.config.mask_format)

        if PRESIDIO_AVAILABLE and self._analyzer is not None:
            return self._mask_with_presidio(text, tmap)
        else:
            return self._mask_with_regex(text, tmap)

    def _mask_with_presidio(self, text: str, token_map: TokenMap) -> tuple[str, TokenMap]:
        """Mask using Presidio NER engine."""
        results = self._analyzer.analyze(
            text=text,
            language="en",
            score_threshold=self.config.score_threshold,
        )

        # Sort by start position (reverse) to replace from end to start
        results = sorted(results, key=lambda r: r.start, reverse=True)

        masked = text
        for result in results:
            original_value = text[result.start : result.end]
            token = token_map.mask(original_value, result.entity_type)
            masked = masked[: result.start] + token + masked[result.end :]

        return masked, token_map

    def _mask_with_regex(self, text: str, token_map: TokenMap) -> tuple[str, TokenMap]:
        """Fallback masking using regex patterns."""
        masked = text
        for entity_type, pattern in self._fallback_patterns:
            for match in reversed(list(pattern.finditer(masked))):
                original_value = match.group()
                token = token_map.mask(original_value, entity_type)
                masked = masked[: match.start()] + token + masked[match.end() :]

        return masked, token_map

    def detect_entities(self, text: str) -> list[dict]:
        """
        Detect PII entities without masking. Returns a list of findings.
        Useful for UI display or audit logging.
        """
        if not PRESIDIO_AVAILABLE or self._analyzer is None:
            return []

        results = self._analyzer.analyze(
            text=text,
            language="en",
            score_threshold=self.config.score_threshold,
        )
        return [
            {
                "entity_type": r.entity_type,
                "start": r.start,
                "end": r.end,
                "score": round(r.score, 3),
                "value": text[r.start : r.end],
            }
            for r in results
        ]
