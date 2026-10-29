"""Password hashing helpers for agent accounts."""

import base64
import binascii
import hashlib
import hmac
import secrets


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_KEY_LENGTH = 32


def hash_password(password: str) -> str:
    """Return a salted scrypt hash suitable for the agents.password_hash column."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LENGTH,
    )
    salt_text = base64.urlsafe_b64encode(salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt_text}${digest_text}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against the supported self-describing scrypt format."""
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = stored_hash.split("$")
        if (
            algorithm != "scrypt"
            or int(n_text) != _SCRYPT_N
            or int(r_text) != _SCRYPT_R
            or int(p_text) != _SCRYPT_P
        ):
            return False
        salt = base64.b64decode(salt_text.encode("ascii"), altchars=b"-_", validate=True)
        expected_digest = base64.b64decode(
            digest_text.encode("ascii"), altchars=b"-_", validate=True
        )
        if len(salt) != 16 or len(expected_digest) != _KEY_LENGTH:
            return False
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return False

    actual_digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=len(expected_digest),
    )
    return hmac.compare_digest(actual_digest, expected_digest)
