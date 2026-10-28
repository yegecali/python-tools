#!/usr/bin/env python3
"""Generate a QR code from a text.

Without --out the QR is printed in the terminal. With --out the file format is
chosen by its extension: .png (needs Pillow) or .svg.

Examples:
    python3 qr_generator.py "https://intranet.empresa.com"
    python3 qr_generator.py "Wi-Fi password" --out wifi.png
    python3 qr_generator.py --out link.svg          # asks for the text

Requires the 'qrcode' package (and 'pillow' for PNG): pip install -r requirements.txt
"""

import argparse
import sys
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from qrcode.exceptions import DataOverflowError

from errors import ToolError, run_cli
import ui
import project_settings

EC_LEVELS = {
    "L": ERROR_CORRECT_L,  # ~7% recovery
    "M": ERROR_CORRECT_M,  # ~15%
    "Q": ERROR_CORRECT_Q,  # ~25%
    "H": ERROR_CORRECT_H,  # ~30%
}


def build_qr(text, error_correction, box_size):
    qr = qrcode.QRCode(
        error_correction=EC_LEVELS[error_correction],
        box_size=box_size,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    return qr


def save_qr(qr, out):
    suffix = out.suffix.lower()
    if suffix == ".png":
        image = qr.make_image(fill_color="black", back_color="white")
    elif suffix == ".svg":
        from qrcode.image.svg import SvgPathImage

        image = qr.make_image(image_factory=SvgPathImage)
    else:
        raise ToolError("Formato no soportado. Usa una extension .png o .svg")
    image.save(str(out))


def print_terminal(qr):
    """Draw the QR in the terminal, with dark modules as blank cells (readable on dark terminals).

    Falls back to ASCII ('##' for the light cells) when the console cannot show blocks.
    """
    try:
        "██".encode(sys.stdout.encoding or "ascii")
        dark, light = "  ", "██"
    except (UnicodeEncodeError, LookupError):
        dark, light = "  ", "##"
    for row in qr.get_matrix():
        print("".join(dark if cell else light for cell in row))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera un codigo QR a partir de un texto.")
    parser.add_argument("text", nargs="?", help="texto a codificar; si se omite se pide por consola")
    parser.add_argument("--out", type=Path, help="archivo de salida (.png o .svg); sin esto se muestra en pantalla")
    parser.add_argument("--ec", default=project_settings.QR_ERROR_CORRECTION,
                        choices=list(EC_LEVELS),
                        help="nivel de correccion de errores (default: M)")
    parser.add_argument("--box", type=int, default=project_settings.QR_BOX_SIZE,
                        help="tamano de cada modulo en pixeles (default: QR_BOX_SIZE o 10)")
    args = parser.parse_args(argv)

    text = args.text if args.text is not None else input("Texto para el QR: ")
    if not text:
        raise ToolError("El texto esta vacio")

    try:
        qr = build_qr(text, args.ec, args.box)
    except (DataOverflowError, ValueError):
        # qrcode raises ValueError when no QR version can hold the data
        raise ToolError("El texto es demasiado largo para un codigo QR")

    if args.out:
        save_qr(qr, args.out)
        print(f"{ui.icon('ok')} QR guardado en: {args.out}")
    else:
        print_terminal(qr)


if __name__ == "__main__":
    # Never crash on characters the console cannot encode (e.g. emoji in redirected output)
    sys.stdout.reconfigure(errors="replace")
    run_cli(main)
