"""Core time-tracking state machine (no GUI code, so it can be unit-tested).

Rules:
* Choosing a project in a prompt applies from the moment the prompt appeared.
* While a prompt is unanswered, time keeps going to the previous project.
* When the session goes idle, the current segment ends at the last activity.
* When the session returns from idle, time goes to the previous project from
  the moment of return, and the user is prompted right away (optionally being
  offered to log the away period to a project).
* When tracking is turned off, nothing is recorded and no prompts appear. The
  on/off mode is persisted, so it survives restarts and reboots.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional

from .config import Config
from .storage import StateStore, TimeLog

# A gap this long between ticks means the machine was suspended (or the process stopped).
SUSPEND_GAP_SECONDS = 90
# Idle time below this (while we think we're idle) means the user is back.
RETURN_ACTIVITY_SECONDS = 10
CHECKPOINT_SECONDS = 30


@dataclass
class Prompt:
    shown_at: float
    default: Optional[str]
    away: Optional[tuple[float, float]] = None  # (start, end) of an away period to optionally assign


class Tracker:
    def __init__(self, state: StateStore, get_config: Callable[[], Config],
                 now: Callable[[], float] = time.time):
        self.state = state
        self.get_config = get_config
        self.now = now
        self.mode = "off"            # "off" | "active" | "idle"
        self.prompt: Optional[Prompt] = None
        self.next_prompt_at = 0.0
        self.idle_since: Optional[float] = None
        self.last_tick = now()
        self._last_checkpoint = 0.0
        # Callbacks set by the UI layer.
        self.on_show_prompt: Callable[[Prompt], None] = lambda p: None
        self.on_hide_prompt: Callable[[], None] = lambda: None
        self.on_change: Callable[[], None] = lambda: None

    # ---- helpers -----------------------------------------------------------------
    @property
    def config(self) -> Config:
        return self.get_config()

    @property
    def log(self) -> TimeLog:
        return TimeLog(self.config.log_path)

    @property
    def enabled(self) -> bool:
        return bool(self.state["enabled"])

    @property
    def last_project(self) -> Optional[str]:
        return self.state["last_project"]

    @property
    def current_project(self) -> Optional[str]:
        seg = self.state["open_segment"]
        return seg["project"] if seg else None

    def projects(self) -> list[str]:
        extra = [(self.last_project, float("inf"))] if self.last_project else []
        return self.log.projects_by_recency(extra)

    def _open(self, project: str, start: float) -> None:
        self.state["open_segment"] = {"project": project, "start": start, "last_seen": start}

    def _close(self, end: float) -> None:
        seg = self.state["open_segment"]
        if seg:
            self.log.append(seg["start"], max(seg["start"], end), seg["project"])
            self.state["open_segment"] = None

    def _save(self) -> None:
        self.state.save()
        self._last_checkpoint = self.now()
        self.on_change()

    def _schedule_next(self, from_time: float) -> None:
        self.next_prompt_at = from_time + self.config.prompt_interval_minutes * 60

    def _show_prompt(self, away=None) -> None:
        if self.prompt:
            self.on_hide_prompt()
        self.prompt = Prompt(shown_at=self.now(), default=self.last_project, away=away)
        self.on_show_prompt(self.prompt)

    def _hide_prompt(self) -> None:
        if self.prompt:
            self.prompt = None
            self.on_hide_prompt()

    # ---- lifecycle ------------------------------------------------------------------
    def start(self) -> None:
        """Called once at daemon startup."""
        # Recover a segment left open by a crash/reboot: it ends at the last checkpoint.
        seg = self.state["open_segment"]
        if seg:
            self._close(seg.get("last_seen", seg["start"]))
        self.last_tick = self.now()
        if self.enabled:
            self._activate()
        else:
            self.mode = "off"
        self._save()

    def shutdown(self) -> None:
        self._close(self.now())
        self._hide_prompt()
        self.state.save()

    def _activate(self) -> None:
        """Enter active mode: keep the previous project going and ask right away."""
        now = self.now()
        self.mode = "active"
        self.idle_since = None
        if self.last_project and not self.state["open_segment"]:
            self._open(self.last_project, now)
        self._schedule_next(now)
        self._show_prompt()

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self.enabled and (self.mode != "off") == enabled:
            return
        self.state["enabled"] = enabled
        if enabled:
            self._activate()
        else:
            self._close(self.now())
            self._hide_prompt()
            self.mode = "off"
            self.idle_since = None
        self._save()

    def ask_now(self) -> None:
        if self.mode == "off":
            return
        if not self.prompt:
            self._show_prompt()

    # ---- periodic tick ----------------------------------------------------------------
    def tick(self, idle_seconds: Optional[float]) -> None:
        now = self.now()
        gap = now - self.last_tick
        prev_tick = self.last_tick
        self.last_tick = now
        if self.mode == "off":
            return
        cfg = self.config

        if gap > SUSPEND_GAP_SECONDS and self.mode == "active":
            # Machine was asleep: stop counting at the last tick before the gap.
            self._go_idle(prev_tick)

        if self.mode == "active":
            if idle_seconds is not None and idle_seconds >= cfg.idle_threshold_seconds:
                self._go_idle(now - idle_seconds)
            elif (idle_seconds is None and self.prompt
                  and now - self.prompt.shown_at >= cfg.idle_threshold_seconds):
                # No idle detection available: an unanswered prompt means "away".
                # Keep the prompt open; answering it brings us back.
                self._go_idle(self.prompt.shown_at, hide_prompt=False)
            elif not self.prompt and now >= self.next_prompt_at:
                self._show_prompt()

        elif self.mode == "idle":
            if idle_seconds is not None and idle_seconds < RETURN_ACTIVITY_SECONDS:
                self._return_from_idle(now - idle_seconds)

        seg = self.state["open_segment"]
        if seg and self.mode == "active":
            seg["last_seen"] = now
            if now - self._last_checkpoint >= CHECKPOINT_SECONDS:
                self._save()

    def _go_idle(self, since: float, hide_prompt: bool = True) -> None:
        self._close(since)
        self.mode = "idle"
        self.idle_since = since
        if hide_prompt:
            self._hide_prompt()
        self._save()

    def _return_from_idle(self, at: float) -> None:
        away_start = self.idle_since
        self.mode = "active"
        self.idle_since = None
        if self.last_project:
            self._open(self.last_project, at)
        self._schedule_next(at)
        away = (away_start, at) if self.config.on_return == "assign" and away_start else None
        self._show_prompt(away=away)
        self._save()

    # ---- prompt answers -------------------------------------------------------------
    def answer(self, project: Optional[str], away_project: Optional[str] = None) -> None:
        """User picked `project` (None/empty = keep previous) in the current prompt."""
        now = self.now()
        prompt = self.prompt
        self.prompt = None
        project = (project or "").strip() or self.last_project
        away_project = (away_project or "").strip() or None

        if self.mode == "off":
            return
        if self.mode == "idle":
            # Only reachable without idle detection: answering means the user is back.
            away_start = self.idle_since
            self.mode = "active"
            self.idle_since = None
            if away_project and away_start:
                self.log.append(away_start, now, away_project)
            start = now
        else:
            if prompt and prompt.away and away_project:
                self.log.append(prompt.away[0], prompt.away[1], away_project)
            start = prompt.shown_at if prompt else now

        seg = self.state["open_segment"]
        if project:
            if seg and seg["project"] != project:
                self._close(start)
                seg = None
            if not seg:
                self._open(project, min(start, now))
            self.state["open_segment"]["last_seen"] = now
            self.state["last_project"] = project
        self._schedule_next(now)
        self._save()

    def stop_from_prompt(self) -> None:
        """'Stop tracking' button: previous project counts until the prompt appeared."""
        prompt = self.prompt
        self.prompt = None
        if prompt and self.mode == "active":
            self._close(prompt.shown_at)
        self.set_enabled(False)

    # ---- status ------------------------------------------------------------------------
    def status_text(self) -> str:
        if self.mode == "off":
            return "Tracking is off"
        if self.mode == "idle":
            return "Idle (not recording)"
        if self.current_project:
            return f"Tracking: {self.current_project}"
        return "Waiting for a project"
