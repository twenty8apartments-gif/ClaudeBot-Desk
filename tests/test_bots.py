import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bots"))
import common  # noqa: E402

UTC = timezone.utc


def bar(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c}


class DataDir(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copy(common.ROOT / "data" / "settings.json", self.tmp / "settings.json")
        self._orig = common.DATA
        common.DATA = self.tmp

    def tearDown(self):
        common.DATA = self._orig
        shutil.rmtree(self.tmp)


class TrackerTest(unittest.TestCase):
    def setUp(self):
        import tracker
        self.t = tracker
        self.now = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)

    def idea(self, **kw):
        base = {"instrument": "Gold (XAUUSD)", "direction": "long", "stop": 2630, "target": 2690,
                "horizonDays": 5, "status": "open", "entryPrice": 2650,
                "entryAt": "2026-11-05T06:00:00Z", "lastAt": "2026-11-05T06:00:00Z", "marks": []}
        base.update(kw)
        return base

    def test_pending_stamps_entry(self):
        out = self.t.evaluate({"status": "pending", "direction": "long", "stop": 1, "target": 3},
                              [bar(self.now - timedelta(minutes=30), 2, 2, 2, 2.0)], self.now)
        self.assertEqual(out["status"], "open")
        self.assertEqual(out["entryPrice"], 2.0)

    def test_pending_waits_when_stale(self):
        out = self.t.evaluate({"status": "pending"}, [bar(self.now - timedelta(hours=5), 2, 2, 2, 2)], self.now)
        self.assertEqual(out["status"], "pending")
        self.assertTrue(out["stale"])

    def test_target_hit_by_intrahour_high(self):
        bars = [bar(datetime(2026, 11, 5, 7, tzinfo=UTC), 2650, 2695, 2645, 2660)]
        out = self.t.evaluate(self.idea(), bars, datetime(2026, 11, 5, 7, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "target")
        self.assertEqual(out["exitPrice"], 2690)

    def test_both_touched_assumes_stop(self):
        bars = [bar(datetime(2026, 11, 5, 7, tzinfo=UTC), 2650, 2695, 2625, 2660)]
        out = self.t.evaluate(self.idea(), bars, datetime(2026, 11, 5, 7, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "stopped")

    def test_short_stop(self):
        bars = [bar(datetime(2026, 11, 5, 7, tzinfo=UTC), 1.08, 1.086, 1.079, 1.085)]
        out = self.t.evaluate(self.idea(direction="short", stop=1.085, target=1.07, entryPrice=1.08), bars,
                              datetime(2026, 11, 5, 7, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "stopped")

    def test_old_bars_ignored(self):
        bars = [bar(datetime(2026, 11, 5, 5, tzinfo=UTC), 2650, 2700, 2600, 2650),
                bar(datetime(2026, 11, 5, 7, tzinfo=UTC), 2650, 2660, 2645, 2655)]
        out = self.t.evaluate(self.idea(), bars, datetime(2026, 11, 5, 7, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "open")
        self.assertEqual(out["lastPrice"], 2655)
        self.assertEqual(len(out["marks"]), 1)

    def test_expiry(self):
        bars = [bar(datetime(2026, 11, 12, 7, tzinfo=UTC), 2650, 2660, 2645, 2655)]
        out = self.t.evaluate(self.idea(), bars, datetime(2026, 11, 12, 7, 30, tzinfo=UTC))
        self.assertEqual(out["status"], "expired")
        self.assertEqual(out["exitPrice"], 2655)

    def test_trading_days(self):
        fri = datetime(2026, 11, 6, 12, tzinfo=UTC)
        self.assertEqual(self.t.trading_days_between(fri, fri + timedelta(days=3)), 1)  # Mon only


class JournalTest(unittest.TestCase):
    def test_grades(self):
        import journal
        cfg = {"noTradeMinutes": 15, "maxRiskPct": 1, "dailyStopR": 3}
        research = [{"date": "2026-11-05", "time": "17:30", "impact": "high"}]
        trades = [
            {"date": "2026-11-05", "time": "17:40", "instrument": "ES", "direction": "long",
             "entry": 100, "stop": 99, "exit": 98, "setup": "ORB"},
            {"date": "2026-11-05", "time": "19:00", "instrument": "ES", "direction": "long",
             "entry": 100, "stop": 99, "exit": 101, "notes": "x", "riskPct": 2},
        ]
        r = journal.grade_day("2026-11-05", cfg, trades, research)
        text = " ".join(r["broken"])
        self.assertIn("Release window", text)
        self.assertIn("above your 1% limit", text)
        self.assertEqual(r["grade"], "C")

    def test_daily_stop(self):
        import journal
        cfg = {"dailyStopR": 2}
        trades = [{"date": "d", "time": f"1{i}:00", "instrument": "X", "direction": "long",
                   "entry": 10, "stop": 9, "exit": 9, "notes": "n"} for i in range(3)]
        r = journal.grade_day("d", cfg, trades, [])
        self.assertTrue(any("after hitting the daily stop" in b for b in r["broken"]))


class CommandsTest(DataDir):
    def test_trade_close_delete(self):
        import commands
        msg = commands.handle("[trade] ES long", "date: 2026-11-05\ninstrument: es\ndirection: long\nentry: 5,000\nstop: 4990\nnotes: first line\nsecond line")
        self.assertIn("Saved ES long (open)", msg)
        t = common.load("trades")[0]
        self.assertEqual(t["entry"], 5000.0)
        self.assertEqual(t["notes"], "first line\nsecond line")
        msg = commands.handle(f"[close] {t['id']}", "exit: 5020\npnl: 200")
        self.assertIn("+2.00R", msg)
        self.assertIn("Deleted", commands.handle(f"[delete] {t['id']}", ""))
        self.assertEqual(common.load("trades"), [])

    def test_missing_fields(self):
        import commands
        self.assertIn("missing", commands.handle("[trade]", "instrument: ES"))

    def test_decision_and_resolve(self):
        import commands
        self.assertIn("no-trade", commands.handle("[decision] 2026-11-05", "call: none\nnote: CPI"))
        common.add_blocked("tracker", "Hourly pricing", "x")
        bid = common.load("blocked")[0]["id"]
        self.assertIn("resolved", commands.handle(f"[resolve] {bid}", ""))


class ResearchBriefTest(DataDir):
    def test_events_and_brief(self):
        import brief
        import research
        raw = [
            {"title": "CPI m/m", "country": "USD", "date": "2026-11-05T08:30:00-05:00", "impact": "High", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "German Ifo", "country": "EUR", "date": "2026-11-05T04:00:00-05:00", "impact": "Medium"},
            {"title": "RBA Rate", "country": "AUD", "date": "2026-11-05T22:30:00-05:00", "impact": "High"},
        ]
        ev = research.to_events(raw, common.settings()["watchlist"], ZoneInfo("Indian/Mauritius"))
        self.assertEqual(len(ev), 2)  # AUD not on the watchlist
        cpi = next(e for e in ev if "CPI" in e["title"])
        self.assertEqual((cpi["date"], cpi["time"]), ("2026-11-05", "17:30"))
        self.assertIn("EUR/USD", cpi["instrument"])
        ifo = next(e for e in ev if "Ifo" in e["title"])
        self.assertEqual(ifo["instrument"], "EUR/USD")
        b = brief.build("2026-11-05", common.settings(), ev, [], [])
        self.assertIn("1 high-impact event", b["headline"])
        self.assertTrue(any("17:15–17:45" in r for r in b["reminders"]))


class OpsTest(DataDir):
    def test_main_runs(self):
        import ops
        common.save("trades", [{"date": common.today_local(), "instrument": "ES", "direction": "long",
                                "entry": 1, "stop": 0, "exit": 2, "status": "closed"}])
        ops.main()
        rec = common.load("ops")[0]
        self.assertIn("+1.00R", rec["summary"])
        self.assertTrue(any("missing pnl" in m for m in rec["missing"]))


if __name__ == "__main__":
    unittest.main()
