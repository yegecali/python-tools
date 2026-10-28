"""Shared fixtures. Keys are generated once per test session, never stored in the repository."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _write_key_pair(directory, prefix):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path = directory / f"{prefix}_public.pem"
    private_path = directory / f"{prefix}_private.pem"
    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return public_path, private_path


@pytest.fixture(scope="session")
def rsa_key_files(tmp_path_factory):
    """(public, private) PEM paths of a key pair without passphrase."""
    return _write_key_pair(tmp_path_factory.mktemp("keys"), "main")


@pytest.fixture(scope="session")
def other_rsa_key_files(tmp_path_factory):
    """A second, unrelated key pair, used to check that decryption fails with the wrong key."""
    return _write_key_pair(tmp_path_factory.mktemp("other_keys"), "other")


@pytest.fixture(autouse=True)
def isolated_audit_log(tmp_path, monkeypatch):
    """Tests write their audit trail to a temporary file, never to the project's logs folder."""
    import audit

    monkeypatch.setattr(audit, "AUDIT_FILE", tmp_path / "audit.log")
    return tmp_path / "audit.log"
