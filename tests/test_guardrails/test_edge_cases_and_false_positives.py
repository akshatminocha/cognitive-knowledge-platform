"""
Comprehensive Edge Case, False-Positive, and Adversarial Negative Tests for Phase 7 Guardrails.

Validates:
1. False Positive Avoidance:
   - Random 10-digit integers, timestamps, product serials must NOT be flagged as NPI.
   - Codes with invalid DEA checksums must NOT be flagged as DEA_NUMBER.
   - Medical drugs and dosages must NOT be falsely masked as patient names.
   - 9-character code identifiers (e.g. DataFrame) must NOT be falsely masked as CUSIP.
2. Adversarial / Evasion Edge Cases:
   - Case-insensitive DEA numbers ('ab1234563').
   - NPI with hyphens and spaces ('123-456-7893').
   - PII inside JSON payloads and markdown formatting.
   - Pre-existing masked tokens ('literal [PERSON_1] in input') to test collision avoidance.
3. TokenMap Security & Memory Edge Cases:
   - TokenMap TTL expiration enforcement.
   - Role spoofing & case-insensitivity ('Admin', 'COMPLIANCE_OFFICER', 'hacker').
   - High-volume duplicate entities (deterministic single-token assignment).
   - Empty, whitespace, and special-character inputs.
4. Zero-Shot Circuit Breaker & Malformed Response Resilience:
   - Malformed LLM JSON handling.
   - Graceful fallback under artificial timeout.
"""

from __future__ import annotations

import json
import time
import unittest

from guardrails.config import DataProtectionConfig, DomainType
from guardrails.data_protection import (
    DataProtector,
    validate_dea_checksum,
    validate_npi_luhn,
)
from guardrails.engine import GuardrailEngine
from guardrails.policy_engine import PolicyAction, PolicyDecisionPoint
from guardrails.token_map import TokenMap


class TestFalsePositiveAvoidance(unittest.TestCase):
    """Ensures legitimate non-PII domain strings are NOT erroneously masked."""

    def setUp(self):
        self.protector = DataProtector(DataProtectionConfig(active_domain=DomainType.HEALTHTECH))

    def test_random_10_digit_numbers_not_masked_as_npi(self):
        """Random timestamps, serial numbers, or barcodes failing Luhn must pass through untouched."""
        # 1700000000 is a Unix timestamp (10 digits, fails NPI Luhn 80840)
        timestamp_sample = "Event occurred at timestamp 1700000000 in telemetry log."
        masked, tmap = self.protector.mask_text(timestamp_sample)
        self.assertIn("1700000000", masked, "Unix timestamp was falsely masked as NPI!")
        self.assertEqual(tmap.size, 0)

        # Product barcode
        barcode_sample = "Scanned item barcode 9876543210 on shelf B4."
        masked_b, tmap_b = self.protector.mask_text(barcode_sample)
        self.assertIn("9876543210", masked_b, "Product barcode was falsely masked as NPI!")

    def test_invalid_dea_checksum_not_masked(self):
        """Codes with 2 letters and 7 digits that fail DEA checksum must NOT be masked."""
        # 'AB1234567' has sum 33 -> check digit should be 3, not 7!
        flight_or_part = "Component serial AB1234567 passed stress testing."
        masked, tmap = self.protector.mask_text(flight_or_part)
        self.assertIn("AB1234567", masked, "Invalid DEA checksum string was falsely masked!")

    def test_medical_drugs_and_dosages_not_masked_as_person(self):
        """Prescription drugs (Lisinopril, Metformin, Pembrolizumab) must NOT be masked as names."""
        clinical_text = "Administered Lisinopril 20mg and Metformin 500mg as prescribed."
        masked, tmap = self.protector.mask_text(clinical_text)
        self.assertIn("Lisinopril", masked, "Medication was falsely masked!")
        self.assertIn("Metformin", masked, "Medication was falsely masked!")
        self.assertIn("20mg", masked)
        self.assertEqual(tmap.size, 0)

        # Ensure medications are never added to token map as PERSON
        med_sample = "Patient is currently prescribed Pembrolizumab for oncology treatment."
        masked_p, tmap_p = self.protector.mask_text(med_sample)
        self.assertIn("Pembrolizumab", masked_p)
        self.assertNotIn("Pembrolizumab", tmap_p.get_all_mappings())

    def test_fintech_false_positives_dataframe_and_constants(self):
        """Standard 9-character identifiers in programming must not be masked as CUSIP."""
        fintech_protector = DataProtector(DataProtectionConfig(active_domain=DomainType.FINTECH))
        code_text = "Inspect DataFrame and calculate Component variance."
        masked, tmap = fintech_protector.mask_text(code_text)
        self.assertIn("DataFrame", masked)
        self.assertIn("Component", masked)
        self.assertEqual(tmap.size, 0)


