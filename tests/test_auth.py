"""AtomOS encryption and interoperability with Node.js publicEncrypt."""
import base64
import importlib
import json
import shutil
import subprocess
import unittest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa

from test_core import PACKAGE

auth = importlib.import_module(f"{PACKAGE}.auth")


def oaep():
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA1(), label=None)


class PasswordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ephemeral test keys; never use or persist device/user private keys.
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public_pem = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def test_utf8_plaintext_roundtrip(self):
        password = "  пароль-test-🔑  "
        ciphertext = auth.encrypt_password(password, self.public_pem)
        self.assertEqual(self.private.decrypt(base64.b64decode(ciphertext), oaep()), password.encode("utf-8"))

    def test_randomized_oaep(self):
        first = auth.encrypt_password("synthetic-test", self.public_pem)
        second = auth.encrypt_password("synthetic-test", self.public_pem)
        self.assertNotEqual(first, second)

    def test_builtin_public_key_and_ciphertext_length(self):
        key = serialization.load_pem_public_key(auth.PUBLIC_KEY)
        self.assertIsInstance(key, rsa.RSAPublicKey)
        self.assertEqual(key.key_size, 2048)
        ciphertext = auth.encrypt_password("synthetic-test")
        self.assertEqual(len(base64.b64decode(ciphertext, validate=True)), 256)
        self.assertEqual(len(ciphertext), 344)

    def test_length_limit_measured_in_utf8_bytes(self):
        self.assertTrue(auth.encrypt_password("x" * 214))
        for password in ("x" * 215, "я" * 108, "", None):
            with self.assertRaises(auth.InvalidPassword):
                auth.encrypt_password(password)

    def test_legacy_mode_flag_cannot_bypass_encryption_of_new_input(self):
        data = {"username": "test", "password": "synthetic-test", "password_is_encrypted": True}
        prepared = auth.prepare_credentials(data)
        self.assertNotEqual(prepared["password"], data["password"])
        self.assertNotIn("password_is_encrypted", prepared)
        self.assertTrue(data["password_is_encrypted"])

    def test_plain_mode_never_mutates_input_or_persists_plaintext(self):
        data = {"username": "test", "password": "synthetic-test"}
        prepared = auth.prepare_credentials(data)
        self.assertEqual(data["password"], "synthetic-test")
        self.assertNotEqual(prepared["password"], data["password"])
        self.assertNotIn("password_is_encrypted", prepared)
        self.assertEqual(prepared["username"], "test")

    def test_wrong_key_type_rejected(self):
        pem = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        with self.assertRaises(auth.InvalidPassword):
            auth.encrypt_password("synthetic-test", pem)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for interoperability verification")
    def test_nodejs_public_encrypt_compatibility_both_directions(self):
        password = "  synthetic-пароль-🔑  "
        private_pem = self.private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ).decode("ascii")
        python_ciphertext = auth.encrypt_password(password, self.public_pem)
        script = """
const crypto = require('node:crypto');
let chunks = [];
process.stdin.on('data', data => chunks.push(data));
process.stdin.on('end', () => {
    const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    const decoded = crypto.privateDecrypt(input.privateKey, Buffer.from(input.ciphertext, 'base64')).toString('utf8');
    const ciphertext = crypto.publicEncrypt(input.publicKey, Buffer.from(input.password)).toString('base64');
    process.stdout.write(JSON.stringify({ decoded, ciphertext }));
});
"""
        result = subprocess.run([shutil.which("node"), "-e", script], input=json.dumps({
            "privateKey": private_pem, "publicKey": self.public_pem.decode("ascii"),
            "ciphertext": python_ciphertext, "password": password,
        }), text=True, capture_output=True, check=True, timeout=15)
        output = json.loads(result.stdout)
        self.assertEqual(output["decoded"], password)
        self.assertEqual(self.private.decrypt(base64.b64decode(output["ciphertext"]), oaep()), password.encode("utf-8"))
