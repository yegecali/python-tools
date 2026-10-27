import json
import subprocess
import sys

import pytest

import java_cacerts_installer as installer


def write_domains(path, data, bom=False):
    text = json.dumps(data)
    prefix = b"\xef\xbb\xbf" if bom else b""
    path.write_bytes(prefix + text.encode("utf-8"))
    return path


def test_load_hosts_accepts_domains_urls_and_ports(tmp_path):
    domains = write_domains(
        tmp_path / "domains.json",
        ["google.com", "https://repo.empresa.com:8443", "nexus.empresa.com:8443", "google.com"],
    )

    assert installer.load_hosts(domains) == [
        ("google.com", 443),
        ("repo.empresa.com", 8443),
        ("nexus.empresa.com", 8443),
    ]


def test_load_hosts_tolerates_utf8_bom_from_notepad(tmp_path):
    domains = write_domains(tmp_path / "domains.json", ["github.com"], bom=True)
    assert installer.load_hosts(domains) == [("github.com", 443)]


def test_load_hosts_rejects_non_list_and_non_strings(tmp_path):
    with pytest.raises(ValueError):
        installer.load_hosts(write_domains(tmp_path / "a.json", {"host": "x"}))
    with pytest.raises(ValueError):
        installer.load_hosts(write_domains(tmp_path / "b.json", ["ok.com", 123]))


def test_keytool_name_matches_platform():
    expected = "keytool.exe" if sys.platform == "win32" else "keytool"
    assert installer.KEYTOOL_NAME == expected


def make_java_home(root, nested=False):
    home = root / "Contents" / "Home" if nested else root
    (home / "bin").mkdir(parents=True)
    (home / "bin" / installer.KEYTOOL_NAME).write_text("fake")
    return home


def test_resolve_java_home_accepts_plain_home(tmp_path):
    home = make_java_home(tmp_path / "jdk-21")
    assert installer.resolve_java_home(str(home)) == home


def test_resolve_java_home_accepts_macos_bundle_root(tmp_path):
    bundle = tmp_path / "jdk-21.jdk"
    home = make_java_home(bundle, nested=True)
    assert installer.resolve_java_home(str(bundle)) == home


def test_resolve_java_home_strips_quotes_from_pasted_path(tmp_path):
    home = make_java_home(tmp_path / "jdk")
    assert installer.resolve_java_home(f'  "{home}"  ') == home


def test_resolve_java_home_returns_none_without_keytool(tmp_path):
    assert installer.resolve_java_home(str(tmp_path)) is None


def test_find_cacerts_supports_java_9_and_java_8_layouts(tmp_path):
    new_layout = tmp_path / "new"
    (new_layout / "lib" / "security").mkdir(parents=True)
    (new_layout / "lib" / "security" / "cacerts").write_text("x")
    assert installer.find_cacerts(new_layout) == new_layout / "lib" / "security" / "cacerts"

    old_layout = tmp_path / "old"
    (old_layout / "jre" / "lib" / "security").mkdir(parents=True)
    (old_layout / "jre" / "lib" / "security" / "cacerts").write_text("x")
    assert installer.find_cacerts(old_layout) == old_layout / "jre" / "lib" / "security" / "cacerts"

    assert installer.find_cacerts(tmp_path / "vacio") is None


def fake_java_home(root):
    home = make_java_home(root / "jdk")
    cacerts = home / "lib" / "security" / "cacerts"
    cacerts.parent.mkdir(parents=True)
    cacerts.write_bytes(b"cacerts-original")
    return home


def run_installer(monkeypatch, home, domains_file, downloads):
    """Run main() with the network and keytool replaced by fakes."""
    monkeypatch.setattr(installer, "DOMAINS_FILE", domains_file)
    monkeypatch.setattr(installer.getpass, "getpass", lambda prompt="": "changeit")
    monkeypatch.setattr("builtins.input", lambda prompt="": str(home))
    monkeypatch.setattr(installer, "fetch_pem", lambda host, port, timeout=10: downloads[host])
    monkeypatch.setattr(
        installer,
        "run_keytool",
        lambda java_home, *args: subprocess.CompletedProcess(args, 0, stdout="", stderr=""),
    )
    installer.main()


