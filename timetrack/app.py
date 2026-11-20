"""Entry point: the background app (Gtk.Application) and the command-line interface."""

from __future__ import annotations

import signal
import subprocess
import sys

from . import __version__
from .config import CONFIG_FILE, STATE_DIR, ConfigWatcher, ensure_config_file
from .report import PERIOD_HELP, format_report
from .storage import StateStore, TimeLog

APP_ID = "io.github.youngdjn.Timetrack"
POLL_SECONDS = 5
STATE_FILE = STATE_DIR / "state.json"

USAGE = f"""\
usage: timetrack [command]

Commands:
  (none) | run     start the background tracker (normally started at login)
  on               turn prompting/recording on
  off              turn prompting/recording off (stays off across reboots)
  toggle           switch between on and off
  ask              show the "what are you working on?" prompt now
  status           show whether tracking is on and the current project
  report [PERIOD]  total time per project; PERIOD = {PERIOD_HELP}
                   (default: today)
  quit             stop the background tracker (it restarts at next login)
  version          print the version
"""


def _report(args) -> int:
    cfg = ConfigWatcher(CONFIG_FILE).get()
    try:
        print(format_report(TimeLog(cfg.log_path), args[0] if args else "today",
                            StateStore(STATE_FILE)))
    except ValueError as e:
        print(f"timetrack: {e}", file=sys.stderr)
        return 2
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    args = argv[1:]
    cmd = args[0] if args else "run"
    if cmd in ("-h", "--help", "help"):
        print(USAGE, end="")
        return 0
    if cmd in ("version", "--version"):
        print(__version__)
        return 0
    if cmd == "report":
        return _report(args[1:])
    if cmd not in ("run", "on", "off", "toggle", "ask", "status", "quit"):
        print(f"timetrack: unknown command '{cmd}'\n\n{USAGE}", file=sys.stderr, end="")
        return 2

    # Everything else goes through the single-instance GTK application, so that
    # commands reach the running tracker.
    from gi.repository import GLib

    from .gtk_app import TimetrackApp
    app = TimetrackApp()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.quit_tracker)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, app.quit_tracker)
    return app.run([argv[0], cmd])


def open_path(path) -> None:
    try:
        subprocess.Popen(["xdg-open", str(path)])
    except OSError as e:
        print(f"timetrack: could not open {path}: {e}")


__all__ = ["main", "APP_ID", "POLL_SECONDS", "STATE_FILE", "open_path", "ensure_config_file"]
