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

Requiere las dependencias de requirements.txt: pip install -r requirements.txt
"""

import sys

import java_cacerts_installer
import project_settings
import windows_env_setup

try:
    import qr_generator
    import rsa_crypt
    import rsa_keygen
    import text_qr
except ImportError as error:
    raise SystemExit(f"[x] Falta la dependencia '{error.name}'. Instala con: pip install -r requirements.txt")

DEFAULT_PUBLIC = str(project_settings.get_path("PUBLIC_KEY_FILE", "keys/public-key.pem"))
DEFAULT_PRIVATE = str(project_settings.get_path("PRIVATE_KEY_FILE", "keys/private-key.pem"))


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def run_step(func, *args):
    """Run a tool and keep the menu alive when it exits with an error."""
    try:
        func(*args)
    except SystemExit as error:
        if isinstance(error.code, str):
            print(error.code)
        elif error.code:
            print("[x] El paso termino con errores")


def action_cacerts():
    run_step(java_cacerts_installer.main)


def action_keygen():
    name = ask("Prefijo de los archivos", "rsa")
    bits = ask("Tamano en bits (2048, 3072, 4096)", "2048")
    out = ask("Directorio de salida", str(project_settings.get_path("KEYS_DIR", "keys")))
    argv = ["--name", name, "--bits", bits, "--out", out]
    if ask("Sobrescribir si ya existen? (s/N)", "n").lower() == "s":
        argv.append("--force")
    run_step(rsa_keygen.main, argv)


def action_encrypt():
    pubkey = ask("Llave publica", DEFAULT_PUBLIC)
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    argv = ["encrypt", "--pubkey", pubkey]
    if out:
        argv += ["--out", out]
    run_step(rsa_crypt.main, argv)


def action_decrypt():
    privkey = ask("Llave privada", DEFAULT_PRIVATE)
    source = ask("Archivo JSON encriptado")
    if not source:
        print("[x] Indica el archivo JSON encriptado")
        return
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    argv = ["decrypt", "--privkey", privkey, "--in", source]
    if out:
        argv += ["--out", out]
    run_step(rsa_crypt.main, argv)


def action_qr():
    text = ask("Texto para el QR")
    if not text:
        print("[x] El texto esta vacio")
        return
    out = ask("Archivo de salida .png o .svg (vacio = mostrar en pantalla)")
    argv = ["--out", out] if out else []
    # '--' evita que un texto que empieza con '-' se lea como opcion
    run_step(qr_generator.main, [*argv, "--", text])


def action_text_generate():
    source = ask("Archivo .txt de origen")
    if not source:
        print("[x] Indica el archivo .txt")
        return
    out_dir = ask("Carpeta para guardar los PNG (vacio = mostrar en pantalla)")
    argv = ["generate", source]
    if out_dir:
        argv += ["--out-dir", out_dir]
    if ask("Encriptar con la llave publica? (s/N)", "n").lower() == "s":
        pubkey = ask("Llave publica", DEFAULT_PUBLIC)
        argv += ["--encrypt", "--pubkey", pubkey]
    run_step(text_qr.main, argv)


def action_text_restore():
    parts = ask("Archivo .txt con una parte de QR por linea")
    if not parts:
        print("[x] Indica el archivo con las partes")
        return
    privkey = ask("Llave privada (solo si el mensaje esta encriptado)", DEFAULT_PRIVATE)
    out = ask("Archivo de salida (vacio = mostrar en pantalla)")
    argv = ["restore", parts, "--privkey", privkey]
    if out:
        argv += ["--out", out]
    run_step(text_qr.main, argv)


def action_windows_env():
    run_step(windows_env_setup.main)


def windows_label():
    label = "Configurar Java y Maven (usuario de Windows)"
    if sys.platform != "win32":
        label += " - solo disponible en Windows"
    return label


MENU = [
    ("Instalar certificados en cacerts de Java", action_cacerts),
    ("Generar llaves RSA", action_keygen),
    ("Encriptar un valor", action_encrypt),
    ("Desencriptar un valor", action_decrypt),
    ("QR de un texto corto", action_qr),
    ("Convertir un .txt en QR", action_text_generate),
    ("Restaurar texto desde las partes de QR", action_text_restore),
    (windows_label(), action_windows_env),
]


def menu():
    while True:
        print("\n=== Herramientas ===")
        for number, (label, _) in enumerate(MENU, 1):
            print(f"  {number}) {label}")
        print("  0) Salir")

        choice = input("Opcion: ").strip()
        if choice == "0":
            return
        if not choice.isdigit() or not 1 <= int(choice) <= len(MENU):
            print("[!] Opcion no valida")
            continue
        try:
            MENU[int(choice) - 1][1]()
        except KeyboardInterrupt:
            print("\n[x] Operacion cancelada, volviendo al menu")


def dispatch(argv):
    command, rest = argv[0], argv[1:]
    if command == "cacerts":
        run_step(java_cacerts_installer.main)
    elif command == "keygen":
        run_step(rsa_keygen.main, rest)
    elif command in ("encrypt", "decrypt"):
        run_step(rsa_crypt.main, [command, *rest])
    elif command == "qr":
        run_step(qr_generator.main, rest)
    elif command == "textqr":
        run_step(text_qr.main, rest)
    elif command == "env":
        run_step(windows_env_setup.main)
    else:
        sys.exit(
            f"[x] Comando desconocido: {command}\n"
            "Uso: python3 main.py [cacerts|keygen|encrypt|decrypt|qr|textqr|env]"
        )


if __name__ == "__main__":
    # Never crash on characters the console cannot encode (e.g. emoji in redirected output)
    sys.stdout.reconfigure(errors="replace")
    try:
        if len(sys.argv) > 1:
            dispatch(sys.argv[1:])
        else:
            menu()
    except (KeyboardInterrupt, EOFError):
        sys.exit("\n[x] Cancelado")
