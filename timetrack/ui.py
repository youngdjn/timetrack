"""GTK3 user interface: the prompt popup, the report window and the tray icon."""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

_Indicator = None
for _ns in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(_ns, "0.1")
        _Indicator = __import__("gi.repository", fromlist=[_ns]).__dict__[_ns]
        break
    except (ValueError, ImportError, KeyError):
        continue

APP_ICON = "preferences-system-time-symbolic"
ICON_ACTIVE = "preferences-system-time-symbolic"
ICON_IDLE = "user-idle-symbolic"
ICON_OFF = "media-playback-pause-symbolic"


def rank_projects(projects: list[str], text: str) -> list[str]:
    """Filter projects by `text`: prefix matches first, then substring matches (both
    keep most-recently-used order)."""
    q = text.strip().casefold()
    if not q:
        return list(projects)
    prefix = [p for p in projects if p.casefold().startswith(q)]
    contains = [p for p in projects if q in p.casefold() and p not in prefix]
    return prefix + contains


class ProjectPicker(Gtk.Box):
    """A text entry with a live-filtered list of projects underneath.

    Up/Down move the highlight; Enter picks the highlighted row (or emits `activate`
    with the typed text if nothing matches); Shift+Enter uses the typed text as-is.
    """

    def __init__(self, projects: list[str], default: Optional[str], none_label: Optional[str],
                 on_activate: Callable[[], None], list_height: int = 200):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.projects = projects
        self.none_label = none_label
        self.on_activate = on_activate
        self.default = default  # highlighted while the entry is empty

        self.entry = Gtk.Entry()
        if default:
            self.entry.set_placeholder_text(f"Enter = \u201c{default}\u201d, or type to filter / add new")
        else:
            self.entry.set_placeholder_text("Type to filter or enter a new project name")
        self.entry.set_activates_default(False)
        self.entry.connect("changed", self._on_changed)
        self.entry.connect("key-press-event", self._on_key)
        self.entry.connect("activate", lambda *_: self._activate(exact=False))
        self.pack_start(self.entry, False, False, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.listbox.set_activate_on_single_click(True)
        self.listbox.connect("row-activated", self._on_row_activated)
        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(list_height)
        sw.set_max_content_height(list_height)
        sw.set_shadow_type(Gtk.ShadowType.IN)
        sw.add(self.listbox)
        self.scroller = sw
        self.pack_start(sw, True, True, 0)
        self._refill()

    # Each row stores ("project", name) | ("new", name) | ("none", None).
    def _add_row(self, kind: str, value: Optional[str], label: str, italic=False):
        row = Gtk.ListBoxRow()
        row.kind, row.value = kind, value
        lab = Gtk.Label(label=label, xalign=0)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        lab.set_margin_start(6)
        lab.set_margin_end(6)
        lab.set_margin_top(3)
        lab.set_margin_bottom(3)
        if italic:
            lab.set_markup(f"<i>{GLib.markup_escape_text(label)}</i>")
        row.add(lab)
        self.listbox.add(row)
        return row

    def _refill(self):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        text = self.entry.get_text()
        if self.none_label and not text.strip():
            self._add_row("none", None, self.none_label, italic=True)
        matches = rank_projects(self.projects, text)
        for p in matches:
            self._add_row("project", p, p)
        typed = text.strip()
        if typed and not any(p.casefold() == typed.casefold() for p in self.projects):
            self._add_row("new", typed, f"+ New project: “{typed}”", italic=True)
        self.listbox.show_all()
        rows = self.listbox.get_children()
        if rows:
            preferred = [r for r in rows if r.value == self.default] if not text.strip() else []
            self.listbox.select_row((preferred or rows)[0])

    def _on_changed(self, *_):
        self._refill()

    def _move(self, delta: int):
        row = self.listbox.get_selected_row()
        idx = (row.get_index() if row else -1) + delta
        n = len(self.listbox.get_children())
        if n == 0:
            return
        new = self.listbox.get_row_at_index(max(0, min(n - 1, idx)))
        self.listbox.select_row(new)
        adj = self.scroller.get_vadjustment()
        alloc = new.get_allocation()
        if alloc.y < adj.get_value():
            adj.set_value(alloc.y)
        elif alloc.y + alloc.height > adj.get_value() + adj.get_page_size():
            adj.set_value(alloc.y + alloc.height - adj.get_page_size())

    def _on_key(self, _w, ev):
        key = ev.keyval
        if key in (Gdk.KEY_Down, Gdk.KEY_KP_Down):
            self._move(1)
            return True
        if key in (Gdk.KEY_Up, Gdk.KEY_KP_Up):
            self._move(-1)
            return True
        if key in (Gdk.KEY_Page_Down,):
            self._move(8)
            return True
        if key in (Gdk.KEY_Page_Up,):
            self._move(-8)
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and ev.state & Gdk.ModifierType.SHIFT_MASK:
            self._activate(exact=True)
            return True
        return False

    def _on_row_activated(self, _lb, row):
        self.listbox.select_row(row)
        self.on_activate()

    def _activate(self, exact: bool):
        if exact:
            self._exact = True
        self.on_activate()

    def value(self) -> Optional[str]:
        """The chosen project, or None for 'nothing' (none row / empty entry)."""
        if getattr(self, "_exact", False):
            return self.entry.get_text().strip() or None
        row = self.listbox.get_selected_row()
        if row is not None:
            return row.value
        return self.entry.get_text().strip() or None


def _hm(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%H:%M")


class PromptWindow(Gtk.Window):
    def __init__(self, app, prompt, projects: list[str],
                 on_answer: Callable[[Optional[str], Optional[str]], None],
                 on_stop: Callable[[], None]):
        super().__init__(application=app, title="Timetrack")
        self._done = False
        self.on_answer = on_answer
        self.on_stop = on_stop
        self.default = prompt.default
        self.set_icon_name(APP_ICON)
        self.set_keep_above(True)
        self.stick()
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_default_size(420, -1)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_urgency_hint(True)
        self.connect("delete-event", self._on_delete)
        self.connect("key-press-event", self._on_key)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(14)
        self.add(box)

        self.away_picker = None
        if prompt.away:
            a, b = prompt.away
            mins = int(round((b - a) / 60))
            lab = Gtk.Label(xalign=0)
            lab.set_markup(f"<b>You were away {_hm(a)}–{_hm(b)} ({mins} min).</b>\n"
                           "Log that time to a project? (e.g. a meeting)")
            box.pack_start(lab, False, False, 0)
            self.away_picker = ProjectPicker(projects, None, "Don’t log away time",
                                             self._submit, list_height=110)
            box.pack_start(self.away_picker, False, False, 0)
            box.pack_start(Gtk.Separator(), False, False, 4)

        title = Gtk.Label(xalign=0)
        title.set_markup("<b>What are you working on?</b>")
        box.pack_start(title, False, False, 0)
        self.picker = ProjectPicker(projects, prompt.default, None, self._submit)
        box.pack_start(self.picker, True, True, 0)

        hint = Gtk.Label(xalign=0)
        hint.set_line_wrap(True)
        keep = f"keep “{GLib.markup_escape_text(prompt.default)}”" if prompt.default else "dismiss"
        hint.set_markup("<small>Enter: highlighted project · ↑↓: move · "
                        f"Shift+Enter: exactly what you typed · Esc: {keep}</small>")
        hint.get_style_context().add_class("dim-label")
        box.pack_start(hint, False, False, 0)

        buttons = Gtk.Box(spacing=6)
        stop = Gtk.Button(label="Stop tracking")
        stop.set_tooltip_text("Turn off prompts and recording until you turn it back on")
        stop.connect("clicked", self._on_stop_clicked)
        ok = Gtk.Button(label="OK")
        ok.get_style_context().add_class("suggested-action")
        ok.connect("clicked", lambda *_: self._submit())
        buttons.pack_start(stop, False, False, 0)
        buttons.pack_end(ok, False, False, 0)
        box.pack_start(buttons, False, False, 0)

        self.show_all()
        self.picker.entry.grab_focus()
        self.present_with_time(Gtk.get_current_event_time() or Gdk.CURRENT_TIME)

    def _finish(self):
        self._done = True
        self.destroy()

    def _submit(self):
        if self._done:
            return
        project = self.picker.value()
        if not project and not self.default:
            self.picker.entry.grab_focus()
            return
        away = self.away_picker.value() if self.away_picker else None
        self._finish()
        self.on_answer(project, away)

    def _keep_previous(self):
        if not self._done:
            self._finish()
            self.on_answer(None, None)

    def _on_stop_clicked(self, *_):
        if not self._done:
            self._finish()
            self.on_stop()

    def _on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self._keep_previous()
            return True
        return False

    def _on_delete(self, *_):
        self._keep_previous()
        return True

    def close_silently(self):
        if not self._done:
            self._finish()


class ReportWindow(Gtk.Window):
    def __init__(self, app, make_text: Callable[[str], str]):
        super().__init__(application=app, title="Timetrack report")
        self.make_text = make_text
        self.set_icon_name(APP_ICON)
        self.set_default_size(460, 380)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(10)
        self.add(box)
        combo = Gtk.ComboBoxText()
        for key, label in [("today", "Today"), ("yesterday", "Yesterday"), ("week", "This week"),
                           ("lastweek", "Last week"), ("month", "This month"), ("all", "All time")]:
            combo.append(key, label)
        combo.set_active_id("today")
        combo.connect("changed", lambda c: self._update(c.get_active_id()))
        box.pack_start(combo, False, False, 0)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
        self.view.set_left_margin(8)
        self.view.set_top_margin(8)
        sw = Gtk.ScrolledWindow()
        sw.add(self.view)
        box.pack_start(sw, True, True, 0)
        self._update("today")
        self.show_all()
        self.present()

    def _update(self, period):
        self.view.get_buffer().set_text(self.make_text(period))


class Tray:
    """Top-bar icon (AppIndicator / StatusNotifierItem). No-op if the library is missing."""

    def __init__(self, actions: dict[str, Callable[[], None]]):
        self.available = _Indicator is not None
        if not self.available:
            print("timetrack: AppIndicator library not found; no tray icon "
                  "(install gir1.2-ayatanaappindicator3-0.1). Use the CLI to control it.")
            return
        self.ind = _Indicator.Indicator.new("timetrack", ICON_ACTIVE,
                                            _Indicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(_Indicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("Timetrack")
        menu = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        menu.append(Gtk.SeparatorMenuItem())
        self.ask_item = Gtk.MenuItem(label="Change project now…")
        self.ask_item.connect("activate", lambda *_: actions["ask"]())
        menu.append(self.ask_item)
        self.toggle_item = Gtk.MenuItem(label="")
        self.toggle_item.connect("activate", lambda *_: actions["toggle"]())
        menu.append(self.toggle_item)
        menu.append(Gtk.SeparatorMenuItem())
        for label, key in [("Report…", "report"), ("Open log file", "open_log"),
                           ("Edit settings", "open_config")]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", lambda _i, k=key: actions[k]())
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Quit (until next login)")
        quit_item.connect("activate", lambda *_: actions["quit"]())
        menu.append(quit_item)
        menu.show_all()
        self.ind.set_menu(menu)

    def update(self, mode: str, status: str, project: Optional[str], show_label: bool):
        if not self.available:
            return
        icon = {"active": ICON_ACTIVE, "idle": ICON_IDLE}.get(mode, ICON_OFF)
        self.ind.set_icon_full(icon, status)
        self.ind.set_label(project if (show_label and mode == "active" and project) else "", "")
        self.status_item.set_label(status)
        self.toggle_item.set_label("Resume tracking" if mode == "off" else "Stop tracking")
        self.ask_item.set_sensitive(mode != "off")
