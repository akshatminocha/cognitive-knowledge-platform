"""
Pseudonymization Token Map — Reversible PII masking with token tracking.

Maintains a bidirectional mapping between original PII values and their
pseudonymized tokens (e.g., "John Doe" ↔ "[PERSON_A1]"). This enables:
- Masking PII before sending to LLM
- Re-hydrating PII in the final response for authorized users
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TokenMap:
    """
    Bidirectional token map for reversible pseudonymization.

    Maps original sensitive values to pseudonymized tokens and back.
    Each entity type maintains its own counter for unique token IDs.
    """

    # Forward map: original_value → token
    _forward: dict[str, str] = field(default_factory=dict)
    # Reverse map: token → original_value
    _reverse: dict[str, str] = field(default_factory=dict)
    # Counter per entity type for generating unique IDs
    _counters: dict[str, int] = field(default_factory=dict)
    # Token format template
    _format: str = "[{entity_type}_{index}]"

    def mask(self, original_value: str, entity_type: str) -> str:
        """
        Get or create a pseudonymized token for the given value.

        If the same original_value was already masked, returns the existing token
        (deterministic within a session).
        """
        # Check if already masked
        if original_value in self._forward:
            return self._forward[original_value]

        # Generate new token
        count = self._counters.get(entity_type, 0) + 1
        self._counters[entity_type] = count
        token = self._format.format(entity_type=entity_type, index=count)

        self._forward[original_value] = token
        self._reverse[token] = original_value

        return token

    def unmask(self, token: str) -> str | None:
        """Retrieve the original value for a pseudonymized token."""
        return self._reverse.get(token)

    def restore_text(self, masked_text: str) -> str:
        """
        Replace all pseudonymized tokens in the text with original values.

        Used to re-hydrate the final response for authorized users.
        """
        result = masked_text
        # Sort by token length (longest first) to avoid partial replacements
        for token in sorted(self._reverse.keys(), key=len, reverse=True):
            if token in result:
                result = result.replace(token, self._reverse[token])
        return result

    def mask_text(self, text: str) -> str:
        """
        Replace all known original values in the text with their tokens.

        Used to mask text that may contain previously-seen PII.
        """
        result = text
        # Sort by value length (longest first) to avoid partial replacements
        for original in sorted(self._forward.keys(), key=len, reverse=True):
            if original in result:
                result = result.replace(original, self._forward[original])
        return result

    @property
    def size(self) -> int:
        """Number of masked entities in this map."""
        return len(self._forward)

    def get_all_mappings(self) -> dict[str, str]:
        """Return a copy of the forward mapping (for debugging/logging)."""
        return dict(self._forward)

    def clear(self) -> None:
        """Clear all mappings."""
        self._forward.clear()
        self._reverse.clear()
        self._counters.clear()
