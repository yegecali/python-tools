"""Checks that the configuration and the key files are usable before running a tool.

Returns a list of Check results. Printing them is up to the caller (see main.py).
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import java_cacerts_installer
import project_settings
from errors import ToolError

JAVA_EXE = "java.exe" if sys.platform == "win32" else "java"
MAVEN_EXE = "mvn.cmd" if sys.platform == "win32" else "mvn"
KEYTOOL_TIMEOUT = 20


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _read_json(path):
    if not path.is_file():
        raise ToolError(f"no existe {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ToolError(f"no es JSON valido: {error}") from error


def _versions(path):
    data = _read_json(path)
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, dict) or not versions:
        raise ToolError("'versions' debe ser un objeto con al menos una entrada")
    return versions


def check_tool_versions(name, path, executable):
    """Every configured version must point to a folder that contains bin/<executable>."""
    try:
        versions = _versions(path)
    except ToolError as error:
        return [Check(name, False, f"{path.name}: {error}")]
    checks = []
    for version, home in versions.items():
        exe = Path(home) / "bin" / executable
        found = exe.is_file()
        checks.append(Check(f"{name} {version}", found, str(exe) if found else f"no encuentro {exe}"))
    return checks


def check_domains(path):
    try:
        data = _read_json(path)
    except ToolError as error:
        return Check("Dominios", False, f"{path.name}: {error}")
    valid = isinstance(data, list) and bool(data) and all(isinstance(item, str) for item in data)
    if not valid:
        return Check("Dominios", False, f"{path.name} debe ser una lista de textos con al menos un dominio")
    return Check("Dominios", True, f"{len(data)} dominios en {path.name}")


def check_public_key(path):
    if not path.is_file():
        return Check("Llave publica", False, f"no existe {path}. Genera las llaves con la opcion 2")
    text = path.read_text(encoding="utf-8", errors="replace")
    if "PUBLIC KEY" not in text:
        return Check("Llave publica", False, f"{path} no es una llave publica PEM")
    return Check("Llave publica", True, str(path))


def check_private_key(path):
    if not path.is_file():
        return Check("Llave privada", False, f"no existe {path}. Genera las llaves con la opcion 2")
    text = path.read_text(encoding="utf-8", errors="replace")
    if "PRIVATE KEY" not in text:
        return Check("Llave privada", False, f"{path} no es una llave privada PEM")
    protected = "ENCRYPTED" in text
    return Check("Llave privada", True, f"{path} ({'con passphrase' if protected else 'sin passphrase'})")


def java_homes(path):
    try:
        return list(_versions(path).values())
    except ToolError:
        return []


def check_keytool(homes):
    """Run keytool from the first configured Java that has it, to confirm it starts."""
    for home in homes:
        keytool = Path(home) / "bin" / java_cacerts_installer.KEYTOOL_NAME
        if not keytool.is_file():
            continue
        try:
            result = subprocess.run([str(keytool), "-help"], capture_output=True, timeout=KEYTOOL_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as error:
            return Check("keytool", False, f"no responde: {error}")
        if result.returncode != 0:
            return Check("keytool", False, f"responde con codigo {result.returncode}")
        return Check("keytool", True, str(keytool))
    return Check("keytool", False, "no encuentro keytool en ninguna version de Java configurada")


def run_checks(java_config=None, maven_config=None, domains=None, public_key=None, private_key=None):
    java_config = java_config or project_settings.JAVA_CONFIG_FILE
    maven_config = maven_config or project_settings.MAVEN_CONFIG_FILE
    domains = domains or project_settings.DOMAINS_FILE
    public_key = public_key or project_settings.PUBLIC_KEY_FILE
    private_key = private_key or project_settings.PRIVATE_KEY_FILE

    checks = check_tool_versions("Java", java_config, JAVA_EXE)
    checks += check_tool_versions("Maven", maven_config, MAVEN_EXE)
    checks.append(check_domains(domains))
    checks.append(check_public_key(public_key))
    checks.append(check_private_key(private_key))
    checks.append(check_keytool(java_homes(java_config)))
    return checks
