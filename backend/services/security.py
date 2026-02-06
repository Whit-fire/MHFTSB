import os
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecurityService:
    @staticmethod
    def derive_key(passphrase: str, salt: bytes = None):
        if salt is None:
            salt = os.urandom(16)
        key = hashlib.pbkdf2_hmac('sha256', passphrase.encode(), salt, 100000)
        return key, salt

    @staticmethod
    def encrypt(plaintext: str, passphrase: str) -> str:
        key, salt = SecurityService.derive_key(passphrase)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
        payload = salt + nonce + ciphertext
        return base64.b64encode(payload).decode()

    @staticmethod
    def decrypt(encrypted: str, passphrase: str) -> str:
        payload = base64.b64decode(encrypted)
        salt = payload[:16]
        nonce = payload[16:28]
        ciphertext = payload[28:]
        key, _ = SecurityService.derive_key(passphrase, salt)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
