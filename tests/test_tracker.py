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
        self.cfg = Config(prompt_interval_minutes=15, response_timeout_seconds=60,
                          offer_to_log_away_time=True, log_file=str(self.dir / "log.csv"))
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

    def advance(self, seconds, step=5):
        """Advance time, ticking every `step` seconds."""
        end = self.clock.t + seconds
        while self.clock.t < end:
            self.clock.t = min(end, self.clock.t + step)
            self.t.tick()

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

    def test_prompt_answered_within_timeout_keeps_previous_project(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 50)  # prompt open 50 s, still within the 60 s timeout
        self.assertEqual(self.t.current_project, "alpha")
        self.assertEqual(self.t.mode, "active")
        self.t.answer(None)  # Enter on the highlighted previous project / Esc
        self.assertEqual(self.t.current_project, "alpha")
        self.assertEqual(self.rows(), [])

    def test_unanswered_prompt_ends_segment_at_prompt_time(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 600)  # nobody answers for 10 minutes
        self.assertEqual(self.t.mode, "away")
        self.assertEqual(self.rows(), [(0, 900, "alpha")])
        self.assertIsNone(self.t.current_project)
        # The prompt was re-shown offering to log the away time; no new prompts meanwhile.
        self.assertEqual(round(self.shown[-1].away[0] - 1_000_000), 900)
        n = len(self.shown)
        self.advance(3600)
        self.assertEqual(len(self.shown), n)
        # User answers: new entry starts now, away time logged to "meeting".
        answered = round(self.clock.t - 1_000_000)
        self.t.answer("alpha", away_project="meeting")
        self.assertEqual(self.t.mode, "active")
        self.assertIn((900, answered, "meeting"), self.rows())
        self.assertEqual(round(self.state["open_segment"]["start"] - 1_000_000), answered)
        self.assertEqual(self.t.projects()[:2], ["alpha", "meeting"])

    def test_unanswered_without_logging_away_time(self):
        self.cfg.offer_to_log_away_time = False
        self.t.start()
        self.t.answer("alpha")
        self.advance(15 * 60 + 120)
        self.assertIsNone(self.shown[-1].away)
        self.t.answer(None)
        self.assertEqual(self.rows(), [(0, 900, "alpha")])
        self.assertEqual(self.t.current_project, "alpha")

    def test_startup_prompt_unanswered(self):
        self.t.start()
        self.t.answer("alpha")
        self.t.shutdown()
        self.clock.t += 3600
        self.t = self.make()
        self.t.start()  # login: keeps "alpha" going while the prompt is open
        self.advance(120)
        self.assertEqual(self.t.mode, "away")
        # "alpha" ended when the login prompt appeared, so nothing was recorded.
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.shown[-1].default, "alpha")

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

    def test_suspend_gap_counts_as_away(self):
        self.t.start()
        self.t.answer("alpha")
        self.advance(100)
        self.clock.t += 3600  # suspended
        self.t.tick()
        self.assertEqual(self.rows(), [(0, 100, "alpha")])
        self.assertEqual(self.t.mode, "away")
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
