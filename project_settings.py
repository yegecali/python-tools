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
