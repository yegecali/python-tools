"""Project settings, read from the .env file in the project root.

Only the standard library is used. Real environment variables take priority over .env.
Relative paths are counted from the project root, not from the current directory.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


def _load_env_file(path):
    if not path.is_file():
        return
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            sys.exit(f"[x] {path.name} linea {number}: falta '=' (formato CLAVE=valor)")
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


_load_env_file(ENV_FILE)


def get(name, default):
    value = os.environ.get(name, "").strip()
    return value or default


def get_int(name, default):
    value = get(name, str(default))
    try:
        return int(value)
    except ValueError:
        sys.exit(f"[x] {name} debe ser un numero entero, valor actual: {value!r}")


def get_choice(name, default, choices):
    value = get(name, default)
    if value not in choices:
        sys.exit(f"[x] {name} debe ser uno de {', '.join(map(str, choices))}, valor actual: {value!r}")
    return value


def get_path(name, default):
    path = Path(get(name, default)).expanduser()
    return path if path.is_absolute() else ROOT / path


# Shared file locations and defaults. Every module reads them from here.
DOMAINS_FILE = get_path("DOMAINS_FILE", "config/domains.json")
JAVA_CONFIG_FILE = get_path("JAVA_CONFIG_FILE", "config/java.json")
MAVEN_CONFIG_FILE = get_path("MAVEN_CONFIG_FILE", "config/maven.json")
KEYS_DIR = get_path("KEYS_DIR", "keys")
PUBLIC_KEY_FILE = get_path("PUBLIC_KEY_FILE", "keys/rsa_public.pem")
PRIVATE_KEY_FILE = get_path("PRIVATE_KEY_FILE", "keys/rsa_private.pem")
RSA_KEY_BITS = get_int("RSA_KEY_BITS", 2048)
QR_ERROR_CORRECTION = get_choice("QR_ERROR_CORRECTION", "M", ["L", "M", "Q", "H"])
QR_BOX_SIZE = get_int("QR_BOX_SIZE", 10)
QR_CHUNK_SIZE = get_int("QR_CHUNK_SIZE", 1200)
CERT_FETCH_TIMEOUT = get_int("CERT_FETCH_TIMEOUT", 20)
CERT_FETCH_ATTEMPTS = get_int("CERT_FETCH_ATTEMPTS", 3)
CERT_FETCH_RETRY_DELAY = get_int("CERT_FETCH_RETRY_DELAY", 2)
CERT_FETCH_WORKERS = get_int("CERT_FETCH_WORKERS", 4)
AUDIT_LOG_FILE = get_path("AUDIT_LOG_FILE", "logs/audit.log")
