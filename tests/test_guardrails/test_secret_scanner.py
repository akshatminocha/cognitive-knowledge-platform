"""
Tests for SecretScanner and Credentials Data Protection Guardrails.
Verifies vendor API keys, private keys, database URIs, passwords,
and Shannon entropy scanning with reversible TokenMap pseudonymization.
"""

from __future__ import annotations

import pytest

from guardrails.secret_scanner import (
    SecretScanner,
    calculate_shannon_entropy,
    is_high_entropy_candidate,
)
from guardrails.data_protection import DataProtector
from guardrails.engine import GuardrailEngine
from guardrails.token_map import TokenMap


class TestShannonEntropy:
    """Verify mathematical entropy calculation and high-entropy detection."""

    def test_shannon_entropy_calculation(self):
        # Empty string
        assert calculate_shannon_entropy("") == 0.0

        # Uniform character string (zero entropy)
        assert calculate_shannon_entropy("aaaaaaaaaaaaaaaa") == 0.0

        # Natural low-entropy text with recurring characters (entropy < 2.5)
        repetitive_word = "senselessness"
        assert calculate_shannon_entropy(repetitive_word) < 2.5

        # Random cryptographic token (high entropy > 4.0)
        random_token = "K9#m$L2!vP8*qR4@zX7&"
        secret_entropy = calculate_shannon_entropy(random_token)
        assert secret_entropy >= 4.0

    def test_high_entropy_candidate_detection(self):
        # Benign short word -> False
        assert not is_high_entropy_candidate("normalword")

        # Repetitive string -> False
        assert not is_high_entropy_candidate("abcabcabcabcabcabc")

        # Long CamelCase words (natural language) -> False
        assert not is_high_entropy_candidate("CognitiveKnowledgePlatform")
        assert not is_high_entropy_candidate("DeoxyribonucleicAcid")

        # Standard UUIDs (database / session IDs) -> False
        assert not is_high_entropy_candidate("123e4567-e89b-12d3-a456-426614174000")

        # URLs and file paths -> False
        assert not is_high_entropy_candidate("https://hospital.org/api/v2/records/summary")
        assert not is_high_entropy_candidate("patient_discharge_summary.json")

        # True arbitrary secrets (mix of letters, digits, and symbols with high entropy) -> True
        secret_candidate = "q9Z#x7$L2!vP8*kR4@bC"
        assert is_high_entropy_candidate(secret_candidate, threshold=3.5)
        assert is_high_entropy_candidate("4f8a9c2b1e7d6a5f4e3c2b1a0f9e8d7c", threshold=3.5)


