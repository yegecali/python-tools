import builtins
import json
import sys
from pathlib import Path

import pytest

import windows_env_setup as wes

JAVA_ENTRY = "%JAVA_HOME%\\bin"
MAVEN_ENTRY = "%MAVEN_HOME%\\bin"


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """Point Path.home() at a temporary folder, so ~/.m2 is never touched."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


# --- PATH logic -------------------------------------------------------------

def test_java_entry_goes_first_and_old_jdk_is_removed():
    current = r"C:\Windows\system32;C:\Program Files\Java\jdk-17\bin;C:\Tools"
    new, removed = wes.build_path(current, "java")

    assert new.split(";")[0] == JAVA_ENTRY
    assert removed == [r"C:\Program Files\Java\jdk-17\bin"]
    assert r"C:\Tools" in new.split(";")


def test_oracle_javapath_shim_is_kept():
    current = r"C:\Program Files\Common Files\Oracle\Java\javapath;C:\Windows"
    new, removed = wes.build_path(current, "java")
    assert removed == []
    assert r"C:\Program Files\Common Files\Oracle\Java\javapath" in new.split(";")


def test_configuring_java_does_not_touch_maven_entries():
    current = r"C:\tools\apache-maven-3.8.1\bin;C:\Windows"
    new, removed = wes.build_path(current, "java")
    assert removed == []
    assert r"C:\tools\apache-maven-3.8.1\bin" in new.split(";")


def test_configuring_maven_removes_old_maven_only():
    current = f"{JAVA_ENTRY};C:\\tools\\apache-maven-3.8.1\\bin\\;C:\\Windows"
    new, removed = wes.build_path(current, "maven")
    assert removed == ["C:\\tools\\apache-maven-3.8.1\\bin\\"]
    assert new.split(";")[0] == MAVEN_ENTRY
    assert JAVA_ENTRY in new.split(";")


def test_build_path_is_idempotent():
    current = r"C:\Windows;C:\Program Files\Java\jdk-21\bin"
    once, _ = wes.build_path(current, "java")
    twice, removed = wes.build_path(once, "java")
    assert twice == once
    assert removed == []


def test_build_path_from_empty_path():
    assert wes.build_path("", "java") == (JAVA_ENTRY, [])


# --- configuration files ----------------------------------------------------

def test_load_config_accepts_bom(tmp_path):
    cfg = tmp_path / "java.json"
    cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"versions": {"21": "C:\\jdk"}}).encode())
    assert wes.load_config(cfg)["versions"] == {"21": "C:\\jdk"}


def test_load_config_rejects_invalid_json(tmp_path):
    cfg = tmp_path / "java.json"
    cfg.write_text("{no es json", encoding="utf-8")
    with pytest.raises(SystemExit, match="no es JSON valido"):
        wes.load_config(cfg)


def test_load_config_requires_versions(tmp_path):
    cfg = tmp_path / "maven.json"
    cfg.write_text(json.dumps({"versions": {}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="versions"):
        wes.load_config(cfg)


def test_validate_home_checks_executable(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "java.exe").write_text("x")
    assert wes.validate_home(str(tmp_path), "java.exe") == str(tmp_path)
    with pytest.raises(SystemExit, match="mvn.cmd"):
        wes.validate_home(str(tmp_path), "mvn.cmd")


# --- settings profiles ------------------------------------------------------

def make_profiles(tmp_path):
    empresa = tmp_path / "settings-empresa.xml"
    cliente = tmp_path / "settings-cliente.xml"
    empresa.write_text("<settings>EMPRESA</settings>")
    cliente.write_text("<settings>CLIENTE</settings>")
    return empresa, cliente


def test_legacy_settings_key_becomes_default_profile(tmp_path):
    _, cliente = make_profiles(tmp_path)
    assert wes.settings_profiles({"settings": str(cliente)}) == {"default": str(cliente)}


def test_missing_profile_file_exits(tmp_path):
    with pytest.raises(SystemExit, match="no existe"):
        wes.settings_profiles({"settings_profiles": {"x": str(tmp_path / "nope.xml")}})


def test_active_profile_is_detected_by_content(tmp_path, fake_home):
    empresa, cliente = make_profiles(tmp_path)
    profiles = {"empresa": str(empresa), "cliente": str(cliente)}
    assert wes.active_settings_profile(profiles) is None

    (fake_home / ".m2").mkdir()
    (fake_home / ".m2" / "settings.xml").write_bytes(cliente.read_bytes())
    assert wes.active_settings_profile(profiles) == "cliente"


def test_switching_profiles_does_not_create_backup(tmp_path, fake_home):
    empresa, cliente = make_profiles(tmp_path)
    m2 = fake_home / ".m2"
    m2.mkdir()
    (m2 / "settings.xml").write_bytes(cliente.read_bytes())

    wes.apply_settings(empresa, [empresa, cliente])

    assert (m2 / "settings.xml").read_bytes() == empresa.read_bytes()
    assert list(m2.glob("*.bak")) == []


def test_manual_edits_are_backed_up_before_switching(tmp_path, fake_home):
    empresa, cliente = make_profiles(tmp_path)
    m2 = fake_home / ".m2"
    m2.mkdir()
    (m2 / "settings.xml").write_text("<settings>EDICION MANUAL</settings>")

    wes.apply_settings(cliente, [empresa, cliente])

    backups = list(m2.glob("settings.xml.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "<settings>EDICION MANUAL</settings>"
    assert (m2 / "settings.xml").read_bytes() == cliente.read_bytes()


def test_choose_settings_returns_selected_profile_or_none(tmp_path, fake_home, monkeypatch):
    empresa, cliente = make_profiles(tmp_path)
    config = {"settings_profiles": {"empresa": str(empresa), "cliente": str(cliente)}}

    answers = iter(["2"])
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    source, files = wes.choose_settings(config)
    assert source == cliente
    assert set(files) == {empresa, cliente}

    answers = iter(["3"])  # "(no cambiar)" is the last option
    monkeypatch.setattr(builtins, "input", lambda prompt="": next(answers))
    source, _ = wes.choose_settings(config)
    assert source is None


# --- Windows registry (fake winreg, so the logic runs on any system) --------

class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_EXPAND_SZ = 2

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path, reserved, access):
        fake = self

        class Key:
            def __enter__(self):
                return fake

            def __exit__(self, *exc):
                return False

        return Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = (value, kind)


@pytest.fixture
def fake_registry(monkeypatch):
    registry = FakeWinreg()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    return registry


def test_write_then_read_user_environment_keeps_type(fake_registry):
    wes.write_user_env("Path", "%JAVA_HOME%\\bin;C:\\Windows", FakeWinreg.REG_EXPAND_SZ)
    assert wes.read_user_env("Path") == ("%JAVA_HOME%\\bin;C:\\Windows", FakeWinreg.REG_EXPAND_SZ)


def test_missing_user_variable_reads_as_empty(fake_registry):
    assert wes.read_user_env("JAVA_HOME") == ("", FakeWinreg.REG_EXPAND_SZ)


def test_main_refuses_to_run_outside_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(SystemExit, match="solo funciona en Windows"):
        wes.main()
