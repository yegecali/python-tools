import json

import audit


def test_record_appends_one_json_line_per_event(isolated_audit_log):
    audit.record("cacerts.install", "ok", alias="github.com", java_home="C:\\jdk-21")
    audit.record("keygen", "ok", name="rsa", bits=2048, protected=True)

    lines = isolated_audit_log.read_text(encoding="utf-8").splitlines()
    first, second = (json.loads(line) for line in lines)

    assert first["action"] == "cacerts.install"
    assert first["status"] == "ok"
    assert first["alias"] == "github.com"
    assert second["protected"] is True
    assert {"time", "user"} <= first.keys()


def test_record_never_stores_what_callers_do_not_pass(isolated_audit_log):
    # The API takes names, paths and counts only; there is no field for values or passwords
    audit.record("decrypt", "error", privkey="keys/rsa_private.pem", reason="llave incorrecta")

    entry = json.loads(isolated_audit_log.read_text(encoding="utf-8"))
    assert "password" not in entry and "value" not in entry and "passphrase" not in entry


def test_a_log_problem_does_not_break_the_operation(tmp_path, monkeypatch, capsys):
    blocked = tmp_path / "archivo"
    blocked.write_text("no es carpeta")
    monkeypatch.setattr(audit, "AUDIT_FILE", blocked / "audit.log")

    audit.record("check", "ok")  # must not raise

    assert "auditoria" in capsys.readouterr().out
