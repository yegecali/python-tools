import sys
from types import SimpleNamespace

import ui


def test_icon_uses_emoji_when_console_can_show_it(monkeypatch):
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(encoding="utf-8"))
    assert ui.icon("error") == "❌"


def test_icon_falls_back_to_plain_text_on_legacy_console(monkeypatch):
    monkeypatch.setattr(sys, "stdout", SimpleNamespace(encoding="cp850"))
    assert ui.icon("error") == "[x]"
    assert ui.icon("warn") == "[!]"