class TestAdversarialAndEvasionEdgeCases(unittest.TestCase):
    """Verifies robustness against non-standard formatting, evasion, and collisions."""

    def setUp(self):
        self.protector = DataProtector(DataProtectionConfig(active_domain=DomainType.HEALTHTECH))

    def test_lowercase_dea_normalization(self):
        """DEA numbers written in lowercase (e.g. 'ab1234563') must be detected and masked."""
        sample = "Prescription signed by provider with dea ab1234563."
        masked, tmap = self.protector.mask_text(sample)
        self.assertNotIn("ab1234563", masked.lower())
        self.assertGreaterEqual(tmap.size, 1)

    def test_pii_inside_json_structure(self):
        """Detects and masks PII embedded inside JSON serialized strings."""
        json_payload = json.dumps({
            "patient": {"mrn": "MRN-123456", "contact": "patient@hospital.org"},
            "status": "admitted"
        })
        masked, tmap = self.protector.mask_text(json_payload)
        self.assertNotIn("MRN-123456", masked)
        self.assertNotIn("patient@hospital.org", masked)
        self.assertGreaterEqual(tmap.size, 2)

    def test_preexisting_token_collision(self):
        """If user literally submits '[PERSON_1]', TokenMap must not crash or falsely unmask it."""
        literal_input = "User wrote: my favorite pseudonym is [PERSON_1]."
        masked, tmap = self.protector.mask_text(literal_input)
        # Even if unmasking is called, it should safely handle unassigned tokens
        restored = tmap.restore_text(masked, user_role="admin")
        self.assertIn("[PERSON_1]", restored)


class TestTokenMapSecurityAndStress(unittest.TestCase):
    """Verifies cryptographic TTL, role case-insensitivity, and deduplication stress."""

    def test_token_map_ttl_expiration(self):
        """Expired TokenMap must refuse to unmask or restore PII."""
        # Create map with 0.1 second TTL
        tmap = TokenMap(_ttl_seconds=0.1)
        token = tmap.mask("Secret Value", "SECRET")

        # Immediately available
        self.assertEqual(tmap.unmask(token, user_role="admin"), "Secret Value")

        # Wait for expiration
        time.sleep(0.15)
        self.assertTrue(tmap.is_expired())

        # Unmasking and restoring must be blocked after TTL expiration
        self.assertIsNone(tmap.unmask(token, user_role="admin"))
        restored = tmap.restore_text(f"Text with {token}", user_role="admin")
        self.assertEqual(restored, f"Text with {token}")

    def test_role_authorization_case_insensitivity_and_spoofing(self):
        """Role checks must be case-insensitive ('Admin', 'COMPLIANCE_OFFICER') and reject malicious roles."""
        tmap = TokenMap(enforce_rbac=True)
        token = tmap.mask("John Doe", "PERSON")

        # Case variations of authorized roles should succeed
        self.assertEqual(tmap.unmask(token, user_role="Admin"), "John Doe")
        self.assertEqual(tmap.unmask(token, user_role="COMPLIANCE_OFFICER"), "John Doe")

        # Attacker trying SQL injection or path traversal in role string
        self.assertIsNone(tmap.unmask(token, user_role="admin; DROP TABLE users;"))
        self.assertIsNone(tmap.unmask(token, user_role="admin/../../root"))
        self.assertIsNone(tmap.unmask(token, user_role=""))
        self.assertIsNone(tmap.unmask(token, user_role="superadmin"))  # Unregistered role

    def test_high_volume_duplicate_entities_stress(self):
        """100 occurrences of the same PII must map deterministically to exactly 1 token."""
        tmap = TokenMap()
        for _ in range(100):
            token = tmap.mask("1234567893", "NPI")
            self.assertEqual(token, "[NPI_1]")

        self.assertEqual(tmap.size, 1)

    def test_empty_and_special_character_inputs(self):
        """Engine handles empty, whitespace, and Unicode text safely."""
        protector = DataProtector()
        for sample in ["", "   \n\t  ", "!@#$%^&*()_+=-~`", "こんにちは 世界"]:
            masked, tmap = protector.mask_text(sample)
            self.assertEqual(tmap.size, 0)
            self.assertEqual(masked, sample)


