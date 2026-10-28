#!/usr/bin/env python3
"""Generate an RSA key pair and save it as PEM files.

Creates two files in the output directory:
    <name>_private.pem  -> private key (PKCS#8)
    <name>_public.pem   -> public key (SubjectPublicKeyInfo)

Requires the 'cryptography' package:  pip install cryptography
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import project_settings


def ask_passphrase():
    passphrase = getpass.getpass("Passphrase para la llave privada (vacio = sin cifrar): ")
    if not passphrase:
        print("[!] La llave privada quedara sin cifrar. Protege el archivo.")
        return serialization.NoEncryption()
    if getpass.getpass("Repite la passphrase: ") != passphrase:
        sys.exit("[x] Las passphrases no coinciden")
    return serialization.BestAvailableEncryption(passphrase.encode("utf-8"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera un par de llaves RSA en formato PEM.")
    parser.add_argument("--name", default="rsa", help="prefijo de los archivos (default: rsa)")
    parser.add_argument("--bits", type=int, default=project_settings.RSA_KEY_BITS, choices=[2048, 3072, 4096],
                        help="tamano de la llave en bits (default: 2048)")
    parser.add_argument("--out", default=project_settings.KEYS_DIR,
                        help="directorio de salida (default: KEYS_DIR o keys)")
    parser.add_argument("--force", action="store_true", help="sobrescribir si ya existen")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / f"{args.name}_private.pem"
    public_path = out_dir / f"{args.name}_public.pem"

    if not args.force:
        for path in (private_path, public_path):
            if path.exists():
                sys.exit(f"[x] Ya existe {path}. Usa --force para sobrescribir.")

    encryption = ask_passphrase()

    print(f"Generando llave RSA de {args.bits} bits...")
    key = rsa.generate_private_key(public_exponent=65537, key_size=args.bits)

    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    if os.name == "posix":
        os.chmod(private_path, 0o600)

    print(f"[+] Llave privada: {private_path}")
    print(f"[+] Llave publica: {public_path}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[x] Cancelado")
