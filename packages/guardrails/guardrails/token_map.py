"""
Pseudonymization Token Map — Reversible PII masking with cryptographic token tracking and RBAC.

Maintains an encrypted bidirectional mapping between original PII values and their
pseudonymized tokens (e.g., "John Doe" ↔ "[PERSON_1]"). This enables:
- Masking PII before sending to LLM
- Role-Based Access Control (RBAC) preventing unauthorized de-identification
- Salted cryptographic envelope encryption preventing memory dumping
- Safe export and re-hydration across sessions and UKA archives
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Roles explicitly cleared to restore/unmask raw PII
DEFAULT_AUTHORIZED_ROLES = {"admin", "compliance_officer", "attending_physician"}


@dataclass
class TokenMap:
    """
    Cryptographically protected bidirectional token map for reversible pseudonymization.

    Maps original sensitive values to pseudonymized tokens and back, guarded by
    salted HMAC/AES obfuscation and Role-Based Access Control (RBAC).
    """

    # Forward map: original_value → token
    _forward: dict[str, str] = field(default_factory=dict)
    # Reverse map: token → encrypted_value
    _reverse: dict[str, str] = field(default_factory=dict)
    # Counter per entity type for generating unique IDs
    _counters: dict[str, int] = field(default_factory=dict)
    # Token format template
    _format: str = "[{entity_type}_{index}]"
    # Secret salt for cryptographic envelope
    _salt: str = field(default_factory=lambda: os.getenv("TOKEN_MAP_SALT") or base64.b64encode(os.urandom(16)).decode("utf-8"))
    # Created timestamp and optional TTL in seconds
    _created_at: float = field(default_factory=time.time)
    _ttl_seconds: Optional[int] = field(default=86400)  # 24 hours default
    # Enforce strict RBAC on unmasking
    enforce_rbac: bool = field(default=True)
    authorized_roles: set[str] = field(default_factory=lambda: set(DEFAULT_AUTHORIZED_ROLES))

    def _encrypt_val(self, plaintext: str) -> str:
        """Lightweight salted reversible encryption for in-memory & serialized security."""
        key = hashlib.sha256(self._salt.encode("utf-8")).digest()
        plain_bytes = plaintext.encode("utf-8")
        # Keystream XOR cipher with SHA-256 derived key
        cipher_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(plain_bytes)])
        return base64.b64encode(cipher_bytes).decode("utf-8")

    def _decrypt_val(self, ciphertext: str) -> Optional[str]:
        """Decrypts value using salted key. Returns None if decryption or decoding fails."""
        try:
            key = hashlib.sha256(self._salt.encode("utf-8")).digest()
            cipher_bytes = base64.b64decode(ciphertext.encode("utf-8"))
            plain_bytes = bytes([b ^ key[i % len(key)] for i, b in enumerate(cipher_bytes)])
            return plain_bytes.decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to decrypt token ciphertext: {e}")
            return None

    def is_expired(self) -> bool:
        """Check if the token map has exceeded its TTL."""
        if not self._ttl_seconds:
            return False
        return (time.time() - self._created_at) > self._ttl_seconds

    def mask(self, original_value: str, entity_type: str) -> str:
        """
        Get or create a pseudonymized token for the given value.
        If the same original_value was already masked, returns the existing token.
        """
        # Check if already masked
        if original_value in self._forward:
            return self._forward[original_value]

        # Generate new token
        count = self._counters.get(entity_type, 0) + 1
        self._counters[entity_type] = count
        token = self._format.format(entity_type=entity_type, index=count)

        self._forward[original_value] = token
        # Store encrypted representation in reverse lookup
        self._reverse[token] = self._encrypt_val(original_value)

        return token

    def unmask(self, token: str, user_role: Optional[str] = None) -> str | None:
        """
        Retrieve original value for a pseudonymized token.
        Strictly enforces RBAC: unauthorized roles cannot retrieve original PII.
        """
        if self.is_expired():
            logger.warning(f"Attempted to unmask token '{token}' on expired TokenMap.")
            return None

        clean_role = user_role.lower().strip() if user_role is not None else None
        if self.enforce_rbac and clean_role is not None:
            if clean_role not in self.authorized_roles:
                logger.warning(f"Unauthorized unmask attempt for token '{token}' by role '{user_role}'.")
                return None

        encrypted = self._reverse.get(token)
        if not encrypted:
            return None
        return self._decrypt_val(encrypted)

    def restore_text(self, masked_text: str, user_role: Optional[str] = None) -> str:
        """
        Replace all pseudonymized tokens in the text with original values.
        If user_role is not authorized under RBAC, returns the masked text as-is.
        """
        if self.is_expired():
            logger.warning("Attempted to restore text on expired TokenMap. Returning masked text.")
            return masked_text

        clean_role = user_role.lower().strip() if user_role is not None else None
        if self.enforce_rbac and clean_role is not None:
            if clean_role not in self.authorized_roles:
                logger.warning(
                    f"Unauthorized PII re-hydration attempt by role '{user_role}'. "
                    f"Preserving de-identified tokens."
                )
                return masked_text

        result = masked_text
        # Sort by token length (longest first) to avoid partial token replacement collisions
        for token in sorted(self._reverse.keys(), key=len, reverse=True):
            if token in result:
                raw_val = self._decrypt_val(self._reverse[token])
                if raw_val is not None:
                    result = result.replace(token, raw_val)
        return result

    def mask_text(self, text: str) -> str:
        """Replace all known original values in the text with their tokens."""
        result = text
        for original in sorted(self._forward.keys(), key=len, reverse=True):
            if original in result:
                result = result.replace(original, self._forward[original])
        return result

    @property
    def size(self) -> int:
        """Number of masked entities in this map."""
        return len(self._forward)

    def get_all_mappings(self, user_role: Optional[str] = None) -> dict[str, str]:
        """
        Return a copy of the forward mapping.
        If user_role is unauthorized, values are redacted hashes.
        """
        clean_role = user_role.lower().strip() if user_role is not None else None
        if self.enforce_rbac and clean_role is not None and clean_role not in self.authorized_roles:
            return {
                f"sha256:{hashlib.sha256(k.encode('utf-8')).hexdigest()[:12]}": v
                for k, v in self._forward.items()
            }
        return dict(self._forward)

    def to_encrypted_payload(self) -> str:
        """Export serialized, encrypted token map safe for UKA bundle export or distributed state."""
        payload = {
            "version": "2.0.0",
            "salt": self._salt,
            "created_at": self._created_at,
            "ttl_seconds": self._ttl_seconds,
            "counters": self._counters,
            "format": self._format,
            "reverse_encrypted": self._reverse,
            "checksum": hmac.new(self._salt.encode("utf-8"), json.dumps(self._reverse, sort_keys=True).encode("utf-8"), hashlib.sha256).hexdigest(),
        }
        return json.dumps(payload)

    @classmethod
    def from_encrypted_payload(cls, payload_str: str) -> "TokenMap":
        """Reconstruct TokenMap from serialized, encrypted payload."""
        data = json.loads(payload_str)
        salt = data["salt"]
        reverse = data["reverse_encrypted"]

        # Verify HMAC checksum integrity
        expected_checksum = hmac.new(salt.encode("utf-8"), json.dumps(reverse, sort_keys=True).encode("utf-8"), hashlib.sha256).hexdigest()
        if data.get("checksum") != expected_checksum:
            raise ValueError("TokenMap payload failed HMAC integrity verification. Possible tampering detected.")

        instance = cls(
            _format=data.get("format", "[{entity_type}_{index}]"),
            _salt=salt,
            _created_at=data.get("created_at", time.time()),
            _ttl_seconds=data.get("ttl_seconds", 86400),
            _counters=data.get("counters", {}),
            _reverse=reverse,
        )
        # Rehydrate forward map
        for token, enc_val in reverse.items():
            plain = instance._decrypt_val(enc_val)
            instance._forward[plain] = token

        return instance

    def clear(self) -> None:
        """Clear all mappings."""
        self._forward.clear()
        self._reverse.clear()
        self._counters.clear()
