"""
AES-128-CBC decryption for encrypted frames from ESP32 Xiaozhi Watcher.

Encrypted format (from ESP32):
    IV (16 bytes) || AES-CBC ciphertext (PKCS7 padded)

The pre-shared key must match the one in the ESP32 firmware (crypto_utils.cc).
"""

import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding


# Default key — MUST match the key in ESP32 firmware (crypto_utils.cc).
# Override via environment variable ENCRYPTION_KEY.
_DEFAULT_KEY = b"xiaozhi-watcher1"  # exactly 16 bytes for AES-128


def _get_key() -> bytes:
    """Return the 16-byte AES-128 key from environment or default."""
    env_key = os.getenv("ENCRYPTION_KEY", "")
    if env_key:
        key_bytes = env_key.encode("utf-8")
        if len(key_bytes) < 16:
            key_bytes = key_bytes.ljust(16, b"0")
        return key_bytes[:16]
    return _DEFAULT_KEY


def decrypt_frame(encrypted_data: bytes) -> bytes:
    """
    Decrypt a frame encrypted by the ESP32.

    Args:
        encrypted_data: IV (16 bytes) + ciphertext

    Returns:
        Decrypted plaintext (JPEG bytes)

    Raises:
        ValueError: if the data is too short or decryption fails
    """
    if len(encrypted_data) < 32:
        raise ValueError(
            f"Encrypted data too short: {len(encrypted_data)} bytes "
            f"(need at least 16 IV + 16 ciphertext)"
        )

    iv = encrypted_data[:16]
    ciphertext = encrypted_data[16:]

    if len(ciphertext) % 16 != 0:
        raise ValueError(
            f"Ciphertext length {len(ciphertext)} is not a multiple of 16"
        )

    key = _get_key()

    # AES-128-CBC decrypt
    cipher = Cipher(algorithms.AES128(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

    # Remove PKCS7 padding
    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()

    return plaintext


def try_decrypt(data: bytes) -> bytes:
    """
    Try to decrypt. If it looks like raw JPEG (starts with 0xFF 0xD8),
    return as-is. Otherwise attempt AES-CBC decryption.

    This provides backward compatibility with unencrypted frames.
    """
    if len(data) >= 2 and data[0] == 0xFF and data[1] == 0xD8:
        # Looks like a raw JPEG — return unchanged
        return data
    return decrypt_frame(data)
