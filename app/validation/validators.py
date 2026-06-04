import re

import bleach
from app.monitoring.logging_utils import ValidationError


def sanitize_html(text: str) -> str:
    """Remove all HTML tags"""
    return bleach.clean(text, tags=[], strip=True)


def validate_message(message) -> str:
    """Validate and sanitize user message"""
    if message is None:
        raise ValidationError("Message cannot be None")
    if isinstance(message, dict):
        if "text" not in message:
            raise ValidationError("Message dict must have 'text' key")
        user_text = message["text"]
    else:
        user_text = str(message)
    user_text = user_text.strip()
    if not user_text:
        raise ValidationError("Message cannot be empty")
    if len(user_text) > 5000:
        raise ValidationError("Message too long (max 5000 characters)")
    dangerous_sql = [
        "DROP TABLE",
        "DELETE FROM",
        "INSERT INTO",
        "UPDATE ",
        "--",
        "/*",
        "*/",
        "';",
        "OR 1=1",
    ]
    if any(pattern in user_text.upper() for pattern in dangerous_sql):
        raise ValidationError("Potentially malicious SQL detected")
    xss_patterns = [
        r"<script[^>]*>.*?</script>",
        r"javascript:",
        r"on\w+\s*=",  # Event handlers
        r"<iframe",
        r"<object",
        r"<embed",
    ]
    for pattern in xss_patterns:
        if re.search(pattern, user_text, re.IGNORECASE):
            raise ValidationError("Potentially malicious HTML detected")
    user_text = sanitize_html(user_text)
    return user_text
