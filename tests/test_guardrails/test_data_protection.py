"""Tests for DataProtector — PII masking and unmasking."""

from __future__ import annotations

import pytest

from guardrails.data_protection import DataProtector
from guardrails.config import DataProtectionConfig
from guardrails.token_map import TokenMap


class TestPIIMasking:
    """Verify PII detection and masking."""

    def test_mask_email(self):
        """Email addresses should be masked."""
        dp = DataProtector()
        masked, tmap = dp.mask_text("Contact me at john.doe@example.com please.")
        assert "john.doe@example.com" not in masked
        assert tmap.size > 0

    def test_mask_phone(self):
        """Phone numbers should be masked."""
        dp = DataProtector()
        masked, tmap = dp.mask_text("Call me at +1-415-555-2671.")
        assert "+1-415-555-2671" not in masked

    def test_no_pii_passthrough(self):
        """Text without PII should pass through unchanged."""
        dp = DataProtector()
        text = "The weather is sunny."
        masked, tmap = dp.mask_text(text)
        # No PII entities should be found
        assert tmap.size == 0

    def test_token_map_rehydration(self):
        """Masked tokens should be recoverable via the TokenMap."""
        dp = DataProtector()
        original = "Patient email is alice@hospital.org"
        masked, tmap = dp.mask_text(original)

        # The token map should contain at least one mapping
        assert tmap.size >= 1

        # Rehydrate should restore original values
        rehydrated = tmap.restore_text(masked)
        assert "alice@hospital.org" in rehydrated

    def test_existing_token_map_preserved(self):
        """Passing an existing TokenMap should preserve previous mappings."""
        dp = DataProtector()
        # First pass
        _, tmap = dp.mask_text("Email: a@b.com")
        original_size = tmap.size

        # Second pass with the same tmap
        _, tmap2 = dp.mask_text("Phone: 555-000-1111", token_map=tmap)
        assert tmap2.size >= original_size


class TestTokenMap:
    """Verify TokenMap operations."""

    def test_empty_map(self):
        """New TokenMap should be empty."""
        tm = TokenMap()
        assert tm.size == 0

    def test_add_and_retrieve(self):
        """Adding a token should allow retrieval."""
        tm = TokenMap()
        token = tm.mask("secret@email.com", "EMAIL")
        assert token is not None
        assert tm.size == 1
        assert tm.unmask(token) == "secret@email.com"
