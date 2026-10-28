#!/usr/bin/env python3
"""Menu principal que orquesta las herramientas del proyecto.

    java_cacerts_installer.py  -> instala certificados de dominios en el cacerts de Java
    rsa_keygen.py              -> genera llaves RSA (publica y privada)
    rsa_crypt.py               -> encripta y desencripta valores con las llaves
    qr_generator.py            -> genera un QR a partir de un texto corto
    text_qr.py                 -> convierte un .txt en uno o varios QR, y los restaura
    windows_env_setup.py       -> configura Java y Maven (y settings.xml) para el usuario de Windows

Uso:
    python3 main.py                              # menu interactivo (en Windows: py main.py)
    python3 main.py cacerts                      # instala certificados en cacerts
    python3 main.py keygen [opciones]            # genera llaves RSA
    python3 main.py encrypt [opciones]           # encripta un valor
    python3 main.py decrypt [opciones]           # desencripta un valor
    python3 main.py qr [opciones] TEXTO          # QR de un texto
    python3 main.py textqr generate [opciones] ARCHIVO.txt
    python3 main.py textqr restore [opciones] PARTES.txt
    python3 main.py env                          # configura Java y Maven (Windows)
    python3 main.py check                        # verifica la configuracion y las llaves

Requiere las dependencias de requirements.txt: pip install -r requirements.txt
"""

import sys
from dataclasses import dataclass
from typing import Callable

from errors import ToolError, run_cli
import audit
import doctor
import java_cacerts_installer
import project_settings
import ui
import windows_env_setup

try:
    import qr_generator
    import rsa_crypt
    import rsa_keygen
    import text_qr
except ImportError as error:
    raise SystemExit(f"{ui.icon('error')} Falta la dependencia '{error.name}'. Instala con: pip install -r requirements.txt")

DEFAULT_PUBLIC = str(project_settings.PUBLIC_KEY_FILE)
DEFAULT_PRIVATE = str(project_settings.PRIVATE_KEY_FILE)


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def flag(name, value):
    """Return [name, value] when the user gave a value, otherwise nothing."""
    return [name, value] if value else []


def run_step(func, *args):
    """Run a tool and keep the menu alive when it fails."""
    try:
        func(*args)
    except ToolError as error:
        print(f"{ui.icon('error')} {error}")
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code)
        elif error.code:
            print(f"{ui.icon('error')} El paso termino con errores")


# Interactive actions: ask the questions of the menu and run the tool.

def action_cacerts():
    run_step(java_cacerts_installer.main)


def action_keygen():
    name = ask("Prefijo de los archivos", "rsa")
    bits = ask("Tamano en bits (2048, 3072, 4096)", "2048")
    out = ask("Directorio de salida", str(project_settings.KEYS_DIR))
    argv = ["--name", name, "--bits", bits, "--out", out]
    if ask("Sobrescribir si ya existen? (s/N)", "n").lower() == "s":
        argv.append("--force")
    run_step(rsa_keygen.main, argv)


def action_encrypt():
    pubkey = ask("Llave publica", DEFAULT_PUBLIC)
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    run_step(rsa_crypt.main, ["encrypt", "--pubkey", pubkey, *flag("--out", out)])


def action_decrypt():
    privkey = ask("Llave privada", DEFAULT_PRIVATE)
    source = ask("Archivo JSON encriptado")
    if not source:
        print(f"{ui.icon('error')} Indica el archivo JSON encriptado")
        return
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    run_step(rsa_crypt.main, ["decrypt", "--privkey", privkey, "--in", source, *flag("--out", out)])


def action_qr():
    text = ask("Texto para el QR")
    if not text:
        print(f"{ui.icon('error')} El texto esta vacio")
        return
    out = ask("Archivo de salida .png o .svg (vacio = mostrar en pantalla)")
    # '--' evita que un texto que empieza con '-' se lea como opcion
    run_step(qr_generator.main, [*flag("--out", out), "--", text])


