import base64
import getpass
import json

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization

import rsa_crypt
import rsa_keygen


def test_roundtrip_short_text(rsa_key_files):
    public_key = rsa_crypt.load_public_key(rsa_key_files[0])
    private_key = rsa_crypt.load_private_key(rsa_key_files[1])

    payload = rsa_crypt.encrypt(public_key, "hola mundo ñ 🔑".encode("utf-8"))

    assert rsa_crypt.decrypt(private_key, payload).decode("utf-8") == "hola mundo ñ 🔑"


def test_roundtrip_value_larger_than_rsa_limit(rsa_key_files):
    # Plain RSA-OAEP cannot hold this; the hybrid AES scheme must.
    public_key = rsa_crypt.load_public_key(rsa_key_files[0])
    private_key = rsa_crypt.load_private_key(rsa_key_files[1])
    value = b"x" * 20_000

    assert rsa_crypt.decrypt(private_key, rsa_crypt.encrypt(public_key, value)) == value


def test_payload_has_expected_fields_and_no_plaintext(rsa_key_files):
    public_key = rsa_crypt.load_public_key(rsa_key_files[0])
    payload = rsa_crypt.encrypt(public_key, b"secreto-123")

    assert set(payload) == {"v", "key", "nonce", "data"}
    assert payload["v"] == rsa_crypt.FORMAT_VERSION
    assert b"secreto-123" not in json.dumps(payload).encode()


def test_wrong_private_key_is_rejected(rsa_key_files, other_rsa_key_files):
    public_key = rsa_crypt.load_public_key(rsa_key_files[0])
    wrong_private = rsa_crypt.load_private_key(other_rsa_key_files[1])

    with pytest.raises(ValueError):
        rsa_crypt.decrypt(wrong_private, rsa_crypt.encrypt(public_key, b"dato"))


def test_tampered_ciphertext_is_rejected(rsa_key_files):
    public_key = rsa_crypt.load_public_key(rsa_key_files[0])
    private_key = rsa_crypt.load_private_key(rsa_key_files[1])
    payload = rsa_crypt.encrypt(public_key, b"dato importante")

    data = bytearray(base64.b64decode(payload["data"]))
    data[0] ^= 0x01
    payload["data"] = base64.b64encode(bytes(data)).decode("ascii")

    with pytest.raises(InvalidTag):
        rsa_crypt.decrypt(private_key, payload)


def test_unsupported_format_version_is_rejected(rsa_key_files):
    private_key = rsa_crypt.load_private_key(rsa_key_files[1])
    with pytest.raises(ValueError, match="version"):
        rsa_crypt.decrypt(private_key, {"v": 99, "key": "", "nonce": "", "data": ""})


def test_keygen_writes_matching_pair_with_private_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "")

    rsa_keygen.main(["--name", "unit", "--bits", "2048", "--out", str(tmp_path)])

    private_path = tmp_path / "unit_private.pem"
    public_path = tmp_path / "unit_public.pem"
    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    public_key = serialization.load_pem_public_key(public_path.read_bytes())
    assert private_key.public_key().public_numbers() == public_key.public_numbers()
    if rsa_keygen.os.name == "posix":
        assert private_path.stat().st_mode & 0o777 == 0o600


def test_keygen_refuses_to_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": "")
    args = ["--name", "dup", "--bits", "2048", "--out", str(tmp_path)]
    rsa_keygen.main(args)

    with pytest.raises(SystemExit, match="--force"):
        rsa_keygen.main(args)
    rsa_keygen.main([*args, "--force"])  # --force overwrites


def test_keygen_with_passphrase_encrypts_private_key(tmp_path, monkeypatch):
    answers = iter(["secreto", "secreto"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))

    rsa_keygen.main(["--name", "pw", "--bits", "2048", "--out", str(tmp_path)])

    pem = (tmp_path / "pw_private.pem").read_bytes()
    with pytest.raises(TypeError):  # no password given: the key must be encrypted
        serialization.load_pem_private_key(pem, password=None)
    serialization.load_pem_private_key(pem, password=b"secreto")


def test_keygen_rejects_mismatched_passphrases(tmp_path, monkeypatch):
    answers = iter(["uno", "dos"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt="": next(answers))
    with pytest.raises(SystemExit, match="no coinciden"):
        rsa_keygen.main(["--name", "mal", "--bits", "2048", "--out", str(tmp_path)])


def test_missing_public_key_explains_how_to_generate_keys(tmp_path):
    with pytest.raises(SystemExit, match="Generar llaves RSA"):
        rsa_crypt.load_public_key(tmp_path / "rsa_public.pem")