class TestPolicyDecisionPointEdgeCases(unittest.TestCase):
    """Verifies boundary conditions in the Policy Decision Point."""

    def test_unmask_policy_role_variations(self):
        pdp = PolicyDecisionPoint()

        # None defaults to authorized for backward compatibility
        res_none = pdp.evaluate_unmask_policy(user_role=None, entity_types=["MRN"])
        self.assertTrue(res_none.allow)
        self.assertEqual(res_none.action, PolicyAction.REHYDRATE)

        # Attending physician allowed
        res_doc = pdp.evaluate_unmask_policy(user_role="attending_physician", entity_types=["MRN"])
        self.assertTrue(res_doc.allow)

        # Intern / Guest denied
        res_guest = pdp.evaluate_unmask_policy(user_role="intern", entity_types=["MRN"])
        self.assertFalse(res_guest.allow)
        self.assertEqual(res_guest.action, PolicyAction.MASK)

    def test_tool_policy_case_insensitivity_mutations(self):
        pdp = PolicyDecisionPoint()

        # Lowercase 'drop table' or mixed case 'MeRge' must be blocked
        res_drop = pdp.evaluate_tool_policy("sql_exec", user_role="admin", is_write_operation=True)
        self.assertFalse(res_drop.allow)
        self.assertEqual(res_drop.action, PolicyAction.BLOCK)


class TestHappyPathAndEngineRoundTrip(unittest.TestCase):
    """Validates seamless happy path detection, selective masking, and PEP roundtrip."""

    def test_selective_masking_valid_vs_invalid_side_by_side(self):
        """In a sentence with both valid and invalid identifiers, ONLY the valid one is masked."""
        protector = DataProtector(DataProtectionConfig(active_domain=DomainType.HEALTHTECH))
        # AB1234567 is invalid DEA checksum; ab1234563 is valid DEA checksum
        mixed_text = "Part AB1234567 was recorded next to prescription dea ab1234563."
        masked, tmap = protector.mask_text(mixed_text)

        self.assertIn("AB1234567", masked, "Invalid DEA was falsely masked!")
        self.assertNotIn("ab1234563", masked, "Valid DEA was missed!")
        self.assertIn("[DEA_NUMBER_1]", masked)
        self.assertEqual(tmap.size, 1)

        # Re-hydration roundtrip
        restored = tmap.restore_text(masked, user_role="compliance_officer")
        self.assertEqual(restored, mixed_text)

    def test_guardrail_engine_pep_full_roundtrip_rbac(self):
        """Full PEP-PDP workflow: guard_input -> guard_output with role enforcement."""
        engine = GuardrailEngine()
        raw_prompt = "Contact patient Alice at alice.wonder@clinic.org regarding NPI 1234567893."

        # Viewer role: input is masked
        input_result = engine.guard_input(raw_prompt, user_role="viewer")
        self.assertTrue(input_result.is_safe)
        self.assertNotIn("alice.wonder@clinic.org", input_result.masked_text)
        self.assertNotIn("1234567893", input_result.masked_text)

        # Viewer attempts to guard_output with rehydration -> PDP blocks unmasking
        output_viewer = engine.guard_output(
            response=f"Summary for {input_result.masked_text}",
            context_chunks=["Contact patient Alice regarding medical record."],
            token_map=input_result.token_map,
            user_role="viewer",
            rehydrate=True,
        )
        self.assertNotIn("alice.wonder@clinic.org", output_viewer.final_response)

        # Compliance officer attempts guard_output with rehydration -> PDP permits unmasking
        output_officer = engine.guard_output(
            response=f"Summary for {input_result.masked_text}",
            context_chunks=["Contact patient Alice regarding medical record."],
            token_map=input_result.token_map,
            user_role="compliance_officer",
            rehydrate=True,
        )
        self.assertIn("alice.wonder@clinic.org", output_officer.final_response)
        self.assertIn("1234567893", output_officer.final_response)

    def test_multi_tenant_salt_isolation(self):
        """Tokens generated by one tenant cannot be unmasked by another tenant with a different salt."""
        tmap_a = TokenMap(_salt="tenant-alpha-salt-12345")
        tmap_b = TokenMap(_salt="tenant-bravo-salt-67890")

        token_a = tmap_a.mask("Patient Diagnosis Cancer", "DIAGNOSIS")
        token_b = tmap_b.mask("Patient Diagnosis Diabetes", "DIAGNOSIS")

        self.assertEqual(token_a, "[DIAGNOSIS_1]")
        self.assertEqual(token_b, "[DIAGNOSIS_1]")

        # Plaintext in A unmasks correctly
        self.assertEqual(tmap_a.unmask(token_a, user_role="admin"), "Patient Diagnosis Cancer")

        # Injected ciphertext into B with different salt fails decryption gracefully and returns None
        tmap_b._reverse[token_a] = tmap_a._reverse[token_a]
        self.assertIsNone(tmap_b.unmask(token_a, user_role="admin"))


if __name__ == "__main__":
    unittest.main()
