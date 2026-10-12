"""AtomOS password encryption compatible with Node.js publicEncrypt defaults.

Protocol reference: https://github.com/jerry-yu/deeper-device-mcp/blob/master/src/functions.ts
Public key reference: https://github.com/jerry-yu/deeper-device-mcp/blob/master/src/public.ts
"""
import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxZ9YwQ1CVM4zNHVNPxoD
Sz6uFGEcyHUOFkoA2hnijjJccCNRGnYlQmnCmaKPtCPiJ26ibXcL9BpfputJpE7Q
cJcJx8CN0Pr/MceYQraFS3UG+zNdI6tGzLDGrBoB+5WFSbK6aOdHFJfcoBfdULHb
g2eGp2IJwSPal3lFNwE/oTL3K1z7EiwbDq0LrY7FcwMGmG3EFaGtMxRy/cq3r0xR
M1V7WIu1I6gw463luLs6NFCdrY/fiXoSrXRf6sOTZClXeRhKjA6c0wLIxizgw6ll
4EeffYVBQSKlEjJJR2y7cxxbp1XkC19evxe0DYbnsemogDcSkmDCj75hsgwuzoTM
FwIDAQAB
-----END PUBLIC KEY-----"""


class InvalidPassword(ValueError):
    """The supplied password cannot be prepared for AtomOS."""


def encrypt_password(password, public_key=PUBLIC_KEY):
    """Encode UTF-8, RSA-OAEP SHA-1 / MGF1 SHA-1, then Base64.

    OAEP uses random padding, so ciphertexts for the same password differ.
    """
    if not isinstance(password, str) or not password:
        raise InvalidPassword("Password must not be empty")
    try:
        key = serialization.load_pem_public_key(public_key)
        if not isinstance(key, rsa.RSAPublicKey):
            raise InvalidPassword("Expected an RSA public key")
        encoded = password.encode("utf-8")
        if len(encoded) > key.key_size // 8 - 2 * hashes.SHA1().digest_size - 2:
            raise InvalidPassword("Password is too long for this RSA key")
        encrypted = key.encrypt(encoded, padding.OAEP(
            mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None,
        ))
        return base64.b64encode(encrypted).decode("ascii")
    except (ValueError, TypeError, UnicodeError) as err:
        if isinstance(err, InvalidPassword):
            raise
        raise InvalidPassword("Cannot encrypt password") from err


def prepare_credentials(data):
    """Encrypt fresh plaintext form input without changing existing saved secrets.

    This helper is only used for configuration form submissions. Runtime login
    sends the already encrypted secret directly, including legacy config entries.
    An old stored mode flag must not bypass encryption of a newly entered password.
    """
    prepared = dict(data)
    prepared.pop("password_is_encrypted", None)
    prepared["password"] = encrypt_password(prepared.get("password"))
    return prepared
