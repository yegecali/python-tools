#!/usr/bin/env python3
"""Download the TLS certificates of the domains listed in config/domains.json and
import them into the cacerts truststore of a Java installation.

config/domains.json must contain an array, e.g.:
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

import project_settings

DOMAINS_FILE = project_settings.get_path("DOMAINS_FILE", "config/domains.json")
CERTS_DIR = "certs"
DEFAULT_PASSWORD = project_settings.get("CACERTS_PASSWORD", "changeit")
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
    print(f"  Conectando a {host}:{port} ...")
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            print(f"  Handshake TLS completo: {tls.version()}, cifrado {tls.cipher()[0]}")
            der = tls.getpeercert(binary_form=True)
    print(f"  Certificado recibido ({len(der)} bytes)")
    return ssl.DER_cert_to_PEM_cert(der)


def run_keytool(java_home, *args):
    """Print the keytool command about to run (password masked), then run it."""
    command = [str(keytool_path(java_home)), *args]
    shown, mask_next = [], False
    for arg in command:
        if mask_next:
            shown.append("******")
            mask_next = False
            continue
        shown.append(arg)
        mask_next = arg == "-storepass"
    print(f"  $ {subprocess.list2cmdline(shown)}")
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        # No explicit encoding: keytool writes in the console code page (cp850/cp1252 on Windows)
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

    if not DOMAINS_FILE.exists():
        sys.exit(f"[x] No existe {DOMAINS_FILE} (copia config/domains.example.json)")

    hosts = load_hosts(DOMAINS_FILE)
    if not hosts:
        sys.exit("[x] config/domains.json no tiene dominios validos")

    print(f"\nJava:     {java_home}")
    print(f"cacerts:  {cacerts}")
    print(f"Dominios: {len(hosts)}")

    password = getpass.getpass(f"\nContrasena del cacerts [{DEFAULT_PASSWORD}]: ") or DEFAULT_PASSWORD

    print("\nVerificando contrasena:")
    check = run_keytool(java_home, "-list", "-keystore", str(cacerts), "-storepass", password)
    if check.returncode != 0:
        sys.exit(f"[x] No se pudo abrir cacerts (contrasena incorrecta?):\n{check.stderr.strip()}")
    print("  OK")

    backup = cacerts.with_name(cacerts.name + ".bak")
    if not backup.exists():
        shutil.copy2(cacerts, backup)
        print(f"\n[+] Backup creado: {backup}")

    certs_dir = java_home / CERTS_DIR
    certs_dir.mkdir(exist_ok=True)

    installed, failed = [], []
    for index, (host, port) in enumerate(hosts, 1):
        alias = host if port == 443 else f"{host}_{port}"
        print(f"\n[{index}/{len(hosts)}] {alias}")

        try:
            pem = fetch_pem(host, port)
        except OSError as error:
            print(f"  [x] No se pudo descargar el certificado: {error}")
            failed.append(alias)
            continue

        pem_path = certs_dir / f"{alias}.crt"
        # Write bytes so Windows does not turn the line endings into CRLF
        pem_path.write_bytes(pem.encode("ascii"))
        print(f"  Guardado en: {pem_path}")

        print("  Datos del certificado:")
        info = run_keytool(java_home, "-printcert", "-file", str(pem_path))
        # Keep only the header (owner, issuer, validity, fingerprints); the rest is extensions
        lines = [line for line in info.stdout.splitlines() if line.strip()][:7]
        for line in lines or [info.stderr.strip()]:
            print(f"    {line}")

        # Remove a previous entry with the same alias so the import replaces it.
        print("  Eliminando entrada anterior (si existe):")
        run_keytool(java_home, "-delete", "-alias", alias, "-keystore", str(cacerts), "-storepass", password)

        print("  Importando en cacerts:")
        result = run_keytool(
            java_home,
            "-importcert", "-noprompt", "-trustcacerts",
            "-alias", alias,
            "-file", str(pem_path),
            "-keystore", str(cacerts),
            "-storepass", password,
        )
        if result.returncode == 0:
            print("  [+] Importado")
            installed.append(alias)
        else:
            print(f"  [x] Error al importar:\n{result.stderr.strip()}")
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
