# timetrack

A small, prompt-based time tracker for the Linux desktop (built for Ubuntu 26.04 / GNOME).

Every *N* minutes a popup asks **"What are you working on?"**. The last project is
highlighted, so if nothing changed you just press **Enter**. Start typing and the list
of previous projects (most recently used first) filters as you type. If you don't answer
(because you've stepped away), recording stops at the moment the popup appeared.
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
| **Enter** | use the highlighted project (initially your last project; the text box starts empty) |
| type | filter the list (prefix matches first, then anything containing the text) |
| **↑ / ↓**, PgUp/PgDn | move the highlight |
| **Shift+Enter** | use exactly what you typed (e.g. a new project whose name is part of an existing one) |
| **Esc** / close | keep the previous project |

Typing a name that doesn't exist offers **+ New project: "…"**. The **Stop tracking**
button turns tracking off (see below).

Your answer applies **from the moment the popup appeared**. For the first
`response_timeout_seconds` (default 60), time keeps going to the previous project while
the popup waits for you.

### Unanswered prompts (away)

There is no keyboard/mouse idle detection. Instead, if a popup is still unanswered after
`response_timeout_seconds`, you're treated as away: the previous project's entry is
closed **at the moment the popup appeared**, nothing more is recorded, and the popup stays
open until you answer. No further popups appear in the meantime. Suspend/resume works the
same way, with the entry ending when the machine went to sleep.

When you answer, the new entry starts at that moment. With `offer_to_log_away_time = true`
(the default), the popup also says *"No answer since 14:02 — not recording"* and lets you
log the time from then until your answer to a project (e.g. a meeting). Leave it on
*Don't log away time* to drop it.

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
timetrack status          on/off, current project, time until next prompt
timetrack report [PERIOD] totals per project; PERIOD = today (default) | yesterday |
                          week | lastweek | month | all | YYYY-MM-DD | YYYY-MM-DD..YYYY-MM-DD
timetrack quit            stop the tracker until next login (on/off mode is kept)
```

The tray menu also has **Report…**, **Open log file** and **Edit settings**.

## Configuration

`~/.config/timetrack/config.toml` (created on first run; changes apply without restarting):

```toml
prompt_interval_minutes = 15
response_timeout_seconds = 60   # unanswered this long = away (entry ends at prompt time)
offer_to_log_away_time = true   # offer to log the unanswered stretch to a project
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
instead of focusing it. Click the popup (or the notification) before typing. Since an
unanswered popup stops the clock, raise `response_timeout_seconds` if 60 s is too short
to notice it.

## Development

Pure Python 3 + GTK3 via PyGObject; no other dependencies. Run from a checkout with
`python3 -m timetrack`; run tests with `python3 -m unittest discover -s tests`.
The tracking logic (`timetrack/tracker.py`) has no GUI code and is covered by the unit tests.
