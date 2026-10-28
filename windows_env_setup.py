#!/usr/bin/env python3
"""Configure Java and Maven for the current Windows user (not the system).

Writes to HKEY_CURRENT_USER\\Environment:
    JAVA_HOME, MAVEN_HOME, M2_HOME  and  PATH (adds %JAVA_HOME%\\bin and %MAVEN_HOME%\\bin)

Maven settings.xml is copied to %USERPROFILE%\\.m2\\settings.xml (backup of the previous one).

Versions are read from config/java.json and config/maven.json.
Run from a regular (non-admin) terminal:  py windows_env_setup.py
"""

import ctypes
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

import project_settings

JAVA_CONFIG = project_settings.JAVA_CONFIG_FILE
MAVEN_CONFIG = project_settings.MAVEN_CONFIG_FILE

JAVA_ENTRY = "%JAVA_HOME%\\bin"
MAVEN_ENTRY = "%MAVEN_HOME%\\bin"

# Install folders of other JDKs/Maven versions that would shadow the new ones on PATH.
# Only folders ending in \bin are matched, so shims such as ...\javapath are left alone.
JAVA_STALE = re.compile(r"[\\/](jdk|jre)[^\\/]*[\\/]bin[\\/]?$", re.IGNORECASE)
MAVEN_STALE = re.compile(r"[\\/](apache-)?maven[^\\/]*[\\/]bin[\\/]?$", re.IGNORECASE)


def load_config(path):
    if not path.exists():
        sys.exit(f"[x] No existe {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        sys.exit(f"[x] {path.name} no es JSON valido: {error}")
    versions = data.get("versions")
    if not isinstance(versions, dict) or not versions:
        sys.exit(f"[x] {path.name}: 'versions' debe ser un objeto con al menos una entrada")
    return data


def ask_choice(title, options):
    print(f"\n{title}")
    keys = list(options)
    for number, key in enumerate(keys, 1):
        print(f"  {number}) {key}: {options[key]}")
    while True:
        answer = input("Elige un numero: ").strip()
        if answer.isdigit() and 1 <= int(answer) <= len(keys):
            return keys[int(answer) - 1]
        print("[!] Opcion no valida")


def ask_yes(prompt):
    return input(f"{prompt} (s/N): ").strip().lower() == "s"


def choose_targets():
    print("Que deseas configurar?")
    print("  1) Java")
    print("  2) Maven")
    print("  3) Ambos")
    while True:
        answer = input("Opcion: ").strip()
        if answer in ("1", "2", "3"):
            return {"1": {"java"}, "2": {"maven"}, "3": {"java", "maven"}}[answer]
        print("[!] Opcion no valida")


def validate_home(path, executable):
    home = Path(path)
    if not (home / "bin" / executable).is_file():
        sys.exit(f"[x] No encuentro bin\\{executable} en: {home}")
    return str(home)


def build_path(current, tool):
    """Return (new PATH, removed entries) with this tool's bin entry first."""
    entry, stale_pattern = (JAVA_ENTRY, JAVA_STALE) if tool == "java" else (MAVEN_ENTRY, MAVEN_STALE)
    parts = [part for part in current.split(";") if part.strip()]
    removed = [part for part in parts if part != entry and stale_pattern.search(part)]
    kept = [part for part in parts if part != entry and part not in removed]
    return ";".join([entry, *kept]), removed


def read_user_env(name):
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ) as key:
        try:
            value, kind = winreg.QueryValueEx(key, name)
            return value, kind
        except FileNotFoundError:
            return "", winreg.REG_EXPAND_SZ


def write_user_env(name, value, kind):
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, kind, value)


def notify_environment_change():
    """Tell running programs (Explorer, new terminals) that the environment changed."""
    hwnd_broadcast, wm_settingchange, smto_abortifhung = 0xFFFF, 0x001A, 0x0002
    result = ctypes.c_size_t()
    ctypes.windll.user32.SendMessageTimeoutW(
        hwnd_broadcast, wm_settingchange, 0, "Environment", smto_abortifhung, 5000, ctypes.byref(result)
    )


def settings_profiles(config):
    """Map profile name -> settings.xml path. 'settings' is kept as a profile named 'default'."""
    profiles = dict(config.get("settings_profiles") or {})
    if config.get("settings") and "default" not in profiles:
        profiles["default"] = config["settings"]
    for name, path in profiles.items():
        if not Path(path).is_file():
            sys.exit(f"[x] Perfil de settings '{name}': no existe {path}")
    return profiles


