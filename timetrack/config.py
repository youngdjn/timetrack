"""User configuration (~/.config/timetrack/config.toml)."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", ".config") / "timetrack"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "timetrack"
STATE_DIR = _xdg("XDG_STATE_HOME", ".local/state") / "timetrack"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_CONFIG_TEXT = """\
# timetrack configuration. Changes are picked up automatically (no restart needed).

# Minutes between "What are you working on?" prompts.
prompt_interval_minutes = 15

# If a prompt is still unanswered after this many seconds, you're considered away:
# the previous project's time ends at the moment the prompt appeared, and nothing is
# recorded until you answer.
response_timeout_seconds = 60

# When you finally answer such a prompt, offer to log the unanswered stretch to a
# project (e.g. a meeting). Leave that field empty to not log it.
offer_to_log_away_time = true

# Show the current project's name next to the tray icon.
show_project_in_panel = true

# Where the time log (CSV) is written. Empty = ~/.local/share/timetrack/log.csv
log_file = ""
"""


@dataclass
class Config:
    prompt_interval_minutes: float = 15
    response_timeout_seconds: float = 60
    offer_to_log_away_time: bool = True
    show_project_in_panel: bool = True
    log_file: str = ""

    @property
    def log_path(self) -> Path:
        return Path(os.path.expanduser(self.log_file)) if self.log_file else DATA_DIR / "log.csv"


def ensure_config_file(path: Path = CONFIG_FILE) -> None:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TEXT)


def load_config(path: Path = CONFIG_FILE) -> Config:
    cfg = Config()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return cfg
    except (tomllib.TOMLDecodeError, OSError) as e:
        print(f"timetrack: ignoring invalid config {path}: {e}")
        return cfg

    def num(key, minimum):
        v = data.get(key, getattr(cfg, key))
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= minimum:
            setattr(cfg, key, float(v))
        else:
            print(f"timetrack: config '{key}' must be a number >= {minimum}; using default")

    # Settings from version 0.1 (session idle detection) map onto the new ones.
    if "response_timeout_seconds" not in data and "idle_threshold_seconds" in data:
        data["response_timeout_seconds"] = data["idle_threshold_seconds"]
    if "offer_to_log_away_time" not in data and "on_return" in data:
        data["offer_to_log_away_time"] = data["on_return"] != "prompt"

    num("prompt_interval_minutes", 0.1)
    num("response_timeout_seconds", 5)
    cfg.offer_to_log_away_time = bool(data.get("offer_to_log_away_time", True))
    cfg.show_project_in_panel = bool(data.get("show_project_in_panel", cfg.show_project_in_panel))
    cfg.log_file = str(data.get("log_file", "") or "")
    return cfg


class ConfigWatcher:
    """Reloads the config file whenever its mtime changes."""

    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self._mtime = None
        self.config = load_config(path)
        self._mtime = self._stat()

    def _stat(self):
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def get(self) -> Config:
        m = self._stat()
        if m != self._mtime:
            self._mtime = m
            self.config = load_config(self.path)
        return self.config
