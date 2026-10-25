"""Authenticated encryption for application secrets stored in the settings table."""
import base64
import hashlib

from cryptography.fernet import Fernet


def fernet_for_secret(secret):
    """Derive a Fernet key from a high-entropy private environment secret.

    The environment secret can be any random string; it is never returned to the browser.
    Keep it stable. Rotating it without decrypting/re-encrypting stored values makes them unreadable.
    """
    if not secret or not isinstance(secret, str):
        raise ValueError("An encryption secret is required")
    material = hashlib.sha256(b"coaching-institute-smtp-v1:" + secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(material))
