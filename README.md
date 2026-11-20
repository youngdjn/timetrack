# timetrack

A small, prompt-based time tracker for the Linux desktop (built for Ubuntu 26.04 / GNOME).

Every *N* minutes a popup asks **"What are you working on?"**. The last project is
pre-selected, so if nothing changed you just press **Enter**. Start typing and the list
of previous projects (most recently used first) filters as you type. When you step away
from the computer, recording stops automatically at your last keyboard/mouse activity.
Everything is stored in a plain CSV file.

## Install

```bash
git clone https://github.com/youngdjn/timetrack.git
cd timetrack
./install.sh
```

The installer:

* installs the needed system packages with apt if they're missing (`python3-gi`,
  `gir1.2-gtk-3.0`, `gir1.2-ayatanaappindicator3-0.1`) — this is the only step that uses `sudo`;
* copies the app to `~/.local/lib/timetrack` and puts a `timetrack` command in `~/.local/bin`;
* adds it to your login autostart and to the app grid, and starts it.

Re-run `./install.sh` after pulling updates. `./uninstall.sh` removes it (add `--purge` to
also delete your log and settings).

The tray icon uses Ubuntu's built-in *Ubuntu AppIndicators* GNOME extension, which is
enabled by default on Ubuntu. On a stock (non-Ubuntu) GNOME, install the
"AppIndicator and KStatusNotifierItem Support" extension, or just use the CLI.

## Using it

### The popup

| Key | Action |
|---|---|
| **Enter** | use the highlighted project (initially your last project) |
| type | filter the list (prefix matches first, then anything containing the text) |
| **↑ / ↓**, PgUp/PgDn | move the highlight |
| **Shift+Enter** | use exactly what you typed (e.g. a new project whose name is part of an existing one) |
| **Esc** / close | keep the previous project |

Typing a name that doesn't exist offers **+ New project: "…"**. The **Stop tracking**
button turns tracking off (see below).

Your answer applies **from the moment the popup appeared**. Until you answer, time keeps
going to the previous project, and the popup stays open.

### Idle / away

The session's idle time is read from GNOME (Mutter's IdleMonitor D-Bus API, which works on
Wayland), falling back to `org.freedesktop.ScreenSaver` (KDE) or `xprintidle` (X11).
When there has been no keyboard/mouse input for `idle_threshold_seconds` (default 60),
the current entry is closed **at the time of your last activity**. Suspend/resume is
treated the same way.

When you come back, you're prompted right away. With `on_return = "assign"` (the default),
the popup also says *"You were away 14:02–14:47 (45 min)"* and lets you log that period to
a project (e.g. a meeting); leave it on *Don't log away time* to drop it. With
`on_return = "prompt"`, away time is never logged.

If no idle detection is available at all, an unanswered popup is treated as "away" after
`idle_threshold_seconds`, counted from when the popup appeared.

### Turning it on/off

Use the tray menu (**Stop tracking** / **Resume tracking**), the **Stop tracking** button in
the popup, or the CLI. When off, nothing is recorded and no popups appear. The on/off
state is saved, so after a reboot it comes back in the same mode. Turning it on prompts
you right away.

### Command line

```text
timetrack                 start the background tracker (done automatically at login)
timetrack on | off | toggle
timetrack ask             show the prompt now
timetrack status          on/off, current project, next prompt, idle backend
timetrack report [PERIOD] totals per project; PERIOD = today (default) | yesterday |
                          week | lastweek | month | all | YYYY-MM-DD | YYYY-MM-DD..YYYY-MM-DD
timetrack quit            stop the tracker until next login (on/off mode is kept)
```

The tray menu also has **Report…**, **Open log file** and **Edit settings**.

## Configuration

`~/.config/timetrack/config.toml` (created on first run; changes apply without restarting):

```toml
prompt_interval_minutes = 15
idle_threshold_seconds = 60
on_return = "assign"          # or "prompt"
show_project_in_panel = true  # show the project name next to the tray icon
log_file = ""                 # default: ~/.local/share/timetrack/log.csv
```

## Data

* **Time log:** `~/.local/share/timetrack/log.csv`. One row per stretch of time:

  ```csv
  start,end,minutes,project
  2026-11-20T09:00:00-08:00,2026-11-20T10:12:31-08:00,72.52,Website redesign
  ```

  Edit it freely (for example, rename a project). The project list in the popup is built
  from this file.
* **State:** `~/.local/state/timetrack/state.json`. Holds the on/off mode, last project, and
  the stretch currently in progress. That stretch is saved every 30 s, so a crash or power
  cut loses at most about 30 s.

## Notes on Wayland

GNOME on Wayland doesn't let background apps steal keyboard focus. The popup opens on top
of other windows, but GNOME may sometimes show a *"Timetrack is ready"* notification
instead of focusing it. Click the popup (or the notification) before typing. Pressing Enter
is never required for time to keep counting.

## Development

Pure Python 3 + GTK3 via PyGObject; no other dependencies. Run from a checkout with
`python3 -m timetrack`; run tests with `python3 -m unittest discover -s tests`.
The tracking logic (`timetrack/tracker.py`) has no GUI code and is covered by the unit tests.
