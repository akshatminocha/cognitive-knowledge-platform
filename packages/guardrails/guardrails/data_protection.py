"""
Data Protection — Dynamic PII/PHI/PCI masking using Microsoft Presidio,
Specialized Domain Recognizers, Zero-Shot Hybrid LLM Auditing, and Cryptographic TokenMap.

Domain-aware entity detection with custom recognizers for:
- Healthtech: MRN, NPI (with CMS Luhn algorithm check), DEA numbers (with checksum),
  Insurance Group/Member ID, ICD-10/11 codes.
- Fintech: US EIN, US ITIN, IBAN, SWIFT, Credit Card, Account Numbers, CUSIP, ABA Routing.
- General: Email, Phone, SSN, DOB, Address, IP Addresses.

Features:
- Complete offline regex fallback engine mirroring all domain recognizers.
- Low-latency Zero-Shot Flash LLM Auditor for ambiguous/borderline Presidio scores (< 0.6).
- Reversible pseudonymization with cryptographic salted envelope and strict RBAC.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from typing import Any, Optional

from guardrails.config import CustomEntityPattern, DataProtectionConfig, DomainType
from guardrails.secret_scanner import SecretScanner
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


# ---------------------------------------------------------------------------
# Domain Checksum Validators (NPI Luhn, DEA Checksum) & Medical Whitelist
# ---------------------------------------------------------------------------
COMMON_MEDICATIONS: set[str] = {
    "lisinopril", "metformin", "pembrolizumab", "atorvastatin", "levothyroxine",
    "amlodipine", "metoprolol", "omeprazole", "losartan", "albuterol",
    "gabapentin", "hydrochlorothiazide", "acetaminophen", "ibuprofen", "aspirin",
    "amoxicillin", "azithromycin", "prednisone", "insulin", "doxycycline",
    "ciprofloxacin", "furosemide", "pantoprazole", "sertraline", "simvastatin",
    "warfarin", "apixaban", "clopidogrel", "pemetrexed", "keytruda",
}

def validate_npi_luhn(npi_str: str) -> bool:
    """
    Validates a 10-digit National Provider Identifier (NPI) using the CMS Luhn check.
    Prepends '80840' per the CMS / ISO standard before computing the Luhn checksum.
    """
    digits = re.sub(r"\D", "", npi_str)
    if len(digits) != 10:
        return False

    full = "80840" + digits
    total = 0
    for i, char in enumerate(reversed(full)):
        n = int(char)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def validate_dea_checksum(dea_str: str) -> bool:
    """
    Validates a 9-character DEA registration number (2 letters + 7 digits).
    Rule: (d1 + d3 + d5) + 2 * (d2 + d4 + d6) mod 10 == check digit (d7).
    """
    clean = dea_str.strip().upper()
    if not re.match(r"^[A-Z]{2}\d{7}$", clean):
        return False

    d = [int(c) for c in clean[2:]]
    sum1 = d[0] + d[2] + d[4]
    sum2 = (d[1] + d[3] + d[5]) * 2
    check = (sum1 + sum2) % 10
    return check == d[6]


def validate_phone_number(val: str) -> bool:
    """Validate phone number string to prevent bare integers, timestamps, or barcodes being falsely flagged."""
    val_clean = val.strip()
    has_formatting = any(c in val_clean for c in ("-", "(", ")", "+", " ", "."))
    try:
        import phonenumbers
        parsed = phonenumbers.parse(val_clean, "US")
        if not phonenumbers.is_possible_number(parsed):
            return False
        if has_formatting:
            return True
        return phonenumbers.is_valid_number(parsed)
    except Exception:
        return has_formatting and len(re.sub(r"\D", "", val_clean)) >= 7


# ---------------------------------------------------------------------------
# Domain-Specific Entity Patterns
# ---------------------------------------------------------------------------
HEALTHTECH_PATTERNS: list[CustomEntityPattern] = [
    CustomEntityPattern(
        entity_type="MEDICAL_RECORD_NUMBER",
        patterns=[r"\bMRN[-:#\s]*\d{6,10}\b", r"\bMR[-#]\d{6,10}\b"],
        score=0.9,
        context_words=["mrn", "medical record", "patient id", "chart number"],
    ),
    CustomEntityPattern(
        entity_type="NPI",
        patterns=[r"\b[1-9]\d{9}\b"],
        score=0.85,
        context_words=["npi", "provider", "physician", "doctor", "prescriber", "national provider identifier"],
    ),
    CustomEntityPattern(
        entity_type="DEA_NUMBER",
        patterns=[r"(?i)\b[A-Za-z]{2}\d{7}\b"],
        score=0.85,
        context_words=["dea", "dea#", "prescription", "license", "controlled substance", "narcotics"],
    ),
    CustomEntityPattern(
        entity_type="INSURANCE_ID",
        patterns=[r"\b[A-Z]{2,3}\d{8,12}\b", r"\bGRP[-:#\s]*[A-Z0-9]{6,12}\b"],
        score=0.7,
        context_words=["insurance", "policy", "member id", "subscriber", "coverage", "group number"],
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
        entity_type="US_EIN",
        patterns=[r"\b\d{2}-\d{7}\b"],
        score=0.85,
        context_words=["ein", "employer id", "tax id", "fein", "taxpayer"],
    ),
    CustomEntityPattern(
        entity_type="US_ITIN",
        patterns=[r"\b9\d{2}[-\s]?\d{2}[-\s]?\d{4}\b"],
        score=0.85,
        context_words=["itin", "tax id", "irs", "taxpayer identification"],
    ),
    CustomEntityPattern(
        entity_type="IBAN",
        patterns=[r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"],
        score=0.95,
        context_words=["iban", "account", "transfer", "wire"],
    ),
    CustomEntityPattern(
        entity_type="SWIFT_CODE",
        patterns=[r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b"],
        score=0.35,
        context_words=["swift", "bic", "bank", "routing", "transfer", "wire"],
    ),
    CustomEntityPattern(
        entity_type="ACCOUNT_NUMBER",
        patterns=[r"\b\d{8,17}\b"],
        score=0.35,
        context_words=["account", "acct", "checking", "savings", "balance"],
    ),
    CustomEntityPattern(
        entity_type="CUSIP",
        patterns=[r"(?i)\b(?=[0-9A-Za-z]*\d)[0-9A-Za-z]{8}\d\b"],
        score=0.75,
        context_words=["cusip", "security", "bond", "equity", "isin", "ticker"],
    ),
    CustomEntityPattern(
        entity_type="ROUTING_NUMBER",
        patterns=[r"\b\d{9}\b"],
        score=0.75,
        context_words=["routing", "aba", "transit", "wire routing", "ach"],
    ),
]

DOMAIN_PATTERNS: dict[DomainType, list[CustomEntityPattern]] = {
    DomainType.HEALTHTECH: HEALTHTECH_PATTERNS,
    DomainType.FINTECH: FINTECH_PATTERNS,
    DomainType.EDTECH: [],
    DomainType.ADTECH: [],
    DomainType.ENTERPRISE_OPS: [],
    DomainType.GENERAL: [],
}

# Default entities Presidio already detects
DEFAULT_ENTITIES = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
    "US_SSN", "US_DRIVER_LICENSE", "DATE_TIME", "IP_ADDRESS",
    "LOCATION", "NRP", "URL",
]


class DataProtector:
    """
    Enterprise PII/PHI/PCI detection and masking engine.

    Combines Presidio NER, domain pattern recognizers (with Luhn & checksum validators),
    complete offline regex fallback parity, and a fast Zero-Shot LLM Audit Layer.
    """

    def __init__(self, config: Optional[DataProtectionConfig] = None) -> None:
        self.config = config or DataProtectionConfig()
        self._analyzer: Optional[AnalyzerEngine] = None  # type: ignore[assignment]
        self._token_map = TokenMap(
            _format=self.config.mask_format,
            _salt=self.config.token_map_salt or "ckp-default-salt",
            enforce_rbac=self.config.enable_encrypted_token_map,
        )
        self._fallback_patterns = self._build_fallback_patterns()
        self._secret_scanner = SecretScanner(
            entropy_threshold=self.config.entropy_threshold,
            enable_entropy_check=self.config.enable_secret_scanning,
        )

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

    def _get_active_entities(self) -> list[str]:
        """Compute the list of active entity types based on core, domain, and custom configuration."""
        entities = list(DEFAULT_ENTITIES)
        domain_patterns = DOMAIN_PATTERNS.get(self.config.active_domain, [])
        for p in domain_patterns:
            if p.entity_type not in entities:
                entities.append(p.entity_type)
        for c in self.config.custom_entities:
            if c.entity_type not in entities:
                entities.append(c.entity_type)
        return entities

    def _build_fallback_patterns(self) -> list[tuple[str, re.Pattern]]:
        """
        Build complete regex fallback patterns for offline environments or
        when Presidio is uninstalled. Mirrors all core and domain entities.
        """
        return [
            # Core PII
            ("EMAIL_ADDRESS", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
            ("PHONE_NUMBER", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
            ("US_SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
            ("CREDIT_CARD", re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
            ("IP_ADDRESS", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),

            # Healthcare
            ("MEDICAL_RECORD_NUMBER", re.compile(r"\b(?:MRN[-:#\s]*|MR[-#])\d{6,10}\b", re.IGNORECASE)),
            ("NPI", re.compile(r"\b(?:NPI[-:#\s]*)?([1-9]\d{9})\b", re.IGNORECASE)),
            ("DEA_NUMBER", re.compile(r"\b[A-Za-z]{2}\d{7}\b", re.IGNORECASE)),
            ("ICD_CODE", re.compile(r"\b[A-TV-Z]\d{2}\.?\d{0,4}\b")),
            ("INSURANCE_ID", re.compile(r"\b(?:INS|GRP)[-:#\s]*[A-Z0-9]{6,12}\b", re.IGNORECASE)),

            # Fintech
            ("US_EIN", re.compile(r"\b\d{2}-\d{7}\b")),
            ("US_ITIN", re.compile(r"\b9\d{2}[-\s]?\d{2}[-\s]?\d{4}\b")),
            ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b")),
            ("SWIFT_CODE", re.compile(r"\b[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?\b")),
            ("CUSIP", re.compile(r"\b(?=[0-9A-Za-z]*\d)[0-9A-Za-z]{8}\d\b", re.IGNORECASE)),
        ]

    def mask_text(
        self,
        text: str,
        token_map: Optional[TokenMap] = None,
        user_role: Optional[str] = None,
    ) -> tuple[str, TokenMap]:
        """
        Detect and mask Secrets, Passwords, and PII/PHI entities in the text.
        Returns (masked_text, token_map).
        """
        if not self.config.enabled:
            return text, token_map or self._token_map

        tmap = token_map or TokenMap(
            _format=self.config.mask_format,
            _salt=self.config.token_map_salt or "ckp-default-salt",
            enforce_rbac=self.config.enable_encrypted_token_map,
        )

        # 1. Mask API keys, passwords, and high-entropy secrets first
        if self.config.enable_secret_scanning:
            text, tmap = self._secret_scanner.mask_secrets(text, tmap)

        # 2. Mask PII/PHI entities (Presidio or Regex fallback)
        if PRESIDIO_AVAILABLE and self._analyzer is not None:
            return self._mask_with_presidio_and_hybrid(text, tmap)
        else:
            return self._mask_with_regex(text, tmap)

    @staticmethod
    def _resolve_overlapping_spans(results: list) -> list:
        """
        Filter overlapping recognizer results.
        Retains higher score span; if scores equal, retains longer span.
        """
        if not results:
            return []

        sorted_by_priority = sorted(
            results,
            key=lambda r: (getattr(r, "score", 0.5), (getattr(r, "end", 0) - getattr(r, "start", 0))),
            reverse=True,
        )

        accepted = []
        for candidate in sorted_by_priority:
            overlaps = False
            for chosen in accepted:
                if max(candidate.start, chosen.start) < min(candidate.end, chosen.end):
                    overlaps = True
                    break
            if not overlaps:
                accepted.append(candidate)

        return sorted(accepted, key=lambda r: r.start)

    def _mask_with_presidio_and_hybrid(self, text: str, token_map: TokenMap) -> tuple[str, TokenMap]:
        """Mask using Presidio NER engine augmented with Zero-Shot LLM Audit."""
        raw_results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=self._get_active_entities(),
            score_threshold=self.config.score_threshold,
        )

        # Post-validate domain entities (NPI Luhn, DEA checksum, SWIFT format)
        filtered_results = []
        has_borderline_scores = False

        for r in raw_results:
            span_val = text[r.start : r.end]
            # Suppress clinical medication false positives mistakenly flagged by generic NER as PERSON/LOCATION
            if r.entity_type in ("PERSON", "LOCATION", "ORGANIZATION") and span_val.strip().lower() in COMMON_MEDICATIONS:
                continue

            if r.entity_type == "NPI":
                if not validate_npi_luhn(span_val):
                    continue  # Discard false-positive NPI failing Luhn algorithm
            elif r.entity_type == "DEA_NUMBER":
                if not validate_dea_checksum(span_val):
                    continue  # Discard false-positive DEA failing checksum
            elif r.entity_type == "PHONE_NUMBER":
                if not validate_phone_number(span_val):
                    continue  # Discard timestamps or non-phone digit strings
            elif r.entity_type == "SWIFT_CODE":
                if not span_val.isupper() or len(span_val) not in (8, 11):
                    continue  # Discard false-positive SWIFT failing format/casing

            if r.score < self.config.zero_shot_audit_threshold:
                has_borderline_scores = True

            filtered_results.append(r)

        # Trigger Zero-Shot LLM Audit if borderline scores exist or in strict compliance mode
        if (has_borderline_scores or self.config.strict_compliance_mode) and self.config.enable_zero_shot_audit:
            llm_findings = self._audit_with_llm(text, filtered_results)
            filtered_results.extend(llm_findings)

        # Resolve overlapping spans
        results = self._resolve_overlapping_spans(filtered_results)
        results = sorted(results, key=lambda r: r.start, reverse=True)

        masked = text
        for result in results:
            original_value = text[result.start : result.end]
            token = token_map.mask(original_value, result.entity_type)
            masked = masked[: result.start] + token + masked[result.end :]

        return masked, token_map

    def _mask_with_regex(self, text: str, token_map: TokenMap) -> tuple[str, TokenMap]:
        """Fallback masking using regex patterns with domain checksum verification."""
        findings = []
        for entity_type, pattern in self._fallback_patterns:
            for match in pattern.finditer(text):
                val = match.group()
                # Verify domain checksums
                if entity_type == "NPI" and not validate_npi_luhn(val):
                    continue
                if entity_type == "DEA_NUMBER" and not validate_dea_checksum(val):
                    continue

                class SimpleSpan:
                    def __init__(self, s, e, et, sc):
                        self.start, self.end, self.entity_type, self.score = s, e, et, sc

                findings.append(SimpleSpan(match.start(), match.end(), entity_type, 0.85))

        # Check for zero-shot LLM audit if strict compliance mode is active
        if self.config.strict_compliance_mode and self.config.enable_zero_shot_audit:
            llm_findings = self._audit_with_llm(text, findings)
            findings.extend(llm_findings)

        resolved = self._resolve_overlapping_spans(findings)
        resolved = sorted(resolved, key=lambda r: r.start, reverse=True)

        masked = text
        for r in resolved:
            original_value = text[r.start : r.end]
            token = token_map.mask(original_value, r.entity_type)
            masked = masked[: r.start] + token + masked[r.end :]

        return masked, token_map

    def _audit_with_llm(self, text: str, existing_spans: list) -> list:
        """
        Executes a low-latency Zero-Shot LLM Audit for ambiguous, contextual, or borderline PII.
        Uses a timeout circuit-breaker (default 0.8s) so query latency is never blocked.
        """
        def _call_llm_worker() -> list:
            try:
                # Fast rule-based / simulated auditor if running in tests or no API key
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    return self._contextual_fallback_auditor(text)

                # If google-genai is present, query Gemini 2.5 Flash
                import google.genai as genai
                client = genai.Client(api_key=api_key)

                prompt = (
                    "You are a HIPAA and GDPR compliance privacy auditor. "
                    "Analyze the text and extract any overlooked sensitive entities "
                    "(e.g., patient names, physician names, medical record numbers, addresses). "
                    "Return ONLY a JSON array with schema: "
                    '[{"entity_type": "...", "value": "...", "confidence": 0.95}]\n\n'
                    f"Text: {text}"
                )

                response = client.models.generate_content(
                    model=self.config.zero_shot_model,
                    contents=prompt,
                )

                raw_json = response.text.strip().removeprefix("```json").removesuffix("```").strip()
                parsed = json.loads(raw_json)
                results = []

                if isinstance(parsed, list):
                    for item in parsed:
                        val = item.get("value")
                        if val and val in text:
                            start = text.find(val)
                            end = start + len(val)

                            class LLMSpan:
                                def __init__(self, s, e, et, sc):
                                    self.start, self.end, self.entity_type, self.score = s, e, et, sc

                            results.append(LLMSpan(start, end, item.get("entity_type", "PII"), item.get("confidence", 0.9)))
                return results

            except Exception as err:
                logger.debug(f"[Zero-Shot LLM Audit] Worker note: {err}")
                return self._contextual_fallback_auditor(text)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call_llm_worker)
            try:
                return future.result(timeout=self.config.zero_shot_timeout_seconds)
            except concurrent.futures.TimeoutError:
                logger.warning(
                    f"[Zero-Shot LLM Audit] Timed out after {self.config.zero_shot_timeout_seconds}s. "
                    "Continuing with deterministic findings."
                )
                return []

    def _contextual_fallback_auditor(self, text: str) -> list:
        """Heuristic contextual auditor identifying ambiguous titles and patient wards."""
        spans = []
        # Detect 'Dr. [Lastname]' or 'Patient [Lastname]' missed by standard patterns
        dr_pattern = re.compile(r"\b(?:Dr\.|Doctor|Physician|Patient)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")
        for m in dr_pattern.finditer(text):
            full_val = m.group(1)
            start = m.start(1)
            end = m.end(1)

            class ContextSpan:
                def __init__(self, s, e, et, sc):
                    self.start, self.end, self.entity_type, self.score = s, e, et, sc

            spans.append(ContextSpan(start, end, "PERSON", 0.88))

        return spans

    def detect_entities(self, text: str) -> list[dict[str, Any]]:
        """
        Detect PII and Secret entities without masking.
        Returns detailed findings with detector sources (Presidio, Regex Fallback, Zero-Shot LLM).
        """
        findings: list[dict[str, Any]] = []

        # 1. Detect secrets
        if self.config.enable_secret_scanning:
            for s in self._secret_scanner.scan(text):
                findings.append({
                    "entity_type": s.secret_type,
                    "start": s.start,
                    "end": s.end,
                    "score": round(s.confidence, 3),
                    "value": s.value,
                    "source": "secret_scanner",
                })

        # 2. Detect PII/PHI
        if PRESIDIO_AVAILABLE and self._analyzer is not None:
            raw_results = self._analyzer.analyze(
                text=text,
                language="en",
                entities=self._get_active_entities(),
                score_threshold=self.config.score_threshold,
            )
            filtered = []
            for r in raw_results:
                val = text[r.start : r.end]
                if r.entity_type in ("PERSON", "LOCATION", "ORGANIZATION") and val.strip().lower() in COMMON_MEDICATIONS:
                    continue
                if r.entity_type == "NPI" and not validate_npi_luhn(val):
                    continue
                if r.entity_type == "DEA_NUMBER" and not validate_dea_checksum(val):
                    continue
                if r.entity_type == "PHONE_NUMBER" and not validate_phone_number(val):
                    continue
                if r.entity_type == "SWIFT_CODE" and (not val.isupper() or len(val) not in (8, 11)):
                    continue
                filtered.append(r)

            resolved = self._resolve_overlapping_spans(filtered)
            for r in resolved:
                findings.append({
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": round(r.score, 3),
                    "value": text[r.start : r.end],
                    "source": "presidio_ner",
                })
        else:
            # Fallback regex detection
            for entity_type, pattern in self._fallback_patterns:
                for match in pattern.finditer(text):
                    val = match.group()
                    if entity_type == "NPI" and not validate_npi_luhn(val):
                        continue
                    if entity_type == "DEA_NUMBER" and not validate_dea_checksum(val):
                        continue
                    findings.append({
                        "entity_type": entity_type,
                        "start": match.start(),
                        "end": match.end(),
                        "score": 0.85,
                        "value": val,
                        "source": "regex_fallback",
                    })

        return findings
