"""Summaries of the time log."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Optional

from .storage import StateStore, TimeLog

PERIOD_HELP = ("today | yesterday | week | lastweek | month | all | "
               "YYYY-MM-DD | YYYY-MM-DD..YYYY-MM-DD")


def period_range(period: str, today: Optional[date] = None):
    """Return (start_ts, end_ts, label) for a period name."""
    today = today or date.today()

    def ts(d: date) -> float:
        return datetime.combine(d, time.min).timestamp()

    p = period.strip().lower()
    if p == "today":
        return ts(today), ts(today + timedelta(1)), f"Today ({today})"
    if p == "yesterday":
        y = today - timedelta(1)
        return ts(y), ts(today), f"Yesterday ({y})"
    if p == "week":
        start = today - timedelta(today.weekday())
        return ts(start), ts(today + timedelta(1)), f"This week (since {start})"
    if p == "lastweek":
        start = today - timedelta(today.weekday() + 7)
        return ts(start), ts(start + timedelta(7)), f"Last week ({start} .. {start + timedelta(6)})"
    if p == "month":
        start = today.replace(day=1)
        return ts(start), ts(today + timedelta(1)), f"This month (since {start})"
    if p == "all":
        return float("-inf"), float("inf"), "All time"
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(?:\.\.(\d{4}-\d{2}-\d{2}))?", p)
    if m:
        a = date.fromisoformat(m.group(1))
        b = date.fromisoformat(m.group(2)) if m.group(2) else a
        label = str(a) if a == b else f"{a} .. {b}"
        return ts(a), ts(b + timedelta(1)), label
    raise ValueError(f"unknown period '{period}' (use {PERIOD_HELP})")


def totals(log: TimeLog, start: float, end: float, state: Optional[StateStore] = None):
    out: dict[str, float] = defaultdict(float)
    segments = list(log.rows())
    if state is not None and state["open_segment"]:
        seg = state["open_segment"]
        segments.append((seg["start"], seg.get("last_seen", seg["start"]), seg["project"]))
    for s, e, project in segments:
        overlap = min(e, end) - max(s, start)
        if overlap > 0:
            out[project] += overlap
    return dict(out)


def fmt_duration(seconds: float) -> str:
    minutes = int(round(seconds / 60))
    return f"{minutes // 60}:{minutes % 60:02d}"


def format_report(log: TimeLog, period: str = "today", state: Optional[StateStore] = None) -> str:
    start, end, label = period_range(period)
    t = totals(log, start, end, state)
    lines = [label, ""]
    if not t:
        lines.append("  (no time recorded)")
        return "\n".join(lines)
    width = max(len(p) for p in t)
    width = max(width, len("Total"))
    for project, secs in sorted(t.items(), key=lambda kv: kv[1], reverse=True):
        lines.append(f"  {project:<{width}}  {fmt_duration(secs):>7}  ({secs / 3600:.2f} h)")
    total = sum(t.values())
    lines.append(f"  {'-' * width}  {'-' * 7}")
    lines.append(f"  {'Total':<{width}}  {fmt_duration(total):>7}  ({total / 3600:.2f} h)")
    return "\n".join(lines)
