"""
Secret Scanner — High-Entropy & Pattern-Based Secrets & Credentials Detection.

Detects sensitive credentials before they reach external LLMs:
1. Deterministic Known Vendor API Keys (OpenAI, Anthropic, Google, AWS, GitHub, Slack)
2. Asymmetric Cryptographic Private Keys (PEM / OpenSSH)
3. Database Connection URIs with embedded passwords
4. Contextual Passwords & Auth Tokens (e.g., password=..., pwd: ...)
5. Shannon Entropy Analysis for zero-day arbitrary high-entropy tokens and secrets
"""

from __future__ import annotations

import math
import re
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from guardrails.token_map import TokenMap

logger = logging.getLogger(__name__)


@dataclass
class SecretMatch:
    """Represents a detected secret or credential."""

    secret_type: str
    value: str
    start: int
    end: int
    confidence: float


# ---------------------------------------------------------------------------
# Shannon Entropy Calculation
# ---------------------------------------------------------------------------
def calculate_shannon_entropy(text: str) -> float:
    """
    Compute the Shannon entropy of a string: H = -sum(p_i * log2(p_i)).
    
    Standard English text: ~1.5 - 2.8
    Base64 / Hex / Random cryptographic secrets: >= 3.5 - 4.5
    """
    if not text:
        return 0.0

    length = len(text)
    counts = Counter(text)
    entropy = 0.0

    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)

    return entropy


UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
COMMON_FILE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".docx", ".pptx",
    ".xlsx", ".csv", ".json", ".xml", ".html", ".css", ".js", ".ts",
    ".py", ".md", ".txt", ".tar", ".gz", ".zip",
)


def is_high_entropy_candidate(token: str, threshold: float = 3.6, min_len: int = 16) -> bool:
    """
    Determine if an alphanumeric string is an arbitrary secret based on length,
    Shannon entropy, and multi-tier heuristic exclusions.

    Excludes:
    - Pure numbers (timestamps, IDs, credit cards handled by Presidio)
    - Pure alphabetic words (long CamelCase identifiers, medical terms)
    - Standard UUIDs (record / session IDs)
    - URLs and web endpoints (http/https/ftp)
    - File system paths and common document extensions
    - Low-diversity or repetitive sequences
    """
    # Clean surrounding punctuation
    token = token.strip("`'\"()[]{}<>,;:")
    if len(token) < min_len or len(token) > 256:
        return False

    # Avoid purely numeric strings (like timestamps, credit cards handled by Presidio)
    if token.isdigit():
        return False

    # Avoid purely alphabetic strings (prevents false positives on long CamelCase/PascalCase words)
    if token.isalpha():
        return False

    # Avoid standard UUIDs
    if UUID_PATTERN.match(token):
        return False

    # Avoid URLs and web schemes
    if token.lower().startswith(("http://", "https://", "ftp://", "file://", "ws://", "wss://")):
        return False

    # Avoid file paths and common file extensions
    if any(token.lower().endswith(ext) for ext in COMMON_FILE_EXTENSIONS):
        return False

    # Check for character diversity (mix of upper, lower, digits, symbols)
    has_upper = any(c.isupper() for c in token)
    has_lower = any(c.islower() for c in token)
    has_digit = any(c.isdigit() for c in token)
    has_symbol = any(c in "-_+=/!@#$%^&*" for c in token)

    # Must contain at least digits or symbols, in addition to letters
    has_letter = has_upper or has_lower
    if not (has_letter and (has_digit or has_symbol)):
        return False

    diversity_score = sum([has_upper, has_lower, has_digit, has_symbol])
    if diversity_score < 2:
        return False

    # Reject common non-secret sequences (e.g. repetitive characters)
    counts = Counter(token)
    most_common_char_freq = counts.most_common(1)[0][1] / len(token)
    if most_common_char_freq > 0.35:
        return False

    entropy = calculate_shannon_entropy(token)
    return entropy >= threshold