def active_settings_profile(profiles):
    """Name of the profile whose file matches ~/.m2/settings.xml byte for byte, or None."""
    dest = Path.home() / ".m2" / "settings.xml"
    if not dest.is_file():
        return None
    current = dest.read_bytes()
    for name, path in profiles.items():
        if Path(path).read_bytes() == current:
            return name
    return None


def choose_settings(config):
    """Ask which settings profile to activate. Returns (source or None, all profile files)."""
    profiles = settings_profiles(config)
    if not profiles:
        return None, []
    active = active_settings_profile(profiles)
    print("\nSettings de Maven:")
    print(f"  Perfil activo ahora: {active or 'ninguno (settings.xml personalizado o inexistente)'}")
    options = dict(profiles)
    options["(no cambiar)"] = "mantener el settings.xml actual"
    chosen = ask_choice("Que perfil de settings.xml usar?", options)
    profile_files = [Path(path) for path in profiles.values()]
    if chosen == "(no cambiar)":
        return None, profile_files
    return Path(profiles[chosen]), profile_files


def apply_settings(source, profile_files):
    m2 = Path.home() / ".m2"
    m2.mkdir(exist_ok=True)
    dest = m2 / "settings.xml"
    if dest.exists():
        current = dest.read_bytes()
        is_known = any(path.read_bytes() == current for path in profile_files if path.is_file())
        # Keep edits made directly in ~/.m2/settings.xml that are not saved in any profile
        if not is_known:
            stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            backup = m2 / f"settings.xml.{stamp}.bak"
            shutil.copy2(dest, backup)
            print(f"  Cambios no guardados en ningun perfil respaldados en: {backup}")
    shutil.copy2(source, dest)
    print(f"  settings.xml activo: {source} -> {dest}")


def main():
    if sys.platform != "win32":
        sys.exit("[x] Este script solo funciona en Windows")

    targets = choose_targets()
    java_home = maven_home = settings = None
    settings_files = []

    if "java" in targets:
        config = load_config(JAVA_CONFIG)
        name = ask_choice("Versiones de Java disponibles:", config["versions"])
        java_home = validate_home(config["versions"][name], "java.exe")
        print(f"  Java seleccionado: {name}")

    if "maven" in targets:
        config = load_config(MAVEN_CONFIG)
        name = ask_choice("Versiones de Maven disponibles:", config["versions"])
        maven_home = validate_home(config["versions"][name], "mvn.cmd")
        print(f"  Maven seleccionado: {name}")
        settings, settings_files = choose_settings(config)

    current_path, _ = read_user_env("Path")
    new_path = current_path
    removed_all = []
    if java_home:
        new_path, removed = build_path(new_path, "java")
        removed_all += removed
    if maven_home:
        new_path, removed = build_path(new_path, "maven")
        removed_all += removed

    print("\nCambios que se aplicaran (solo usuario actual, HKCU):")
    if java_home:
        print(f"  JAVA_HOME = {java_home}")
    if maven_home:
        print(f"  MAVEN_HOME = {maven_home}")
        print(f"  M2_HOME = {maven_home}")
    if removed_all:
        print("  PATH - se quitan entradas de otras versiones:")
        for entry in removed_all:
            print(f"      - {entry}")
    prepended = [entry for entry, chosen in ((JAVA_ENTRY, java_home), (MAVEN_ENTRY, maven_home)) if chosen]
    print("  PATH - se anteponen:", ", ".join(prepended))
    if settings:
        print(f"  settings.xml <- {settings}")

    if not ask_yes("\nAplicar cambios?"):
        sys.exit("Cancelado, no se modifico nada")

    import winreg

    if java_home:
        write_user_env("JAVA_HOME", java_home, winreg.REG_SZ)
    if maven_home:
        write_user_env("MAVEN_HOME", maven_home, winreg.REG_SZ)
        write_user_env("M2_HOME", maven_home, winreg.REG_SZ)
    _, path_kind = read_user_env("Path")
    write_user_env("Path", new_path, path_kind)
    if settings:
        apply_settings(settings, settings_files)

    notify_environment_change()
    print("\n[+] Variables de usuario actualizadas.")
    print("    Abre una terminal nueva y verifica:")
    if java_home:
        print("      java -version")
    if maven_home:
        print("      mvn -v")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\n[x] Cancelado")
