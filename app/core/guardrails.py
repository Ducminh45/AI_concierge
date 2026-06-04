"""Input and output guardrails for the concierge chatbot."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
_PHONE_RE = re.compile(
    r"(?<!\d)"  # no digit before
    r"(?:\+?1[-.\s]?)?"  # optional country code
    r"(?:\(?\d{3}\)?[-.\s]?)"  # area code
    r"\d{3}[-.\s]?\d{4}"  # subscriber number
    r"(?!\d)",  # no digit after
)
_CC_RE = re.compile(
    r"\b(?:"
    r"4\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Visa
    r"|5[1-5]\d{2}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Mastercard
    r"|3[47]\d{2}[-\s]?\d{6}[-\s]?\d{5}"  # Amex
    r"|6(?:011|5\d{2})[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}"  # Discover
    r")\b"
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _normalize(text: str) -> str:
    """Normalize unicode and lowercase to prevent bypass via homoglyphs or character tricks."""
    return unicodedata.normalize("NFKC", text).lower()


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _redact(text: str, pattern: re.Pattern, label: str) -> tuple[str, bool]:
    """Replace all matches of *pattern* with a redaction placeholder."""
    new, n = pattern.subn(f"[REDACTED {label}]", text)
    return new, n > 0


_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?above\s+instructions",
        r"ignore\s+(all\s+)?(your|my|these|the|its|prior)\s+(instructions|rules|guidelines|prompt)",
        r"forget\s+(all\s+)?(your|my|these|the|its|prior)\s+(instructions|rules|guidelines|prompt)",
        r"(?:do\s+not|don'?t|stop)\s+follow(?:ing)?\s+(your|the|any)\s+(instructions|rules|guidelines|prompt)",
        r"disregard\s+(all\s+)?previous",
        r"disregard\s+everything",
        r"you\s+are\s+now\s+(?:a|an|the)\b",
        r"you\s+(?:must|will)\s+now\b",
        r"from\s+now\s+on[,;]?\s+you\s+(?:are|will|must|should|have|can)",
        r"new\s+(?:instructions?\s*:|role|persona)",
        r"system\s*prompt\s*:",
        r"act\s+as\s+(?:a|an|if)\b",
        r"pretend\s+(?:you\s+are|to\s+be)\b",
        r"override\s+(?:your|the)\s+(?:instructions|rules|prompt)",
        r"enter\s+(?:developer|debug|admin)\s+mode",
        r"\bDAN\b",  # "Do Anything Now" jailbreak
        r"jailbreak",
        r"reveal\s+(?:your|the)\s+(?:system|initial)\s+prompt",
        r"ignore\s+everything\s+above",
    ]
]

_OFFTOPIC_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"write\s+(?:me\s+)?(?:a\s+)?(?:python|javascript|code|script|program)",
        r"help\s+me\s+hack",
        r"how\s+(?:do\s+I|to)\s+(?:hack|exploit|crack)",
        r"generate\s+(?:a\s+)?(?:malware|virus|exploit)",
        r"create\s+(?:a\s+)?(?:phishing|scam)",
        r"(?:sql|xss|csrf)\s+injection\s+(?:tutorial|example|guide)",
    ]
]


@dataclass
class InputGuard:
    def check_prompt_injection(self, text: str) -> tuple[bool, str]:
        """Return ``(is_safe, reason)`` after scanning for injection patterns."""
        normalized = _normalize(text)
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(normalized):
                return False, f"Prompt injection detected: {pattern.pattern}"
        return True, ""

    def check_pii(self, text: str) -> tuple[str, list[str]]:
        """Detect and redact PII, returning the cleaned text and types found."""
        found: set[str] = set()
        text, hit = _redact(text, _EMAIL_RE, "EMAIL")
        if hit:
            found.add("email")
        text, hit = _redact(text, _PHONE_RE, "PHONE")
        if hit:
            found.add("phone")
        for match in _CC_RE.finditer(text):
            full = match.group(0)
            if _luhn_check(full):
                text = text.replace(full, "[REDACTED CREDIT_CARD]")
                found.add("credit_card")
        text, hit = _redact(text, _SSN_RE, "SSN")
        if hit:
            found.add("ssn")
        return text, list(found)

    def check_topic_boundary(self, text: str) -> bool:
        """Return *True* if the message is on-topic or harmless chitchat."""
        for pattern in _OFFTOPIC_PATTERNS:
            if pattern.search(text):
                return False
        return True


_LEAKED_PROMPT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"MANDATORY\s+RULES\s*:",
        r"RESORT\s+KNOWLEDGE\s+BASE\s*\(",
        r"ACTIVE\s+SESSION\s+ID\s*:",
        r"system\s*prompt\s*:",
    ]
]

_CHARACTER_BREAK_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"as\s+an?\s+AI\s+language\s+model",
        r"I'?m\s+(?:just\s+)?an?\s+AI",
        r"I\s+(?:am|was)\s+(?:created|made|trained)\s+by\s+(?:OpenAI|Anthropic|Google)",
    ]
]

_PARAPHRASED_LEAKAGE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"my\s+instructions\s+say",
        r"my\s+system\s+prompt",
        r"I\s+was\s+told\s+to",
        r"my\s+rules\s+are",
        r"I'?m\s+programmed\s+to",
    ]
]


@dataclass
class OutputGuard:
    input_pii_types: list[str] = field(default_factory=list)

    def check_response(self, text: str) -> tuple[bool, str]:
        """Return ``(is_safe, reason)`` after running all output checks."""
        for pattern in _LEAKED_PROMPT_PATTERNS:
            if pattern.search(text):
                return False, "Response may contain leaked system prompt content"

        for pattern in _CHARACTER_BREAK_PATTERNS:
            if pattern.search(text):
                return False, "Response breaks character (AI self-reference)"

        for pattern in _PARAPHRASED_LEAKAGE_PATTERNS:
            if pattern.search(text):
                return False, "Response contains paraphrased system prompt leakage"

        output_has_email = bool(_EMAIL_RE.search(text))
        output_has_phone = bool(_PHONE_RE.search(text))
        output_has_cc = bool(_CC_RE.search(text))
        output_has_ssn = bool(_SSN_RE.search(text))

        if output_has_email and "email" not in self.input_pii_types:
            return False, "Response contains email address not present in input"
        if output_has_phone and "phone" not in self.input_pii_types:
            return False, "Response contains phone number not present in input"
        if output_has_cc:
            return False, "Response contains credit card number"
        if output_has_ssn and "ssn" not in self.input_pii_types:
            return False, "Response contains SSN not present in input"

        return True, ""
