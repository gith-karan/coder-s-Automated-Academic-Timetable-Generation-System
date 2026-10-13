"""Password hashing, token generation and password policy."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

# Argon2id with OWASP-recommended parameters (m=19 MiB, t=2, p=1) or stronger.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

# A dummy hash so that login timing is identical for unknown users (no user enumeration).
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))

_COMMON_PASSWORDS = {
    "password", "password123", "123456789012", "qwertyuiop12", "nfsu@123456", "admin@123456",
    "welcome@1234", "iloveyou1234", "letmein12345", "changeme1234", "p@ssw0rd1234", "gandhinagar1",
}


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str | None) -> bool:
    try:
        return _hasher.verify(hashed or _DUMMY_HASH, raw) and hashed is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    return _hasher.check_needs_rehash(hashed)


def password_problems(raw: str, *, email: str | None = None, name: str | None = None) -> list[str]:
    problems: list[str] = []
    if len(raw) < 12:
        problems.append("Password must be at least 12 characters long.")
    if len(raw) > 128:
        problems.append("Password must be at most 128 characters long.")
    classes = sum(
        any(c in group for c in raw)
        for group in (string.ascii_lowercase, string.ascii_uppercase, string.digits, string.punctuation)
    )
    if classes < 3:
        problems.append("Use at least three of: lowercase, uppercase, digits, symbols.")
    lowered = raw.lower()
    if lowered in _COMMON_PASSWORDS:
        problems.append("This password is too common.")
    for token in filter(None, [(email or "").split("@")[0].lower(), *(name or "").lower().split()]):
        if len(token) >= 4 and token in lowered:
            problems.append("Password must not contain your name or email.")
            break
    return problems


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(token: str) -> str:
    """Keyed hash so a DB dump alone cannot be used to forge/lookup session tokens."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(12))
    return f"{core}-{secrets.choice('!@#$%^&*')}{secrets.randbelow(90) + 10}"


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