class TestSecretScanner:
    """Verify known signature scanning and masking."""

    @pytest.fixture
    def scanner(self):
        return SecretScanner()

    def test_mask_openai_api_key(self, scanner):
        text = "My OpenAI key is sk-proj-1234567890abcdef1234567890abcdef1234567890"
        masked, tmap = scanner.mask_secrets(text)
        assert "sk-proj-" not in masked
        assert "[OPENAI_API_KEY_1]" in masked
        assert tmap.unmask("[OPENAI_API_KEY_1]") == "sk-proj-1234567890abcdef1234567890abcdef1234567890"

    def test_mask_anthropic_api_key(self, scanner):
        text = "Anthropic key: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
        masked, tmap = scanner.mask_secrets(text)
        assert "sk-ant-" not in masked
        assert "[ANTHROPIC_API_KEY_1]" in masked

    def test_mask_google_api_key(self, scanner):
        text = "Use key AIzaSyD1234567890abcdefghijklmnopqrstuv"
        masked, tmap = scanner.mask_secrets(text)
        assert "AIzaSy" not in masked
        assert "[GOOGLE_API_KEY_1]" in masked

    def test_mask_aws_access_key(self, scanner):
        text = "AWS config: AKIAIOSFODNN7EXAMPLE"
        masked, tmap = scanner.mask_secrets(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in masked
        assert "[AWS_ACCESS_KEY_1]" in masked

    def test_mask_github_token(self, scanner):
        text = "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyzAB"
        masked, tmap = scanner.mask_secrets(text)
        assert "ghp_" not in masked
        assert "[GITHUB_TOKEN_1]" in masked

    def test_mask_database_uri(self, scanner):
        text = "Connect to postgresql://admin:SuperSecretPass123@db.prod.internal:5432/patients"
        masked, tmap = scanner.mask_secrets(text)
        assert "SuperSecretPass123" not in masked
        assert "[DATABASE_URI_1]" in masked

    def test_mask_contextual_password(self, scanner):
        text = "The database password: MyUltraSecretPass123! for the system"
        masked, tmap = scanner.mask_secrets(text)
        assert "MyUltraSecretPass123!" not in masked
        assert "[PASSWORD_1]" in masked

    def test_mask_password_permutations_and_typos(self, scanner):
        # 1. 'password is cjasb3w4'
        masked1, _ = scanner.mask_secrets("My password is cjasb3w4 for login")
        assert "cjasb3w4" not in masked1
        assert "[PASSWORD_1]" in masked1

        # 2. 'pwd: q8dihac'
        masked2, _ = scanner.mask_secrets("Admin account with pwd: q8dihac")
        assert "q8dihac" not in masked2
        assert "[PASSWORD_1]" in masked2

        # 3. 'pass - asdn93'
        masked3, _ = scanner.mask_secrets("Temporary pass - asdn93")
        assert "asdn93" not in masked3
        assert "[PASSWORD_1]" in masked3

        # 4. Typo 'passwrd: mySecret1'
        masked4, _ = scanner.mask_secrets("User passwrd: mySecret1")
        assert "mySecret1" not in masked4
        assert "[PASSWORD_1]" in masked4

        # 5. Typo 'secrt is 999999'
        masked5, _ = scanner.mask_secrets("The secrt is 999999")
        assert "999999" not in masked5
        assert "[PASSWORD_1]" in masked5

        # 6. Prepositional 'with password mySecretPassword1'
        masked6, _ = scanner.mask_secrets("Connect with password mySecretPassword1 to server")
        assert "mySecretPassword1" not in masked6
        assert "[PASSWORD_1]" in masked6

        # 7. Benign stop-words: 'the password is required' should NOT be masked
        benign = "Please note that the password is required and the pass is valid"
        masked_benign, _ = scanner.mask_secrets(benign)
        assert masked_benign == benign

    def test_mask_private_key(self, scanner):
        text = """Here is the certificate:
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA0Y1234567890abcdef...
-----END RSA PRIVATE KEY-----
Done."""
        masked, tmap = scanner.mask_secrets(text)
        assert "BEGIN RSA PRIVATE KEY" not in masked
        assert "[PRIVATE_KEY_1]" in masked


class TestEndToEndGuardrailProtection:
    """Verify GuardrailEngine input masking and output rehydration for mixed PII and Secrets."""

    def test_guard_input_mixed_pii_and_secrets(self):
        engine = GuardrailEngine()
        user_input = (
            "Patient John Doe (email: john.doe@hospital.org) using "
            "OpenAI key sk-proj-1234567890abcdef1234567890abcdef1234567890 "
            "with password: myMasterDatabasePassword!"
        )

        res = engine.guard_input(user_input)
        assert res.is_safe is True
        assert res.pii_entities_found >= 2

        # Verify nothing sensitive exists in masked_text
        assert "sk-proj-" not in res.masked_text
        assert "myMasterDatabasePassword!" not in res.masked_text
        assert "john.doe@hospital.org" not in res.masked_text

        # Verify output re-hydration
        out = engine.guard_output(
            response=f"Stored credentials for {res.masked_text}",
            context_chunks=[],
            token_map=res.token_map,
            rehydrate=True,
        )
        assert "john.doe@hospital.org" in out.final_response
        assert "myMasterDatabasePassword!" in out.final_response
