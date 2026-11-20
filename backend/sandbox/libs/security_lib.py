"""libs.security — TBC v7.1.2 cryptographic toolkit (HMAC, AES/Fernet, hashing, Ed25519).

Method names below match the official TBC docs exactly:
  hmac_sign, hmac_verify, ed25519_verify, verify_coinsway_webhook,
  generate_key, encrypt, decrypt, sha256, sha512, md5

Legacy/alternate-casing helpers (generateKey, aes_encrypt, encryptAES, ...) are kept
as aliases so existing bot code built against earlier builds keeps working.
"""
import hashlib
import hmac
import base64
import os


class SecurityLib:
    # ---------------------------------------------------------------- HMAC
    def hmac_sign(self, secret, data, algorithm="sha256"):
        key_b = secret.encode() if isinstance(secret, str) else secret
        data_b = data.encode() if isinstance(data, str) else data
        algo = (algorithm or "sha256").lower()
        digestmod = {"sha512": hashlib.sha512, "md5": hashlib.md5}.get(algo, hashlib.sha256)
        return hmac.new(key_b, data_b, digestmod).hexdigest()

    def hmac_verify(self, secret, data, signature, algorithm="sha256"):
        expected = self.hmac_sign(secret, data, algorithm=algorithm)
        try:
            return hmac.compare_digest(str(expected), str(signature))
        except Exception:
            return False

    # -------------------------------------------------------------- Hashing
    def hash(self, data, algorithm="sha256"):
        data_b = data.encode() if isinstance(data, str) else data
        algo = (algorithm or "sha256").lower()
        if algo == "sha512":
            return hashlib.sha512(data_b).hexdigest()
        if algo == "md5":
            return hashlib.md5(data_b).hexdigest()
        if algo == "sha1":
            return hashlib.sha1(data_b).hexdigest()
        return hashlib.sha256(data_b).hexdigest()

    def sha256(self, data):
        return self.hash(data, "sha256")

    def sha512(self, data):
        return self.hash(data, "sha512")

    def md5(self, data):
        return self.hash(data, "md5")

    # ------------------------------------------------- AES (Fernet) — docs API
    def generate_key(self):
        """Generate a new Fernet encryption key (urlsafe-base64, 32 bytes)."""
        try:
            from cryptography.fernet import Fernet
            return Fernet.generate_key().decode()
        except ImportError:
            import secrets
            return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()

    def encrypt(self, plaintext, key):
        """Encrypt a string with a Fernet key (from generate_key()). Returns a token string."""
        try:
            from cryptography.fernet import Fernet
            key_b = key.encode() if isinstance(key, str) else key
            f = Fernet(key_b)
            data = plaintext.encode() if isinstance(plaintext, str) else plaintext
            return f.encrypt(data).decode()
        except Exception:
            # Fallback: derive a Fernet-compatible key from an arbitrary passphrase
            derived = base64.urlsafe_b64encode(hashlib.sha256(
                key.encode() if isinstance(key, str) else key
            ).digest())
            from cryptography.fernet import Fernet
            f = Fernet(derived)
            data = plaintext.encode() if isinstance(plaintext, str) else plaintext
            return f.encrypt(data).decode()

    def decrypt(self, token, key):
        """Decrypt a Fernet token produced by encrypt(). Returns the original string."""
        try:
            from cryptography.fernet import Fernet
            key_b = key.encode() if isinstance(key, str) else key
            f = Fernet(key_b)
            out = f.decrypt(token.encode() if isinstance(token, str) else token)
            return out.decode(errors="ignore")
        except Exception:
            derived = base64.urlsafe_b64encode(hashlib.sha256(
                key.encode() if isinstance(key, str) else key
            ).digest())
            from cryptography.fernet import Fernet
            f = Fernet(derived)
            out = f.decrypt(token.encode() if isinstance(token, str) else token)
            return out.decode(errors="ignore")

    # ------------------------------------------------ AES-CBC (legacy helper)
    def aes_encrypt(self, key, plaintext):
        """AES-256-CBC encrypt; key is stretched via SHA256. Returns base64(iv+ciphertext)."""
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            k = hashlib.sha256(key.encode() if isinstance(key, str) else key).digest()
            data = plaintext.encode() if isinstance(plaintext, str) else plaintext
            out = bytes(b ^ k[i % 32] for i, b in enumerate(data))
            return base64.b64encode(out).decode()
        key_b = hashlib.sha256(key.encode() if isinstance(key, str) else key).digest()
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(key_b), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        data = plaintext.encode() if isinstance(plaintext, str) else plaintext
        pad = 16 - (len(data) % 16)
        data = data + bytes([pad] * pad)
        ct = encryptor.update(data) + encryptor.finalize()
        return base64.b64encode(iv + ct).decode()

    def aes_decrypt(self, key, token):
        try:
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            k = hashlib.sha256(key.encode() if isinstance(key, str) else key).digest()
            raw = base64.b64decode(token)
            out = bytes(b ^ k[i % 32] for i, b in enumerate(raw))
            return out.decode(errors="ignore")
        key_b = hashlib.sha256(key.encode() if isinstance(key, str) else key).digest()
        raw = base64.b64decode(token)
        iv, ct = raw[:16], raw[16:]
        cipher = Cipher(algorithms.AES(key_b), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        data = decryptor.update(ct) + decryptor.finalize()
        pad = data[-1]
        if 1 <= pad <= 16:
            data = data[:-pad]
        return data.decode(errors="ignore")

    # ---------------------------------------------------------------- Ed25519
    def ed25519_generate(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            priv = Ed25519PrivateKey.generate()
            priv_bytes = priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            pub_bytes = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return {
                "private_key": priv_bytes.hex(),
                "public_key": pub_bytes.hex(),
            }
        except Exception as e:
            return {"error": str(e)}

    def ed25519_sign(self, private_key_hex, data):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(str(private_key_hex).strip()))
            data_b = data.encode() if isinstance(data, str) else data
            return priv.sign(data_b).hex()
        except Exception as e:
            return {"error": str(e)}

    def ed25519_verify(self, public_key_hex, signature_hex, data):
        """Verify an Ed25519 signature. Matches the official TBC signature order exactly:
        ed25519_verify(public_key_hex, signature_hex, data)."""
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(str(public_key_hex).strip()))
            data_b = data if isinstance(data, (bytes, bytearray)) else str(data).encode()
            pub.verify(bytes.fromhex(str(signature_hex).strip()), data_b)
            return True
        except Exception:
            return False

    # kept for backward-compatibility with earlier builds that used base64 + a
    # different argument order: ed25519_verify_b64(public_key_b64, data, signature_b64)
    def ed25519_verify_b64(self, public_key_b64, data, signature_b64):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
            data_b = data.encode() if isinstance(data, str) else data
            pub.verify(base64.b64decode(signature_b64), data_b)
            return True
        except Exception:
            return False

    # old name, same hex behaviour as the new ed25519_verify — kept as an alias
    def ed25519_verify_hex(self, public_key_hex, signature_hex, data):
        return self.ed25519_verify(public_key_hex, signature_hex, data)

    def verify_coinsway_webhook(self, public_key, signature, data):
        """Coinsway payment webhook verification (Ed25519 over raw body)."""
        if not public_key or not signature:
            return False
        return self.ed25519_verify(public_key, signature, data)

    # ------------------------------------------------------------ Aliases
    def encryptAES(self, key, plaintext):
        return self.aes_encrypt(key, plaintext)

    def decryptAES(self, key, token):
        return self.aes_decrypt(key, token)

    def hmacSign(self, key, data, algorithm="sha256"):
        return self.hmac_sign(key, data, algorithm=algorithm)

    def hmacVerify(self, key, data, signature, algorithm="sha256"):
        return self.hmac_verify(key, data, signature, algorithm=algorithm)

    def generateKey(self, length=32):
        import secrets
        return base64.urlsafe_b64encode(secrets.token_bytes(int(length))).decode().rstrip("=")

    def signHMAC(self, key, data, algorithm="sha256"):
        return self.hmac_sign(key, data, algorithm=algorithm)

    def verifyHMAC(self, key, data, signature, algorithm="sha256"):
        return self.hmac_verify(key, data, signature, algorithm=algorithm)
