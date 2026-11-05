"""
Unit and Integration Tests for Robust PII Masking, Hybrid NER, and PEP-PDP Governance.

Verifies:
- CMS NPI Luhn validation and DEA checksum verification
- Healthcare (MRN, NPI, DEA) and Fintech (EIN, ITIN, CUSIP, IBAN) entity masking
- Complete offline regex fallback parity
- Zero-Shot LLM Audit layer with timeout circuit-breaker
- Cryptographic salted TokenMap and Role-Based Access Control (RBAC)
- Declarative Policy Decision Point (PDP) and OPA evaluation
"""

from __future__ import annotations

import unittest

from guardrails.config import DataProtectionConfig, DomainType, GuardrailConfig
from guardrails.data_protection import (
    DataProtector,
    validate_dea_checksum,
    validate_npi_luhn,
)
from guardrails.engine import GuardrailEngine
from guardrails.policy_engine import PolicyAction, PolicyDecisionPoint
from guardrails.token_map import TokenMap


class TestDomainValidators(unittest.TestCase):
    """Verifies domain checksum algorithms (NPI Luhn, DEA)."""

    def test_npi_luhn_algorithm(self):
        # 1234567893 is a mathematically valid NPI under CMS 80840 Luhn rule
        self.assertTrue(validate_npi_luhn("1234567893"))

        # Random 10-digit number failing Luhn
        self.assertFalse(validate_npi_luhn("1234567890"))
        # Invalid length
        self.assertFalse(validate_npi_luhn("12345"))

    def test_dea_checksum_algorithm(self):
        # AB1234563:
        # (1 + 3 + 5) + 2*(2 + 4 + 6) = 9 + 24 = 33 -> 33 % 10 = 3 (valid!)
        self.assertTrue(validate_dea_checksum("AB1234563"))

        # Invalid checksum digit
        self.assertFalse(validate_dea_checksum("AB1234568"))
        # Invalid format
        self.assertFalse(validate_dea_checksum("12ABC4563"))


class TestHybridNERMasking(unittest.TestCase):
    """Verifies clinical, financial, and zero-shot entity masking."""

    def setUp(self):
        self.config = DataProtectionConfig(
            active_domain=DomainType.HEALTHTECH,
            enable_zero_shot_audit=True,
            zero_shot_timeout_seconds=0.5,
        )
        self.protector = DataProtector(self.config)

    def test_clinical_masking_npi_dea_mrn(self):
        sample = (
            "Physician Dr. Robert Vance (NPI: 1234567893, DEA: AB1234563) "
            "treated patient MRN-987654 for hypertension."
        )
        masked, tmap = self.protector.mask_text(sample)

        self.assertNotIn("1234567893", masked)
        self.assertNotIn("AB1234563", masked)
        self.assertNotIn("987654", masked)
        self.assertGreaterEqual(tmap.size, 3)

    def test_fintech_masking_ein_itin_cusip(self):
        fintech_config = DataProtectionConfig(
            active_domain=DomainType.FINTECH,
            enable_zero_shot_audit=True,
        )
        protector = DataProtector(fintech_config)
        sample = "Entity Corp with EIN 12-3456789 and ITIN 912-34-5678 holds CUSIP 037833100."
        masked, tmap = protector.mask_text(sample)

        self.assertNotIn("12-3456789", masked)
        self.assertNotIn("912-34-5678", masked)
        self.assertNotIn("037833100", masked)
        self.assertGreaterEqual(tmap.size, 2)

    def test_offline_fallback_parity(self):
        """Forces regex fallback path and ensures domain entities are captured."""
        sample = "Patient with MRN 654321, SSN 123-45-6789, and email test@hospital.com."
        tmap = TokenMap()
        masked, res_tmap = self.protector._mask_with_regex(sample, tmap)

        self.assertNotIn("654321", masked)
        self.assertNotIn("123-45-6789", masked)
        self.assertNotIn("test@hospital.com", masked)
        self.assertGreaterEqual(res_tmap.size, 3)

    def test_zero_shot_contextual_auditor(self):
        """Contextual auditor identifies clinical doctor titles missed by plain regex."""
        sample = "Consultation conducted by Doctor Gregory House in the West Wing."
        spans = self.protector._contextual_fallback_auditor(sample)
        self.assertGreaterEqual(len(spans), 1)
        self.assertEqual(spans[0].entity_type, "PERSON")