CONTEXTUAL_STOP_WORDS: set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "to", "in", "on",
    "at", "by", "for", "with", "about", "like", "through", "over",
    "before", "between", "after", "since", "without", "under", "within",
    "along", "following", "across", "behind", "beyond", "plus", "except",
    "but", "up", "out", "around", "down", "off", "above", "near",
    "null", "none", "true", "false", "required", "empty", "hidden",
    "undefined", "valid", "invalid", "missing", "unknown", "changed",
    "correct", "incorrect", "expired", "secure", "insecure", "needed", "set",
    "allowed", "prohibited", "enabled", "disabled", "masked", "redacted",
    "reset", "generated", "hashed", "encrypted",
}

# ---------------------------------------------------------------------------
# Known Secret Signatures & Patterns
# ---------------------------------------------------------------------------
KNOWN_SECRET_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    # Private Cryptographic Keys
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            re.MULTILINE,
        ),
        1.0,
    ),
    # OpenAI API Keys (legacy sk- and modern sk-proj-)
    (
        "OPENAI_API_KEY",
        re.compile(r"\b(?:sk-[a-zA-Z0-9]{20,T?[a-zA-Z0-9]{20,}|sk-proj-[a-zA-Z0-9_\-]{40,})\b"),
        0.98,
    ),
    # Anthropic API Keys
    (
        "ANTHROPIC_API_KEY",
        re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{30,}\b"),
        0.98,
    ),
    # Google API Keys
    (
        "GOOGLE_API_KEY",
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        0.95,
    ),
    # AWS Access Key IDs
    (
        "AWS_ACCESS_KEY",
        re.compile(r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"),
        0.95,
    ),
    # GitHub Personal & App Access Tokens
    (
        "GITHUB_TOKEN",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,255}\b"),
        0.98,
    ),
    # Slack Tokens
    (
        "SLACK_TOKEN",
        re.compile(r"\bxox[baprs]-[0-9a-zA-Z]{10,48}\b"),
        0.95,
    ),
    # Database Connection Strings (with embedded passwords)
    (
        "DATABASE_URI",
        re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp):\/\/[^\s:@]+:[^\s:@]+@[^\s:]+"),
        0.95,
    ),
    # JSON Web Tokens (JWT)
    (
        "JWT_TOKEN",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        0.90,
    ),
    # Contextual Password & Credential Assignment (Forward: password is ..., pwd: ..., pass - ..., creds -> ...)
    (
        "PASSWORD",
        re.compile(
            r"\b(?:"
            r"database_password|client_secret|api_secret|auth_token|access_token|private_key|"
            r"p[a@][sz$]{1,2}w?[o0]?r?d|passwd|pswd|pwd|pass|"
            r"cred(?:ential)?s?|"
            r"secr(?:et)?s?|secrt|secert|"
            r"(?:api[_\-]?|auth[_\-]?)?(?:token|key)s?|"
            r"pin(?:code)?"
            r")"
            r"(?:\s*(?:[:=]|:=|->|=>|-|~)\s*|\s+(?:is|was|are|as|set\s+to|of)\s+)"
            r"[\"']?([^\s\"',;:<>()]{4,})[\"']?",
            re.IGNORECASE,
        ),
        0.90,
    ),
    # Contextual Password & Credential Assignment (Prepositional: with password ..., using pwd ..., for creds ...)
    (
        "PASSWORD",
        re.compile(
            r"\b(?:with|using|for)\s+(?:the\s+)?"
            r"(?:"
            r"database_password|client_secret|api_secret|auth_token|access_token|private_key|"
            r"p[a@][sz$]{1,2}w?[o0]?r?d|passwd|pswd|pwd|pass|"
            r"cred(?:ential)?s?|"
            r"secr(?:et)?s?|secrt|secert|"
            r"(?:api[_\-]?|auth[_\-]?)?(?:token|key)s?|"
            r"pin(?:code)?"
            r")\s*(?:[:=-]|is)?\s*[\"']?([^\s\"',;:<>()]{4,})[\"']?",
            re.IGNORECASE,
        ),
        0.88,
    ),
    # Bearer Authentication Header values
    (
        "BEARER_TOKEN",
        re.compile(r"(?i)\bBearer\s+([A-Za-z0-9_\-\.]{20,})\b"),
        0.85,
    ),
]


