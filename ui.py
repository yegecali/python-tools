"""Iconos para la terminal.

Usa emoji cuando la consola puede mostrarlos (Windows Terminal, VS Code, macOS, Linux).
Si no, usa un texto simple para que nunca salgan signos de interrogacion.
"""

import sys

# name -> (emoji, texto simple)
ICONS = {
    "banner": ("🧰", "*"),
    "title": ("📋", "#"),
    "prompt": ("👉", ">"),
    "ok": ("✅", "[+]"),
    "error": ("❌", "[x]"),
    "warn": ("⚠️", "[!]"),
    "exit": ("👋", "*"),
    "tool_cacerts": ("🛡️", "[CA]"),
    "tool_keygen": ("🔑", "[KEY]"),
    "tool_encrypt": ("🔒", "[ENC]"),
    "tool_decrypt": ("🔓", "[DEC]"),
    "tool_qr": ("📱", "[QR]"),
    "tool_text_generate": ("📄", "[TXT]"),
    "tool_text_restore": ("🧩", "[REST]"),
    "tool_windows": ("💻", "[WIN]"),
    "tool_check": ("🩺", "[CHK]"),
}


def _can_print(text):
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def icon(name):
    emoji, plain = ICONS[name]
    return emoji if _can_print(emoji) else plain
