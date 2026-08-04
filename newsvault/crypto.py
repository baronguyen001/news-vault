from __future__ import annotations

import functools
import hashlib
import json
import os
import struct
import tempfile
import zlib
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC: bytes = b"NVLT"
VERSION: int = 1
DEFAULT_ITERATIONS: int = 250_000
SALT_BYTES: int = 16
IV_BYTES: int = 12


class DecryptionError(Exception):
    """Raised when an encrypted payload cannot be authenticated or decoded."""


def new_salt() -> bytes:
    """Return a fresh random salt for key derivation."""
    return os.urandom(SALT_BYTES)


@functools.cache
def _derive_key(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )


def derive_key(password: str, salt: bytes, iterations: int = DEFAULT_ITERATIONS) -> bytes:
    """Derive a 32-byte AES key from *password* and *salt* using PBKDF2-HMAC-SHA256.

    Calls are cached so repeated encryption rounds during a long backfill do not
    re-run the full PBKDF2 iteration count.
    """
    return _derive_key(password, salt, iterations)


def encrypt_payload(
    payload: object,
    password: str,
    *,
    salt: bytes | None = None,
    iterations: int = DEFAULT_ITERATIONS,
) -> bytes:
    """Serialize, compress and encrypt a payload into the NVLT container format."""
    if salt is None:
        salt = new_salt()
    iv = os.urandom(IV_BYTES)

    key = derive_key(password, salt, iterations)
    plaintext = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    compressed = zlib.compress(plaintext, 6)

    ciphertext = AESGCM(key).encrypt(iv, compressed, None)

    return (
        MAGIC + struct.pack("B", VERSION) + struct.pack(">I", iterations) + salt + iv + ciphertext
    )


def decrypt_payload(blob: bytes, password: str) -> object:
    """Decrypt and deserialize an NVLT container. Raises DecryptionError on failure."""
    header_len = len(MAGIC) + 1 + 4 + SALT_BYTES + IV_BYTES
    if len(blob) < header_len:
        raise DecryptionError("container is too short")

    if not blob.startswith(MAGIC):
        raise DecryptionError("bad magic")

    version = blob[4]
    if version != VERSION:
        raise DecryptionError(f"unsupported container version {version}")

    iterations = struct.unpack(">I", blob[5:9])[0]
    salt = blob[9:25]
    iv = blob[25:37]
    ciphertext = blob[37:]

    if len(ciphertext) < 16:
        raise DecryptionError("truncated ciphertext")

    key = derive_key(password, salt, iterations)

    try:
        compressed = AESGCM(key).decrypt(iv, ciphertext, None)
    except InvalidTag as exc:
        raise DecryptionError("authentication failed") from exc

    try:
        plaintext = zlib.decompress(compressed)
    except Exception as exc:
        raise DecryptionError("decompression failed") from exc

    try:
        return json.loads(plaintext.decode("utf-8"))
    except Exception as exc:
        raise DecryptionError("json decoding failed") from exc


def write_encrypted(
    path: Path,
    payload: object,
    password: str,
    *,
    salt: bytes,
    iterations: int = DEFAULT_ITERATIONS,
) -> int:
    """Encrypt *payload* and write it to *path* atomically. Returns bytes written."""
    blob = encrypt_payload(payload, password, salt=salt, iterations=iterations)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=".",
        suffix=".tmp",
        delete=False,
    ) as fh:
        temp_path = Path(fh.name)
        try:
            fh.write(blob)
            fh.flush()
            os.fsync(fh.fileno())
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    os.replace(temp_path, path)
    return len(blob)
