import io

import pytest
from qrcode.exceptions import DataOverflowError

import qr_generator as qg
from errors import ToolError


class ConsoleWithoutBlocks(io.StringIO):
    """Stands in for a console whose encoding cannot represent block characters."""

    encoding = "cp1252"


def test_build_qr_matrix_has_quiet_zone_and_size_grows_with_text():
    short = qg.build_qr("hola", "M", 10).get_matrix()
    long = qg.build_qr("x" * 300, "M", 10).get_matrix()
    assert len(long) > len(short)
    assert not any(short[0])  # top border row is light


def test_save_png_and_svg(tmp_path):
    qr = qg.build_qr("https://intranet.empresa.com", "M", 10)

    png = tmp_path / "code.png"
    qg.save_qr(qr, png)
    assert png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    svg = tmp_path / "code.svg"
    qg.save_qr(qr, svg)
    assert b"<svg" in svg.read_bytes()


def test_save_rejects_unknown_extension(tmp_path):
    with pytest.raises(ToolError, match="Formato no soportado"):
        qg.save_qr(qg.build_qr("hola", "M", 10), tmp_path / "code.gif")


def test_text_too_long_for_any_qr_raises_value_error():
    with pytest.raises((DataOverflowError, ValueError)):
        qg.build_qr("a" * 4000, "M", 10)


def test_print_terminal_draws_one_row_per_matrix_line(capsys):
    qr = qg.build_qr("hola", "M", 10)
    qg.print_terminal(qr)

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == len(qr.get_matrix())
    assert all(len(line) == 2 * len(qr.get_matrix()) for line in lines)
    assert any("██" in line for line in lines)


def test_print_terminal_falls_back_to_ascii_on_limited_console(monkeypatch):
    fake = ConsoleWithoutBlocks()
    monkeypatch.setattr("sys.stdout", fake)

    qg.print_terminal(qg.build_qr("hola", "M", 10))

    output = fake.getvalue()
    assert "█" not in output
    assert "##" in output


def test_cli_writes_png(tmp_path):
    out = tmp_path / "cli.png"
    qg.main(["--out", str(out), "--", "-texto con guion"])
    assert out.is_file()