def action_text_generate():
    source = ask("Archivo .txt de origen")
    if not source:
        print(f"{ui.icon('error')} Indica el archivo .txt")
        return
    out_dir = ask("Carpeta para guardar los PNG (vacio = mostrar en pantalla)")
    argv = ["generate", source, *flag("--out-dir", out_dir)]
    if ask("Encriptar con la llave publica? (s/N)", "n").lower() == "s":
        argv += ["--encrypt", "--pubkey", ask("Llave publica", DEFAULT_PUBLIC)]
    run_step(text_qr.main, argv)


def action_text_restore():
    parts = ask("Archivo .txt con una parte de QR por linea")
    if not parts:
        print(f"{ui.icon('error')} Indica el archivo con las partes")
        return
    privkey = ask("Llave privada (solo si el mensaje esta encriptado)", DEFAULT_PRIVATE)
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    run_step(text_qr.main, ["restore", parts, "--privkey", privkey, *flag("--out", out)])


def action_windows_env():
    run_step(windows_env_setup.main)


def action_check():
    checks = doctor.run_checks()
    for check in checks:
        print(f"  {ui.icon('ok' if check.ok else 'error')} {check.name}: {check.detail}")
    passed = sum(check.ok for check in checks)
    print(f"\n{passed} de {len(checks)} comprobaciones correctas")
    audit.record("check", "ok" if passed == len(checks) else "error", passed=passed, total=len(checks))


def windows_label():
    label = "Configurar Java y Maven (usuario de Windows)"
    if sys.platform != "win32":
        label += " - solo disponible en Windows"
    return label


@dataclass(frozen=True)
class Tool:
    label: str
    icon: str
    action: Callable[[], None]


# The menu, in the order the user sees it.
MENU = [
    Tool("Instalar certificados en cacerts de Java", "tool_cacerts", action_cacerts),
    Tool("Generar llaves RSA", "tool_keygen", action_keygen),
    Tool("Encriptar un valor", "tool_encrypt", action_encrypt),
    Tool("Desencriptar un valor", "tool_decrypt", action_decrypt),
    Tool("QR de un texto corto", "tool_qr", action_qr),
    Tool("Convertir un .txt en QR", "tool_text_generate", action_text_generate),
    Tool("Restaurar texto desde las partes de QR", "tool_text_restore", action_text_restore),
    Tool(windows_label(), "tool_windows", action_windows_env),
    Tool("Verificar configuracion", "tool_check", action_check),
]

# Command-line names. Lookups happen at call time so the modules can be replaced in tests.
CLI_COMMANDS = {
    "cacerts": lambda argv: java_cacerts_installer.main(),
    "keygen": lambda argv: rsa_keygen.main(argv),
    "encrypt": lambda argv: rsa_crypt.main(["encrypt", *argv]),
    "decrypt": lambda argv: rsa_crypt.main(["decrypt", *argv]),
    "qr": lambda argv: qr_generator.main(argv),
    "textqr": lambda argv: text_qr.main(argv),
    "env": lambda argv: windows_env_setup.main(),
    "check": lambda argv: action_check(),
}


def menu():
    print(f"\n{ui.icon('banner')} Caja de herramientas de Python")
    while True:
        print(f"\n{ui.icon('title')} Herramientas")
        for number, tool in enumerate(MENU, 1):
            print(f"  {number}) {ui.icon(tool.icon)} {tool.label}")
        print(f"  0) {ui.icon('exit')} Salir")

        choice = input(f"{ui.icon('prompt')} Opcion: ").strip()
        if choice == "0":
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            print(f"{ui.icon('warn')} Opcion no valida")
            continue
        try:
            MENU[int(choice) - 1].action()
        except ToolError as error:
            print(f"{ui.icon('error')} {error}")
        except KeyboardInterrupt:
            print(f"\n{ui.icon('error')} Operacion cancelada, volviendo al menu")


def dispatch(argv):
    command, rest = argv[0], argv[1:]
    if command not in CLI_COMMANDS:
        raise ToolError(
            f"Comando desconocido: {command}\n"
            f"Uso: python3 main.py [{'|'.join(CLI_COMMANDS)}]"
        )
    run_step(CLI_COMMANDS[command], rest)


if __name__ == "__main__":
    # Never crash on characters the console cannot encode (e.g. emoji in redirected output)
    sys.stdout.reconfigure(errors="replace")
    run_cli(lambda: dispatch(sys.argv[1:]) if len(sys.argv) > 1 else menu())
