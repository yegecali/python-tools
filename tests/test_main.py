import sys

import pytest

import main as app
import qr_generator


def test_menu_lists_every_tool():
    labels = [label for label, _ in app.MENU]
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
        raise SystemExit("[x] algo salio mal")

    app.run_step(failing)  # must not propagate
    assert "[x] algo salio mal" in capsys.readouterr().out


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
    with pytest.raises(SystemExit, match="Comando desconocido"):
        app.dispatch(["nada"])
