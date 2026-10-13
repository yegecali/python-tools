#!/usr/bin/env python3
"""Turn a .txt file into one or more QR codes, and restore them back.

generate: cleans the text (extra spaces, tabs and line breaks), compresses it, optionally
          encrypts it with RSA (hybrid, see rsa_crypt.py), splits it into parts and creates
          one QR per part.
restore:  takes the decoded content of the QR parts (one per line, e.g. copied from a phone
          scanner) and rebuilds the original text.

Each QR holds a single line:
    TQR1|<mode>|<message-id>|<index>/<total>|<data>
    mode: P = plain (zlib + base64), E = encrypted (zlib + RSA hybrid, JSON)

Examples:
    python3 text_qr.py generate text.example.txt --out-dir qr_out
    python3 text_qr.py generate text.example.txt --encrypt --pubkey keys/public-key.pem
    python3 text_qr.py restore parts.txt --privkey keys/private-key.pem
"""

import argparse
import base64
import hashlib
import json
import sys
import zlib
from pathlib import Path

from cryptography.exceptions import InvalidTag

import project_settings
import rsa_crypt
from qr_generator import build_qr, print_terminal, save_qr

HEADER = "TQR1"
DEFAULT_CHUNK = project_settings.get_int("QR_CHUNK_SIZE", 1200)
DEFAULT_PUBKEY = project_settings.get_path("PUBLIC_KEY_FILE", "keys/public-key.pem")
DEFAULT_PRIVKEY = project_settings.get_path("PRIVATE_KEY_FILE", "keys/private-key.pem")


def clean_text(raw, keep_newlines=False):
    """Collapse extra spaces and tabs. Unless keep_newlines, line breaks become spaces."""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not keep_newlines:
        return " ".join(text.split())
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out = []
    for line in lines:
        if line == "" and out and out[-1] == "":
            continue  # keep at most one blank line between paragraphs
        out.append(line)
    return "\n".join(out).strip()


def make_payload(text, pubkey_path=None):
    """Return (mode, ASCII payload). Encrypted payloads are JSON; plain ones are base64."""
    compressed = zlib.compress(text.encode("utf-8"), 9)
    if pubkey_path:
        public_key = rsa_crypt.load_public_key(pubkey_path)
        return "E", json.dumps(rsa_crypt.encrypt(public_key, compressed), separators=(",", ":"))
    return "P", base64.b64encode(compressed).decode("ascii")


def split_parts(mode, payload, chunk_size):
    message_id = hashlib.sha256(payload.encode("ascii")).hexdigest()[:12]
    chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)] or [""]
    total = len(chunks)
    return [
        f"{HEADER}|{mode}|{message_id}|{index}/{total}|{chunk}"
        for index, chunk in enumerate(chunks, 1)
    ]


def parse_part(line):
    fields = line.strip().split("|", 4)
    if len(fields) != 5 or fields[0] != HEADER:
        raise ValueError("la linea no es una parte TQR1")
    mode, message_id, position, data = fields[1], fields[2], fields[3], fields[4]
    index, total = (int(value) for value in position.split("/"))
    return mode, message_id, index, total, data


def restore(lines, privkey_path):
    messages = {}
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            mode, message_id, index, total, data = parse_part(line)
        except ValueError as error:
            sys.exit(f"[x] Linea {number}: {error}")
        message = messages.setdefault(message_id, {"mode": mode, "total": total, "parts": {}})
        if message["total"] != total or message["mode"] != mode:
            sys.exit(f"[x] Linea {number}: las partes no pertenecen al mismo mensaje")
        message["parts"][index] = data

    if not messages:
        sys.exit("[x] No encontre partes TQR1 en el archivo")
    if len(messages) > 1:
        sys.exit(f"[x] Hay partes de {len(messages)} mensajes distintos: {', '.join(messages)}")

    message_id, message = next(iter(messages.items()))
    missing = [i for i in range(1, message["total"] + 1) if i not in message["parts"]]
    if missing:
        sys.exit(f"[x] Faltan las partes: {', '.join(map(str, missing))} de {message['total']}")

    payload = "".join(message["parts"][i] for i in range(1, message["total"] + 1))
    if hashlib.sha256(payload.encode("ascii")).hexdigest()[:12] != message_id:
        sys.exit("[x] El contenido no coincide con el identificador: alguna parte esta mal copiada")

    if message["mode"] == "E":
        try:
            private_key = rsa_crypt.load_private_key(privkey_path)
            compressed = rsa_crypt.decrypt(private_key, json.loads(payload))
        except FileNotFoundError:
            sys.exit(f"[x] No existe la llave privada: {privkey_path}")
        except (ValueError, KeyError, InvalidTag) as error:
            raise SystemExit("[x] No se pudo desencriptar: llave incorrecta o datos alterados") from error
    else:
        compressed = base64.b64decode(payload)
    return zlib.decompress(compressed).decode("utf-8")


