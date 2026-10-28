"""Errors the user can fix.

Modules raise ToolError with a plain message. The menu or the command line decides how to
show it, so the same code works in the interactive menu, in scripts and in tests.
"""

import sys

import ui


class ToolError(Exception):
    """A problem with the input, the configuration or the environment, with a message for the user."""


def run_cli(main):
    """Run a command-line entry point, showing ToolError messages without a traceback."""
    try:
        main()
    except ToolError as error:
        sys.exit(f"{ui.icon('error')} {error}")
    except (KeyboardInterrupt, EOFError):
        sys.exit(f"\n{ui.icon('error')} Cancelado")
