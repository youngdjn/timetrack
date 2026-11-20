"""Session idle-time detection.

Tries, in order:
  1. GNOME/Mutter's IdleMonitor D-Bus API (works on Wayland and X11 under GNOME)
  2. org.freedesktop.ScreenSaver.GetSessionIdleTime (KDE and some others)
  3. `xprintidle` (any X11 session, if installed)
If none works, get_idle_seconds() returns None and the tracker falls back to
"no response to the popup" as the idle signal.
"""

from __future__ import annotations

import shutil
import subprocess

from gi.repository import Gio, GLib


class IdleMonitor:
    def __init__(self):
        self._bus = None
        self._backend = None  # name of the backend that last worked
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            self._bus = None

    @property
    def backend(self):
        return self._backend

    def _dbus(self, name, path, iface, method):
        res = self._bus.call_sync(name, path, iface, method, None, None,
                                  Gio.DBusCallFlags.NONE, 1000, None)
        return res.unpack()[0]

    def _mutter(self):
        ms = self._dbus("org.gnome.Mutter.IdleMonitor", "/org/gnome/Mutter/IdleMonitor/Core",
                        "org.gnome.Mutter.IdleMonitor", "GetIdletime")
        return ms / 1000.0

    def _freedesktop(self):
        # Returns milliseconds on KDE (spec says seconds; KDE returns ms). Treat as ms.
        ms = self._dbus("org.freedesktop.ScreenSaver", "/org/freedesktop/ScreenSaver",
                        "org.freedesktop.ScreenSaver", "GetSessionIdleTime")
        return ms / 1000.0

    def _xprintidle(self):
        if not shutil.which("xprintidle"):
            raise RuntimeError("xprintidle not installed")
        out = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2, check=True)
        return int(out.stdout.strip()) / 1000.0

    def get_idle_seconds(self):
        backends = [("mutter", self._mutter), ("freedesktop", self._freedesktop),
                    ("xprintidle", self._xprintidle)]
        if self._bus is None:
            backends = backends[2:]
        # Try the backend that worked last time first.
        backends.sort(key=lambda b: b[0] != self._backend)
        for name, fn in backends:
            try:
                value = fn()
            except Exception:
                continue
            self._backend = name
            return max(0.0, float(value))
        self._backend = None
        return None