def test_redownload_overwrites_existing_crt_and_keeps_the_rest(tmp_path, monkeypatch):
    home = fake_java_home(tmp_path)
    domains = write_domains(tmp_path / "domains.json", ["google.com", "github.com"])
    certs = home / "certs"

    run_installer(monkeypatch, home, domains, {
        "google.com": "PEM-GOOGLE-V1\n",
        "github.com": "PEM-GITHUB-V1\n",
    })
    assert (certs / "google.com.crt").read_text() == "PEM-GOOGLE-V1\n"

    # A file that is not part of the current domain list must survive the run.
    (certs / "viejo.crt").write_text("PEM-VIEJO")

    run_installer(monkeypatch, home, domains, {
        "google.com": "PEM-GOOGLE-V2\n",
        "github.com": "PEM-GITHUB-V2\n",
    })

    assert (certs / "google.com.crt").read_text() == "PEM-GOOGLE-V2\n"
    assert (certs / "github.com.crt").read_text() == "PEM-GITHUB-V2\n"
    assert (certs / "viejo.crt").read_text() == "PEM-VIEJO"
    assert len(list(certs.glob("*.crt"))) == 3
    assert (home / "lib" / "security" / "cacerts.bak").exists()


def test_failed_download_keeps_previous_crt(tmp_path, monkeypatch):
    home = fake_java_home(tmp_path)
    domains = write_domains(tmp_path / "domains.json", ["google.com"])
    certs = home / "certs"
    certs.mkdir()
    (certs / "google.com.crt").write_text("PEM-PREVIO")

    def unreachable(host, port, timeout=10):
        raise OSError("sin conexion")

    monkeypatch.setattr(installer, "DOMAINS_FILE", domains)
    monkeypatch.setattr(installer.getpass, "getpass", lambda prompt="": "changeit")
    monkeypatch.setattr("builtins.input", lambda prompt="": str(home))
    monkeypatch.setattr(installer, "fetch_pem", unreachable)
    monkeypatch.setattr(
        installer, "run_keytool",
        lambda java_home, *args: subprocess.CompletedProcess(args, 0, stdout="", stderr=""),
    )

    with pytest.raises(SystemExit):
        installer.main()
    assert (certs / "google.com.crt").read_text() == "PEM-PREVIO"


def test_ask_java_home_offers_configured_versions(tmp_path, monkeypatch):
    config = tmp_path / "java.json"
    config.write_text(json.dumps({"versions": {"21": "C:\\jdk-21", "17": "C:\\jdk-17"}}), encoding="utf-8")
    monkeypatch.setattr(installer.windows_env_setup, "JAVA_CONFIG", config)
    monkeypatch.setattr("builtins.input", lambda prompt="": "2")

    assert installer.ask_java_home() == "C:\\jdk-17"


def test_ask_java_home_allows_typing_another_path(tmp_path, monkeypatch):
    config = tmp_path / "java.json"
    config.write_text(json.dumps({"versions": {"21": "C:\\jdk-21"}}), encoding="utf-8")
    monkeypatch.setattr(installer.windows_env_setup, "JAVA_CONFIG", config)
    answers = iter(["2", "D:\\otro-jdk"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    assert installer.ask_java_home() == "D:\\otro-jdk"


def test_ask_java_home_asks_path_when_nothing_is_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.windows_env_setup, "JAVA_CONFIG", tmp_path / "missing.json")
    monkeypatch.setattr("builtins.input", lambda prompt="": "  /opt/jdk  ")

    assert installer.ask_java_home() == "/opt/jdk"
