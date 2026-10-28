"""Audit trail: one JSON line per operation, in AUDIT_LOG_FILE.

Records what was done, when, by which account and with which result. It never records
secrets: no passwords, no passphrases, no key contents and no values that are encrypted.
"""

import getpass
import json
from datetime import datetime, timezone

import project_settings
import ui

AUDIT_FILE = project_settings.AUDIT_LOG_FILE


def current_user():
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return "desconocido"


def record(action, status, **details):
    """Append one event. Pass paths, names and counts only, never secrets."""
    entry = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": current_user(),
        "action": action,
        "status": status,
        **details,
    }
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_FILE.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        # The operation already happened; a log problem must not hide its result
        print(f"{ui.icon('warn')} No se pudo escribir el log de auditoria: {error}")
