"""The single-instance GTK application that runs the tracker."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from .app import APP_ID, POLL_SECONDS, STATE_FILE, open_path  # noqa: E402
from .config import CONFIG_FILE, ConfigWatcher, ensure_config_file  # noqa: E402
from .idle import IdleMonitor  # noqa: E402
from .report import format_report  # noqa: E402
from .storage import StateStore  # noqa: E402
from .tracker import Tracker  # noqa: E402
from .ui import PromptWindow, ReportWindow, Tray  # noqa: E402


class TimetrackApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.tracker = None
        self.tray = None
        self.prompt_window = None
        self.report_window = None
        self.idle = None
        self.config = None

    # ---- command line (runs in the primary instance) -----------------------------
    def do_command_line(self, cmdline):
        args = cmdline.get_arguments()
        cmd = args[1] if len(args) > 1 else "run"
        out = cmdline.print_literal if hasattr(cmdline, "print_literal") else cmdline.print_

        if cmd == "run":
            if self.tracker is None:
                self._start_tracker()
            else:
                out("timetrack is already running.\n")
            return 0

        running = self.tracker is not None
        if cmd == "quit":
            if running:
                self.quit_tracker()
                out("timetrack stopped.\n")
            else:
                out("timetrack is not running.\n")
            return 0

        if cmd in ("on", "off", "toggle"):
            if running:
                target = (not self.tracker.enabled) if cmd == "toggle" else (cmd == "on")
                self.tracker.set_enabled(target)
                out(self.tracker.status_text() + "\n")
            else:
                state = StateStore(STATE_FILE)
                target = (not state["enabled"]) if cmd == "toggle" else (cmd == "on")
                state["enabled"] = target
                state.save()
                out(f"Tracking will be {'on' if target else 'off'} when timetrack starts "
                    "(it is not running now; start it with `timetrack`).\n")
            return 0

        if cmd == "ask":
            if not running:
                out("timetrack is not running.\n")
                return 1
            if not self.tracker.enabled:
                out("Tracking is off; turn it on with `timetrack on`.\n")
                return 1
            self.tracker.ask_now()
            return 0

        if cmd == "status":
            if running:
                t = self.tracker
                text = t.status_text()
                if t.mode == "active":
                    import time
                    mins = max(0, int((t.next_prompt_at - time.time()) / 60 + 0.5))
                    text += f" (next prompt in ~{mins} min; idle detection: {self.idle.backend or 'none'})"
                out(text + "\n")
            else:
                state = StateStore(STATE_FILE)
                out(f"timetrack is not running (tracking is set to "
                    f"{'on' if state['enabled'] else 'off'}).\n")
            return 0
        return 2

    # ---- tracker ------------------------------------------------------------------------
    def _start_tracker(self):
        ensure_config_file()
        self.config = ConfigWatcher(CONFIG_FILE)
        self.idle = IdleMonitor()
        self.tracker = Tracker(StateStore(STATE_FILE), self.config.get)
        self.tracker.on_show_prompt = self._show_prompt
        self.tracker.on_hide_prompt = self._hide_prompt
        self.tracker.on_change = self._update_tray
        self.tray = Tray({
            "ask": self.tracker.ask_now,
            "toggle": lambda: self.tracker.set_enabled(not self.tracker.enabled),
            "report": self._show_report,
            "open_log": lambda: open_path(self.config.get().log_path),
            "open_config": lambda: open_path(CONFIG_FILE),
            "quit": self.quit_tracker,
        })
        self.hold()
        self.tracker.start()
        self._update_tray()
        GLib.timeout_add_seconds(POLL_SECONDS, self._tick)

    def _tick(self):
        if self.tracker is None:
            return False
        self.tracker.tick(self.idle.get_idle_seconds())
        self._update_tray()
        return True

    def _update_tray(self):
        if self.tray and self.tracker:
            self.tray.update(self.tracker.mode, self.tracker.status_text(),
                             self.tracker.current_project, self.config.get().show_project_in_panel)

    def _show_prompt(self, prompt):
        self._hide_prompt()
        self.prompt_window = PromptWindow(
            self, prompt, self.tracker.projects(),
            on_answer=self._on_answer, on_stop=self._on_stop)

    def _hide_prompt(self):
        if self.prompt_window is not None:
            w, self.prompt_window = self.prompt_window, None
            w.close_silently()

    def _on_answer(self, project, away):
        self.prompt_window = None
        self.tracker.answer(project, away)

    def _on_stop(self):
        self.prompt_window = None
        self.tracker.stop_from_prompt()

    def _show_report(self):
        if self.report_window is not None:
            self.report_window.present()
            return

        def closed(*_):
            self.report_window = None
        self.report_window = ReportWindow(
            self, lambda period: format_report(self.tracker.log, period, self.tracker.state))
        self.report_window.connect("destroy", closed)

    def quit_tracker(self, *_):
        if self.tracker is not None:
            self.tracker.shutdown()
            self.tracker = None
            self._hide_prompt()
            self.release()
        self.quit()
        return GLib.SOURCE_REMOVE