# ---------------------------------------------------------------------------
# Secret Scanner Engine
# ---------------------------------------------------------------------------
class SecretScanner:
    """
    High-accuracy detector for passwords, API keys, private keys, and high-entropy secrets.
    """

    def __init__(
        self,
        entropy_threshold: float = 3.6,
        enable_entropy_check: bool = True,
    ) -> None:
        self.entropy_threshold = entropy_threshold
        self.enable_entropy_check = enable_entropy_check

    def scan(self, text: str) -> list[SecretMatch]:
        """
        Scan text and return all detected secret matches, ordered by start position.
        """
        if not text:
            return []

        matches: list[SecretMatch] = []
        covered_spans: list[tuple[int, int]] = []

        # 1. Deterministic Known Signatures
        for secret_type, pattern, confidence in KNOWN_SECRET_PATTERNS:
            for match in pattern.finditer(text):
                # If pattern has a capturing group (like password/bearer), extract that group
                if match.groups() and match.group(1):
                    val = match.group(1).rstrip(".!?,")
                    start = match.start(1)
                    end = start + len(val)
                    # Filter out stop words in contextual assignments (e.g. 'password is required')
                    if secret_type == "PASSWORD" and val.lower() in CONTEXTUAL_STOP_WORDS:
                        continue
                else:
                    val = match.group(0)
                    start, end = match.start(), match.end()

                # Avoid duplicate matches on overlapping spans
                if any(cs[0] <= start and end <= cs[1] for cs in covered_spans):
                    continue

                matches.append(
                    SecretMatch(
                        secret_type=secret_type,
                        value=val,
                        start=start,
                        end=end,
                        confidence=confidence,
                    )
                )
                covered_spans.append((start, end))

        # 2. Shannon Entropy Scan for Arbitrary Unknown Secrets
        if self.enable_entropy_check:
            # Word token boundary search for standalone alphanumeric tokens
            word_pattern = re.compile(r"\b[A-Za-z0-9_\-+=/!@#$%^&*]{16,}\b")
            for m in word_pattern.finditer(text):
                start, end = m.start(), m.end()
                # Skip if already captured by known pattern
                if any(cs[0] <= start and end <= cs[1] for cs in covered_spans):
                    continue

                token = m.group(0)
                if is_high_entropy_candidate(token, threshold=self.entropy_threshold):
                    matches.append(
                        SecretMatch(
                            secret_type="HIGH_ENTROPY_SECRET",
                            value=token,
                            start=start,
                            end=end,
                            confidence=0.80,
                        )
                    )
                    covered_spans.append((start, end))

        # Sort matches in reverse order for clean non-colliding replacement
        matches.sort(key=lambda m: m.start, reverse=True)
        return matches

    def mask_secrets(
        self,
        text: str,
        token_map: Optional[TokenMap] = None,
    ) -> tuple[str, TokenMap]:
        """
        Mask all detected secrets into reversible TokenMap tokens.
        
        Example:
            "sk-1234567890abcdef1234567890" -> "[OPENAI_API_KEY_1]"
            "password: mySecretPassword123" -> "password: [PASSWORD_1]"
        """
        tmap = token_map or TokenMap()
        matches = self.scan(text)

        if not matches:
            return text, tmap

        masked = text
        for m in matches:
            # Replace from end to start to preserve string indices
            token = tmap.mask(m.value, m.secret_type)
            masked = masked[: m.start] + token + masked[m.end :]

        return masked, tmap