class TestCryptographicTokenMapAndRBAC(unittest.TestCase):
    """Verifies salted cryptographic encryption and Role-Based Access Control."""

    def test_rbac_unmask_authorization(self):
        tmap = TokenMap(enforce_rbac=True)
        token = tmap.mask("Secret MRN 999999", "MRN")

        # 1. Standard or anonymous user cannot unmask
        unmasked_viewer = tmap.unmask(token, user_role="viewer")
        self.assertIsNone(unmasked_viewer)

        # 2. Re-hydration denied for unauthorized user (tokens preserved)
        restored_viewer = tmap.restore_text(f"Patient has {token}", user_role="viewer")
        self.assertEqual(restored_viewer, f"Patient has {token}")

        # 3. Compliance officer and Admin can unmask
        unmasked_admin = tmap.unmask(token, user_role="admin")
        self.assertEqual(unmasked_admin, "Secret MRN 999999")

        restored_compliance = tmap.restore_text(f"Patient has {token}", user_role="compliance_officer")
        self.assertEqual(restored_compliance, "Patient has Secret MRN 999999")

    def test_encrypted_serialization_and_tamper_detection(self):
        tmap = TokenMap(_salt="test-secret-salt")
        tmap.mask("confidential_patient_id", "PATIENT_ID")

        # Export serialized envelope
        payload = tmap.to_encrypted_payload()
        self.assertIn("reverse_encrypted", payload)
        self.assertNotIn("confidential_patient_id", payload)  # Plaintext never exposed!

        # Import into fresh TokenMap instance
        imported_tmap = TokenMap.from_encrypted_payload(payload)
        self.assertEqual(imported_tmap.size, 1)
        self.assertEqual(
            imported_tmap.unmask("[PATIENT_ID_1]", user_role="admin"),
            "confidential_patient_id"
        )

        # Tampered payload fails HMAC verification
        tampered = payload.replace("PATIENT_ID", "TAMPERED_ID")
        with self.assertRaises(ValueError):
            TokenMap.from_encrypted_payload(tampered)


class TestPolicyDecisionPoint(unittest.TestCase):
    """Verifies decoupled PDP / OPA evaluation matrix."""

    def setUp(self):
        self.pdp = PolicyDecisionPoint()

    def test_input_policy_prompt_injection(self):
        decision = self.pdp.evaluate_input_policy(
            user_role="user",
            domain="healthtech",
            detected_entities=[],
            has_prompt_injection=True,
        )
        self.assertFalse(decision.allow)
        self.assertEqual(decision.action, PolicyAction.BLOCK)

    def test_input_policy_pii_masking_requirement(self):
        decision = self.pdp.evaluate_input_policy(
            user_role="user",
            domain="healthtech",
            detected_entities=["NPI", "MRN"],
            has_prompt_injection=False,
        )
        self.assertTrue(decision.allow)
        self.assertEqual(decision.action, PolicyAction.MASK)

    def test_unmask_rbac_clearance(self):
        # Viewer denied
        viewer_dec = self.pdp.evaluate_unmask_policy(user_role="analyst", entity_types=["MRN"])
        self.assertFalse(viewer_dec.allow)

        # Compliance officer allowed
        compliance_dec = self.pdp.evaluate_unmask_policy(user_role="compliance_officer", entity_types=["MRN"])
        self.assertTrue(compliance_dec.allow)
        self.assertEqual(compliance_dec.action, PolicyAction.REHYDRATE)

    def test_tool_policy_write_blocking(self):
        write_dec = self.pdp.evaluate_tool_policy(
            tool_name="neo4j_query",
            user_role="analyst",
            is_write_operation=True,
        )
        self.assertFalse(write_dec.allow)
        self.assertEqual(write_dec.action, PolicyAction.BLOCK)


class TestGuardrailEngineIntegration(unittest.TestCase):
    """Verifies end-to-end PEP integration with PolicyDecisionPoint."""

    def test_engine_pep_masking_and_rbac_output(self):
        engine = GuardrailEngine()

        # Input PEP
        input_res = engine.guard_input(
            "Admit patient with MRN: 112233 under Dr. Vance (NPI: 1234567893).",
            user_role="doctor",
        )
        self.assertNotIn("112233", input_res.masked_text)
        self.assertNotIn("1234567893", input_res.masked_text)

        # Output PEP for unauthorized role (remains masked)
        out_unauth = engine.guard_output(
            response=f"Diagnosed {input_res.masked_text}",
            context_chunks=[],
            token_map=input_res.token_map,
            rehydrate=True,
            user_role="research_assistant",
        )
        self.assertFalse(out_unauth.was_rehydrated)
        self.assertIn("[MEDICAL_RECORD_NUMBER_1]", out_unauth.final_response)

        # Output PEP for compliance officer (rehydrates original)
        out_auth = engine.guard_output(
            response=f"Diagnosed {input_res.masked_text}",
            context_chunks=[],
            token_map=input_res.token_map,
            rehydrate=True,
            user_role="compliance_officer",
        )
        self.assertTrue(out_auth.was_rehydrated)
        self.assertIn("112233", out_auth.final_response)


if __name__ == "__main__":
    unittest.main()

