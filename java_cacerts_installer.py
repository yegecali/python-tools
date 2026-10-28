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
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from errors import ToolError, run_cli
import ui
import project_settings
import windows_env_setup

DOMAINS_FILE = project_settings.DOMAINS_FILE
CERTS_DIR = "certs"
DEFAULT_PASSWORD = project_settings.get("CACERTS_PASSWORD", "changeit")
# Downloads can fail on a slow or unstable network: wait longer and retry before giving up
CERT_TIMEOUT = project_settings.CERT_FETCH_TIMEOUT
CERT_ATTEMPTS = project_settings.CERT_FETCH_ATTEMPTS
CERT_RETRY_DELAY = project_settings.CERT_FETCH_RETRY_DELAY
CERT_WORKERS = project_settings.CERT_FETCH_WORKERS
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
            print(f"{ui.icon('warn')} Entrada ignorada, no es un dominio valido: {entry}")
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


def download_pem(host, port):
    """Retry fetch_pem with growing waits (2 s, 4 s, ...) before reporting the host as failed."""
    for attempt in range(1, CERT_ATTEMPTS + 1):
        try:
            return fetch_pem(host, port, CERT_TIMEOUT)
        except OSError as error:
            if attempt == CERT_ATTEMPTS:
                raise
            wait = CERT_RETRY_DELAY * 2 ** (attempt - 1)
            print(f"  {ui.icon('warn')} Intento {attempt}/{CERT_ATTEMPTS} fallo: {error}")
            print(f"      Reintentando en {wait} s ...")
            time.sleep(wait)


def alias_for(host, port):
    return host if port == 443 else f"{host}_{port}"


def _download_or_error(entry):
    host, port = entry
    alias = alias_for(host, port)
    try:
        return alias, download_pem(host, port), None
    except OSError as error:
        return alias, None, str(error)


def download_all(hosts):
    """Download the certificates in parallel (the work is network bound).

    Returns (alias, pem, error) in the original order, so the output stays readable.
    """
    with ThreadPoolExecutor(max_workers=CERT_WORKERS) as pool:
        return list(pool.map(_download_or_error, hosts))


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


def ask_java_home():
    """Offer the Java versions from config/java.json; type a path only if there are none."""
    manual = "Directorio de tu Java (JAVA_HOME): "
    if not windows_env_setup.JAVA_CONFIG.exists():
        return input(manual).strip()

    config = windows_env_setup.load_config(windows_env_setup.JAVA_CONFIG)
    options = {**config["versions"], "(otra ruta)": "escribir el directorio a mano"}
    chosen = windows_env_setup.ask_choice("Versiones de Java configuradas:", options)
    if chosen == "(otra ruta)":
        return input(manual).strip()
    return config["versions"][chosen]


def main():
    raw = ask_java_home()
    java_home = resolve_java_home(raw)
    if java_home is None:
        raise ToolError(f"No encuentro bin/keytool dentro de: {raw}")

    cacerts = find_cacerts(java_home)
    if cacerts is None:
        raise ToolError(f"No encuentro cacerts dentro de: {java_home}")

    if not DOMAINS_FILE.exists():
        raise ToolError(f"No existe {DOMAINS_FILE} (copia config/domains.example.json)")

    hosts = load_hosts(DOMAINS_FILE)
    if not hosts:
        raise ToolError("config/domains.json no tiene dominios validos")

    print(f"\nJava:     {java_home}")
    print(f"cacerts:  {cacerts}")
    print(f"Dominios: {len(hosts)}")

    password = getpass.getpass(f"\nContrasena del cacerts [{DEFAULT_PASSWORD}]: ") or DEFAULT_PASSWORD

    print("\nVerificando contrasena:")
    check = run_keytool(java_home, "-list", "-keystore", str(cacerts), "-storepass", password)
    if check.returncode != 0:
        raise ToolError(f"No se pudo abrir cacerts (contrasena incorrecta?):\n{check.stderr.strip()}")
    print("  OK")

    backup = cacerts.with_name(cacerts.name + ".bak")
    if not backup.exists():
        shutil.copy2(cacerts, backup)
        print(f"\n{ui.icon('ok')} Backup creado: {backup}")

    certs_dir = java_home / CERTS_DIR
    certs_dir.mkdir(exist_ok=True)

    print(f"\nDescargando {len(hosts)} certificados ({CERT_WORKERS} en paralelo) ...")
    downloads = download_all(hosts)

    installed, failed = [], []
    for index, (alias, pem, error) in enumerate(downloads, 1):
        print(f"\n[{index}/{len(downloads)}] {alias}")

        if error:
            print(f"  {ui.icon('error')} No se pudo descargar el certificado: {error}")
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
            print(f"  {ui.icon('ok')} Importado")
            installed.append(alias)
        else:
            print(f"  {ui.icon('error')} Error al importar:\n{result.stderr.strip()}")
            failed.append(alias)

    print(f"\nResumen: {len(installed)} instalados, {len(failed)} con error")
    if failed:
        print("Con error:", ", ".join(failed))
        raise ToolError(f"Certificados con error: {', '.join(failed)}")


if __name__ == "__main__":
    run_cli(main)
