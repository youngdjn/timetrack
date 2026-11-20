import tempfile
import unittest
from pathlib import Path

from timetrack.config import Config
from timetrack.report import totals
from timetrack.storage import StateStore, TimeLog
from timetrack.tracker import Tracker


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.cfg = Config(prompt_interval_minutes=15, idle_threshold_seconds=60,
                          on_return="assign", log_file=str(self.dir / "log.csv"))
        self.clock = Clock()
        self.state = StateStore(self.dir / "state.json")
        self.shown = []
        self.hidden = 0
        self.t = self.make()

    def make(self):
        t = Tracker(self.state, lambda: self.cfg, now=self.clock)
        t.on_show_prompt = self.shown.append

        def hide():
            self.hidden += 1
        t.on_hide_prompt = hide
        return t

    def advance(self, seconds, idle=0.0, step=5):
        """Advance time, ticking every `step` seconds; `idle` is a function or a constant
        giving the session idle time at each tick."""
        end = self.clock.t + seconds
        while self.clock.t < end:
            self.clock.t = min(end, self.clock.t + step)
            self.t.tick(idle(self.clock.t) if callable(idle) else idle)

    def rows(self):
        return [(round(s - 1_000_000), round(e - 1_000_000), p)
                for s, e, p in TimeLog(self.cfg.log_path).rows()]


class TrackerTests(Base):
    def test_first_start_prompts_and_records_nothing_until_answer(self):
        self.t.start()
        self.assertEqual(len(self.shown), 1)
        self.assertIsNone(self.t.current_project)
        self.advance(30)
        self.t.answer("alpha")
        # Applies from when the prompt appeared.
        self.assertEqual(self.state["open_segment"]["start"], 1_000_000)
        self.assertEqual(self.t.last_project, "alpha")

    def test_periodic_prompt_and_switch_applies_from_prompt_time(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60)
        self.assertEqual(len(self.shown), 2)
        self.assertEqual(self.shown[-1].default, "alpha")
        prompt_time = self.shown[-1].shown_at
        self.advance(40)  # user takes 40s to answer
        self.t.answer("beta")
        self.assertEqual(self.rows(), [(0, round(prompt_time - 1_000_000), "alpha")])
        self.assertEqual(self.t.current_project, "beta")

    def test_unanswered_prompt_keeps_previous_project(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 300)  # prompt open, user active, no answer
        self.assertEqual(self.t.current_project, "alpha")
        self.assertEqual(self.t.mode, "active")
        self.t.answer(None)  # Esc
        self.assertEqual(self.t.current_project, "alpha")
        self.assertEqual(self.rows(), [])

    def test_idle_ends_segment_at_last_activity_and_return_prompts_with_away(self):
        self.t.start()
        self.t.answer("alpha")
        last_activity = self.clock.t + 600
        self.advance(900, idle=lambda now: max(0, now - last_activity))
        self.assertEqual(self.t.mode, "idle")
        self.assertEqual(self.rows(), [(0, 600, "alpha")])
        # User comes back.
        self.advance(5, idle=0)
        self.assertEqual(self.t.mode, "active")
        self.assertEqual(self.t.current_project, "alpha")
        p = self.shown[-1]
        self.assertEqual(round(p.away[0] - 1_000_000), 600)
        self.assertEqual(round(p.away[1] - 1_000_000), 905)
        self.t.answer("alpha", away_project="meeting")
        self.assertIn((600, 905, "meeting"), self.rows())
        self.assertEqual(self.t.projects()[:2], ["alpha", "meeting"])

    def test_return_mode_prompt_has_no_away(self):
        self.cfg.on_return = "prompt"
        self.t.start()
        self.t.answer("alpha")
        self.advance(200, idle=lambda now: now - 1_000_000)
        self.advance(5, idle=0)
        self.assertIsNone(self.shown[-1].away)

    def test_off_persists_and_stops_recording(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(120)
        self.t.set_enabled(False)
        self.assertEqual(self.rows(), [(0, 120, "alpha")])
        n = len(self.shown)
        self.advance(3600)
        self.assertEqual(len(self.shown), n)
        # "Reboot"
        self.state = StateStore(self.dir / "state.json")
        self.t = self.make()
        self.t.start()
        self.assertEqual(self.t.mode, "off")
        self.assertEqual(len(self.shown), n)
        self.t.set_enabled(True)
        self.assertEqual(self.t.current_project, "alpha")
        self.assertEqual(len(self.shown), n + 1)

    def test_crash_recovery_closes_segment_at_last_checkpoint(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(300)
        self.state.save()  # simulate the last checkpoint
        checkpoint = self.state["open_segment"]["last_seen"]
        self.clock.t += 7200  # power off
        state = StateStore(self.dir / "state.json")
        self.state = state
        self.t = self.make()
        self.t.start()
        self.assertEqual(self.rows(), [(0, round(checkpoint - 1_000_000), "alpha")])
        self.assertEqual(self.t.mode, "active")  # was on before reboot

    def test_suspend_gap_counts_as_idle(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(100)
        self.clock.t += 3600  # suspended
        self.t.tick(0.0)
        self.assertEqual(self.rows(), [(0, 100, "alpha")])
        self.t.tick(0.0)
        self.assertEqual(self.t.mode, "active")

    def test_no_idle_backend_falls_back_to_unanswered_prompt(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 120, idle=None)
        self.assertEqual(self.t.mode, "idle")
        self.assertEqual(self.rows(), [(0, 900, "alpha")])
        self.t.answer(None)
        self.assertEqual(self.t.mode, "active")
        self.assertEqual(self.t.current_project, "alpha")

    def test_stop_from_prompt(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 30)
        self.t.stop_from_prompt()
        self.assertEqual(self.rows(), [(0, 900, "alpha")])
        self.assertFalse(self.state["enabled"])

    def test_report_totals_include_open_segment(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(600)
        tot = totals(TimeLog(self.cfg.log_path), 0, float("inf"), self.state)
        self.assertAlmostEqual(tot["alpha"], 600, delta=1)


class RankTests(unittest.TestCase):
    def test_rank(self):
        try:
            from timetrack.ui import rank_projects
        except Exception:  # GTK not available
            self.skipTest("GTK not available")
        projects = ["web site", "Admin", "budget", "Website v2"]
        self.assertEqual(rank_projects(projects, "web"), ["web site", "Website v2"])
        self.assertEqual(rank_projects(projects, "d"), ["Admin", "budget"])
        self.assertEqual(rank_projects(projects, "IT"), ["web site", "Website v2"])
        self.assertEqual(rank_projects(projects, ""), projects)


if __name__ == "__main__":
    unittest.main()
