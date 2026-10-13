#!/usr/bin/env python3
"""Encrypt and decrypt values with an RSA key pair (hybrid scheme).

RSA alone can only encrypt about 190 bytes with a 2048-bit key, so each value is
encrypted with a random AES-256-GCM key, and that AES key is wrapped with RSA-OAEP
(SHA-256) using the public key. Decryption unwraps the AES key with the private key.

Requires the 'cryptography' package:  pip install cryptography

Examples:
    python3 rsa_crypt.py encrypt --pubkey keys/rsa_public.pem
    python3 rsa_crypt.py encrypt --pubkey keys/rsa_public.pem --out secret.json
    python3 rsa_crypt.py decrypt --privkey keys/rsa_private.pem --in secret.json
"""

import argparse
import base64
import getpass
import json
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT_VERSION = 1
OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)


def b64encode(data):
    return base64.b64encode(data).decode("ascii")


def b64decode(text):
    return base64.b64decode(text)


def encrypt(public_key, plaintext):
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    wrapped_key = public_key.encrypt(aes_key, OAEP)
    return {
        "v": FORMAT_VERSION,
        "key": b64encode(wrapped_key),
        "nonce": b64encode(nonce),
        "data": b64encode(ciphertext),
    }


def decrypt(private_key, payload):
    if payload.get("v") != FORMAT_VERSION:
        raise ValueError(f"version de formato no soportada: {payload.get('v')}")
    aes_key = private_key.decrypt(b64decode(payload["key"]), OAEP)
    return AESGCM(aes_key).decrypt(b64decode(payload["nonce"]), b64decode(payload["data"]), None)


def load_public_key(path):
    return serialization.load_pem_public_key(Path(path).read_bytes())


def load_private_key(path):
    pem = Path(path).read_bytes()
    try:
        return serialization.load_pem_private_key(pem, password=None)
    except TypeError:
        # The private key is protected by a passphrase
        passphrase = getpass.getpass("Passphrase de la llave privada: ").encode("utf-8")
        return serialization.load_pem_private_key(pem, password=passphrase)


def cmd_encrypt(args):
    public_key = load_public_key(args.pubkey)
    value = args.value if args.value is not None else getpass.getpass("Valor a encriptar: ")
    if not value:
        sys.exit("[x] El valor esta vacio")

    payload = json.dumps(encrypt(public_key, value.encode("utf-8")), indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(f"[+] Valor encriptado en: {args.out}")
    else:
        print(payload)


def cmd_decrypt(args):
    private_key = load_private_key(args.privkey)
    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    try:
        payload = json.loads(raw)
        plaintext = decrypt(private_key, payload)
    except (ValueError, KeyError, InvalidTag) as error:
        raise SystemExit("[x] No se pudo desencriptar: llave incorrecta o datos alterados") from error

    text = plaintext.decode("utf-8")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[+] Valor desencriptado en: {args.out}")
    else:
        print(text)


def build_parser():
    parser = argparse.ArgumentParser(description="Encripta y desencripta valores con RSA (esquema hibrido).")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enc = subparsers.add_parser("encrypt", help="encriptar un valor con la llave publica")
    enc.add_argument("--pubkey", required=True, help="archivo PEM de la llave publica")
    enc.add_argument("--value", help="valor a encriptar; si se omite se pide de forma oculta")
    enc.add_argument("--out", help="guardar el resultado en un archivo JSON")
    enc.set_defaults(func=cmd_encrypt)

    dec = subparsers.add_parser("decrypt", help="desencriptar con la llave privada")
    dec.add_argument("--privkey", required=True, help="archivo PEM de la llave privada")
    dec.add_argument("--in", dest="input", help="archivo JSON encriptado; si se omite se lee de stdin")
    dec.add_argument("--out", help="guardar el valor desencriptado en un archivo")
    dec.set_defaults(func=cmd_decrypt)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[x] Cancelado")
