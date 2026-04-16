import hashlib
import hmac
import base64
import re

from app.config import HMAC_SECRET


def generate_signature(order_id: str) -> str:
    """Generate a URL-safe signature (12 chars) from order ID."""
    digest = hmac.new(
        HMAC_SECRET.encode(),
        order_id.encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:12]


def verify_signature(order_id: str, signature: str) -> bool:
    """Verify that the provided signature matches the expected one."""
    expected = generate_signature(order_id)
    return hmac.compare_digest(expected, signature)


def is_valid_order_id(value: str) -> bool:
    """Check if a string looks like a valid Cross Cart sales order ID (ULID-based).

    Example: C-01KNTSX8ZCRRPRGNTCGS3R55XR
    """
    pattern = re.compile(r"^C-[0-9A-Z]{26}$")
    return bool(pattern.match(value))
