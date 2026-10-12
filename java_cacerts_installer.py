#!/usr/bin/env python3
"""Download the TLS certificates of the domains listed in domains.json and
import them into the cacerts truststore of a Java installation.

domains.json must live inside the Java directory and contain an array, e.g.:
    ["google.com", "artifactory.company.com", "https://nexus.company.com:8443"]
"""

import getpass
import json
import shutil
import socket
import ssl
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

DOMAINS_FILE = "domains.json"
CERTS_DIR = "certs"
DEFAULT_PASSWORD = "changeit"
CACERTS_CANDIDATES = ["lib/security/cacerts", "jre/lib/security/cacerts"]
KEYTOOL_NAME = "keytool.exe" if sys.platform == "win32" else "keytool"


def keytool_path(java_home):
    return java_home / "bin" / KEYTOOL_NAME


def resolve_java_home(raw):
    """Accept JAVA_HOME or a macOS .jdk bundle root (Contents/Home)."""
    base = Path(raw.strip().strip('"').strip("'")).expanduser()
    for candidate in (base, base / "Contents" / "Home"):
        if keytool_path(candidate).exists():
            return candidate
    return None


def find_cacerts(java_home):
    for relative in CACERTS_CANDIDATES:
        path = java_home / relative
        if path.exists():
            return path
    return None


def load_hosts(domains_path):
    # utf-8-sig tolerates the BOM that Windows Notepad adds
    data = json.loads(domains_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError(f"{domains_path} debe contener un array de strings")

    hosts = []
    for entry in data:
        parsed = urlparse(entry if "://" in entry else f"//{entry}")
        if not parsed.hostname:
            print(f"[!] Entrada ignorada, no es un dominio valido: {entry}")
            continue
        hosts.append((parsed.hostname, parsed.port or 443))
    return list(dict.fromkeys(hosts))


def fetch_pem(host, port, timeout=10):
    """Read the server certificate without validating it: the goal is to trust it."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    return ssl.DER_cert_to_PEM_cert(der)


def keytool(java_home, *args):
    return subprocess.run(
        [str(keytool_path(java_home)), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main():
    raw = input("Directorio de tu Java (JAVA_HOME): ").strip()
    java_home = resolve_java_home(raw)
    if java_home is None:
        sys.exit(f"[x] No encuentro bin/keytool dentro de: {raw}")

    cacerts = find_cacerts(java_home)
    if cacerts is None:
        sys.exit(f"[x] No encuentro cacerts dentro de: {java_home}")

    domains_path = java_home / DOMAINS_FILE
    if not domains_path.exists():
        sys.exit(f"[x] No existe {DOMAINS_FILE} en: {java_home}")

    hosts = load_hosts(domains_path)
    if not hosts:
        sys.exit("[x] domains.json no tiene dominios validos")

    password = getpass.getpass(f"Contrasena del cacerts [{DEFAULT_PASSWORD}]: ") or DEFAULT_PASSWORD

    check = keytool(java_home, "-list", "-keystore", str(cacerts), "-storepass", password)
    if check.returncode != 0:
        sys.exit(f"[x] No se pudo abrir cacerts (contrasena incorrecta?):\n{check.stderr.strip()}")

    backup = cacerts.with_name(cacerts.name + ".bak")
    if not backup.exists():
        shutil.copy2(cacerts, backup)
        print(f"[+] Backup creado: {backup}")

    certs_dir = java_home / CERTS_DIR
    certs_dir.mkdir(exist_ok=True)

    installed, failed = [], []
    for host, port in hosts:
        alias = host if port == 443 else f"{host}_{port}"
        try:
            pem = fetch_pem(host, port)
        except OSError as error:
            print(f"[x] {alias}: no se pudo descargar el certificado ({error})")
            failed.append(alias)
            continue

        pem_path = certs_dir / f"{alias}.crt"
        pem_path.write_text(pem, encoding="utf-8")
        print(f"[+] {alias}: certificado guardado en {pem_path}")

        # Remove a previous entry with the same alias so the import replaces it.
        keytool(java_home, "-delete", "-alias", alias, "-keystore", str(cacerts), "-storepass", password)
        result = keytool(
            java_home,
            "-importcert", "-noprompt", "-trustcacerts",
            "-alias", alias,
            "-file", str(pem_path),
            "-keystore", str(cacerts),
            "-storepass", password,
        )
        if result.returncode == 0:
            print(f"[+] {alias}: importado en cacerts")
            installed.append(alias)
        else:
            print(f"[x] {alias}: error al importar\n{result.stderr.strip()}")
            failed.append(alias)

    print(f"\nResumen: {len(installed)} instalados, {len(failed)} con error")
    if failed:
        print("Con error:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[x] Cancelado")
