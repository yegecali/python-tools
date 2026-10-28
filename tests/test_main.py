import sys

import pytest

import main as app
import qr_generator
import rsa_keygen
from errors import ToolError


def test_menu_lists_every_tool():
    labels = [tool.label for tool in app.MENU]
    assert len(labels) == 8
    assert any("QR" in label for label in labels)
    assert any("Windows" in label for label in labels)


def test_windows_option_says_when_unavailable(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "solo disponible en Windows" in app.windows_label()
    monkeypatch.setattr(sys, "platform", "win32")
    assert "solo disponible en Windows" not in app.windows_label()


def test_run_step_prints_exit_message_and_keeps_going(capsys):
    def failing():
        raise ToolError("algo salio mal")

    app.run_step(failing)  # must not propagate
    assert "algo salio mal" in capsys.readouterr().out


def test_run_step_reports_numeric_failure(capsys):
    def failing():
        raise SystemExit(1)

    app.run_step(failing)
    assert "termino con errores" in capsys.readouterr().out


def test_run_step_passes_through_success():
    calls = []
    app.run_step(lambda *args: calls.append(args), 1, 2)
    assert calls == [(1, 2)]


def test_dispatch_routes_qr_to_generator(monkeypatch):
    received = []
    monkeypatch.setattr(qr_generator, "main", lambda argv=None: received.append(argv))

    app.dispatch(["qr", "--", "hola"])

    assert received == [["--", "hola"]]


def test_dispatch_rejects_unknown_command():
    with pytest.raises(ToolError, match="Comando desconocido"):
        app.dispatch(["nada"])


def test_menu_runs_the_chosen_tool_and_exits_on_zero(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(app, "MENU", [app.Tool("Prueba", "tool_qr", lambda: called.append("ok"))])
    answers = iter(["9", "1", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    app.menu()

    assert called == ["ok"]
    assert "Opcion no valida" in capsys.readouterr().out


def test_menu_survives_a_tool_error(monkeypatch, capsys):
    def broken():
        raise app.ToolError("algo fallo")

    monkeypatch.setattr(app, "MENU", [app.Tool("Roto", "tool_qr", broken)])
    answers = iter(["1", "0"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))

    app.menu()

    assert "algo fallo" in capsys.readouterr().out


def test_dispatch_routes_keygen_arguments(monkeypatch):
    received = []
    monkeypatch.setattr(rsa_keygen, "main", lambda argv=None: received.append(argv))

    app.dispatch(["keygen", "--name", "prueba"])

    assert received == [["--name", "prueba"]]


def test_flag_only_adds_arguments_with_a_value():
    assert app.flag("--out", "salida.json") == ["--out", "salida.json"]
    assert app.flag("--out", "") == []