def cmd_generate(args):
    source = Path(args.file)
    if not source.is_file():
        sys.exit(f"[x] No existe el archivo: {source}")

    raw = source.read_text(encoding="utf-8-sig")
    text = clean_text(raw, args.keep_newlines)
    if not text:
        sys.exit("[x] El archivo no tiene texto despues de limpiarlo")

    pubkey = None
    if args.encrypt:
        pubkey = Path(args.pubkey)
        if not pubkey.is_file():
            sys.exit(f"[x] No existe la llave publica: {pubkey}")

    try:
        mode, payload = make_payload(text, pubkey)
    except ValueError as error:
        sys.exit(f"[x] No se pudo leer la llave publica: {error}")

    parts = split_parts(mode, payload, args.chunk)
    print(f"Caracteres: {len(raw)} originales -> {len(text)} limpios")
    print(f"Modo: {'encriptado (RSA + AES)' if mode == 'E' else 'texto plano comprimido'}")
    print(f"Partes: {len(parts)}")

    try:
        qrs = [build_qr(part, args.ec, args.box) for part in parts]
    except ValueError:
        sys.exit("[x] Una parte no cabe en un QR. Usa un --chunk mas pequeno")

    total = len(qrs)
    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, qr in enumerate(qrs, 1):
            path = out_dir / f"parte_{index:02d}_de_{total:02d}.png"
            save_qr(qr, path)
            print(f"[+] {path}")
        return

    for index, qr in enumerate(qrs, 1):
        print(f"\n--- Parte {index} de {total} ---")
        print_terminal(qr)
        if index < total and sys.stdin.isatty():
            input("Enter para la siguiente parte...")


def cmd_restore(args):
    lines = Path(args.file).read_text(encoding="utf-8-sig").splitlines()
    text = restore(lines, Path(args.privkey))
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[+] Texto restaurado en: {args.out}")
    else:
        print(text)


def build_parser():
    parser = argparse.ArgumentParser(description="Convierte un .txt en codigos QR y los restaura.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen = subparsers.add_parser("generate", help="crear los QR a partir de un .txt")
    gen.add_argument("file", help="archivo .txt de origen")
    gen.add_argument("--out-dir", help="guardar cada parte como PNG en esta carpeta; sin esto se muestran en terminal")
    gen.add_argument("--chunk", type=int, default=DEFAULT_CHUNK,
                     help=f"caracteres por parte (default: {DEFAULT_CHUNK})")
    gen.add_argument("--ec", default=project_settings.get_choice("QR_ERROR_CORRECTION", "M", ["L", "M", "Q", "H"]),
                     choices=["L", "M", "Q", "H"], help="correccion de errores (default: QR_ERROR_CORRECTION o M)")
    gen.add_argument("--box", type=int, default=project_settings.get_int("QR_BOX_SIZE", 10),
                     help="tamano de cada modulo en pixeles para PNG (default: QR_BOX_SIZE o 10)")
    gen.add_argument("--keep-newlines", action="store_true", help="conservar los saltos de parrafo")
    gen.add_argument("--encrypt", action="store_true", help="encriptar con la llave publica")
    gen.add_argument("--pubkey", default=str(DEFAULT_PUBKEY), help="llave publica PEM (default: keys/public-key.pem)")
    gen.set_defaults(func=cmd_generate)

    res = subparsers.add_parser("restore", help="reconstruir el texto desde el contenido de las partes")
    res.add_argument("file", help="archivo .txt con una parte TQR1 por linea")
    res.add_argument("--privkey", default=str(DEFAULT_PRIVKEY),
                     help="llave privada PEM, solo si el mensaje esta encriptado (default: keys/private-key.pem)")
    res.add_argument("--out", help="guardar el texto restaurado en un archivo")
    res.set_defaults(func=cmd_restore)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    # Never crash on characters the console cannot encode (e.g. emoji in redirected output)
    sys.stdout.reconfigure(errors="replace")
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[x] Cancelado")
