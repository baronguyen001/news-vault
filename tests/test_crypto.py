from __future__ import annotations

from pathlib import Path

import pytest

from newsvault.crypto import (
    MAGIC,
    DecryptionError,
    decrypt_payload,
    encrypt_payload,
    new_salt,
    write_encrypted,
)

PAYLOAD = {
    "text": "Tiếng Việt có dấu 😊",
    "nested": {"a": [1, 2, 3], "b": True},
    "many": list(range(200)),
}


def test_roundtrip_nested_vietnamese() -> None:
    password = "mật khẩu bí mật"
    blob = encrypt_payload(PAYLOAD, password)
    assert blob.startswith(MAGIC)
    assert decrypt_payload(blob, password) == PAYLOAD


def test_wrong_password_raises() -> None:
    blob = encrypt_payload(PAYLOAD, "correct horse")
    with pytest.raises(DecryptionError):
        decrypt_payload(blob, "wrong horse")


def test_flipped_byte_raises() -> None:
    blob = bytearray(encrypt_payload(PAYLOAD, "pw"))
    blob[-5] ^= 0xFF
    with pytest.raises(DecryptionError):
        decrypt_payload(bytes(blob), "pw")


def test_truncated_blob_raises() -> None:
    blob = encrypt_payload(PAYLOAD, "pw")
    with pytest.raises(DecryptionError):
        decrypt_payload(blob[:-20], "pw")


def test_corrupted_magic_raises() -> None:
    blob = bytearray(encrypt_payload(PAYLOAD, "pw"))
    blob[0] = 0x00
    with pytest.raises(DecryptionError):
        decrypt_payload(bytes(blob), "pw")


def test_same_salt_different_iv() -> None:
    salt = new_salt()
    first = encrypt_payload(PAYLOAD, "pw", salt=salt)
    second = encrypt_payload(PAYLOAD, "pw", salt=salt)
    assert first != second
    assert decrypt_payload(first, "pw") == PAYLOAD
    assert decrypt_payload(second, "pw") == PAYLOAD


def test_write_encrypted_creates_parents(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "file.enc"
    salt = new_salt()
    written = write_encrypted(path, PAYLOAD, "pw", salt=salt)
    assert path.exists()
    assert written > 0
    content = path.read_bytes()
    assert content.startswith(MAGIC)
    assert decrypt_payload(content, "pw") == PAYLOAD
