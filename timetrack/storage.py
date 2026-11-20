"""Persistence: the CSV time log and the small JSON state file."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path

LOG_HEADER = ["start", "end", "minutes", "project"]


def fmt_ts(t: float) -> str:
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def parse_ts(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class TimeLog:
    """Append-only CSV of completed time segments."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, start: float, end: float, project: str) -> None:
        if end - start < 1 or not project:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists() or self.path.stat().st_size == 0
        with open(self.path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(LOG_HEADER)
            w.writerow([fmt_ts(start), fmt_ts(end), f"{(end - start) / 60:.2f}", project])

    def rows(self):
        """Yield (start, end, project) tuples; malformed lines are skipped."""
        try:
            f = open(self.path, newline="")
        except FileNotFoundError:
            return
        with f:
            for row in csv.DictReader(f):
                try:
                    yield parse_ts(row["start"]), parse_ts(row["end"]), row["project"]
                except (KeyError, ValueError, TypeError):
                    continue

    def projects_by_recency(self, extra: list[tuple[str, float]] = ()) -> list[str]:
        last_used: dict[str, float] = {}
        for _start, end, project in self.rows():
            if end > last_used.get(project, float("-inf")):
                last_used[project] = end
        for project, t in extra:
            if project and t > last_used.get(project, float("-inf")):
                last_used[project] = t
        return sorted(last_used, key=lambda p: last_used[p], reverse=True)


class StateStore:
    """Persistent state: on/off mode, last project, and the in-progress segment.

    The in-progress segment is checkpointed regularly so that a crash, power loss
    or reboot loses at most a minute of time.
    """

    DEFAULTS = {"enabled": True, "last_project": None, "open_segment": None}

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = dict(self.DEFAULTS)
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self.data.update({k: loaded[k] for k in self.DEFAULTS if k in loaded})
        except (FileNotFoundError, ValueError, OSError):
            pass

    def save(self) -> None:
        _atomic_write(self.path, json.dumps(self.data, indent=2) + "\n")

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
