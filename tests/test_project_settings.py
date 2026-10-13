import os
from pathlib import Path

import pytest

import project_settings as ps


def test_env_file_parses_quotes_comments_and_blank_lines(tmp_path, monkeypatch):
    for name in ("TEST_A", "TEST_B", "TEST_C"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    env.write_text('# comentario\n\nTEST_A = "hola mundo"\nTEST_B=\'x=y\'\nTEST_C=\n', encoding="utf-8")

    ps._load_env_file(env)

    assert os.environ["TEST_A"] == "hola mundo"
    assert os.environ["TEST_B"] == "x=y"
    assert os.environ["TEST_C"] == ""


def test_real_environment_variable_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PRIORITY", "del-sistema")
    env = tmp_path / ".env"
    env.write_text("TEST_PRIORITY=del-archivo\n", encoding="utf-8")

    ps._load_env_file(env)

    assert os.environ["TEST_PRIORITY"] == "del-sistema"


def test_env_file_line_without_equals_exits(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LINEA ROTA\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="falta '='"):
        ps._load_env_file(env)


def test_missing_env_file_is_ignored(tmp_path):
    ps._load_env_file(tmp_path / "no-existe.env")  # must not raise


def test_get_returns_default_when_missing_or_empty(monkeypatch):
    monkeypatch.delenv("TEST_MISSING", raising=False)
    assert ps.get("TEST_MISSING", "dflt") == "dflt"
    monkeypatch.setenv("TEST_MISSING", "   ")
    assert ps.get("TEST_MISSING", "dflt") == "dflt"


def test_get_int_parses_and_rejects_invalid(monkeypatch):
    monkeypatch.setenv("TEST_INT", "42")
    assert ps.get_int("TEST_INT", 1) == 42
    monkeypatch.setenv("TEST_INT", "abc")
    with pytest.raises(SystemExit, match="TEST_INT"):
        ps.get_int("TEST_INT", 1)


def test_get_choice_accepts_listed_values_only(monkeypatch):
    monkeypatch.setenv("TEST_CHOICE", "H")
    assert ps.get_choice("TEST_CHOICE", "M", ["L", "M", "Q", "H"]) == "H"
    monkeypatch.setenv("TEST_CHOICE", "X")
    with pytest.raises(SystemExit, match="TEST_CHOICE"):
        ps.get_choice("TEST_CHOICE", "M", ["L", "M", "Q", "H"])


def test_get_path_resolves_relative_paths_from_project_root(monkeypatch):
    monkeypatch.delenv("TEST_PATH", raising=False)
    assert ps.get_path("TEST_PATH", "keys/public-key.pem") == ps.ROOT / "keys" / "public-key.pem"


def test_get_path_keeps_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_PATH", str(tmp_path))
    assert ps.get_path("TEST_PATH", "keys") == tmp_path
    assert isinstance(ps.get_path("TEST_PATH", "keys"), Path)
