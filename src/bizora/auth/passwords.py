"""Password hashing with stdlib PBKDF2-HMAC-SHA256 (no new dependencies).

Stored form is ``pbkdf2_sha256$<iterations>$<b64 salt>$<b64 key>``.
Verification fails closed: malformed stored hashes never raise and
never match, and comparison is constant-time.
"""

import base64
import binascii
import hashlib
import hmac
import os

ALGORITHM_ID = "pbkdf2_sha256"
ITERATIONS = 600_000
SALT_BYTES = 16
KEY_BYTES = 32
_MAX_ITERATIONS = 10_000_000


def hash_password(password: str) -> str:
    """Hash a password for storage."""
    if not password:
        raise ValueError("Password must be non-empty.")
    salt = os.urandom(SALT_BYTES)
    key = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    key_b64 = base64.b64encode(key).decode("ascii")
    return f"{ALGORITHM_ID}${ITERATIONS}${salt_b64}${key_b64}"


def verify_password(password: str, stored: str) -> bool:
    """Return whether a password matches a stored hash."""
    try:
        algorithm, iterations_raw, salt_b64, key_b64 = stored.split("$")
        if algorithm != ALGORITHM_ID:
            return False
        iterations = int(iterations_raw)
        if not 1 <= iterations <= _MAX_ITERATIONS:
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(key_b64.encode("ascii"))
        if len(salt) != SALT_BYTES or len(expected) != KEY_BYTES:
            return False
    except (ValueError, binascii.Error):
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(candidate, expected)
