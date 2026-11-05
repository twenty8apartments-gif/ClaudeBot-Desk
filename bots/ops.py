"""Tax & Ops bot (free): weekly records and totals from your journal.
Records only: not tax advice and not a filing.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from common import iso, load, log_run, now_utc, save, settings, today_local, trade_r


def totals(trades: list, start: str, end: str, ccy: str) -> str:
    rows = [t for t in trades if start <= (t.get("date") or "") <= end]
    closed = [t for t in rows if trade_r(t) is not None]
    rs = [trade_r(t) for t in closed]
    wins = sum(1 for r in rs if r > 0)
    pnl_known = [float(t["pnl"]) for t in closed if t.get("pnl") not in (None, "")]
    by = Counter(t.get("instrument") for t in rows)
    s = (f"{len(rows)} trades ({len(closed)} closed, {len(rows) - len(closed)} open), "
         f"{wins} wins / {len(closed) - wins} losses, net {sum(rs):+.2f}R")
    if pnl_known:
        s += f", P&L {sum(pnl_known):+.2f} {ccy}"
        missing = len(closed) - len(pnl_known)
        if missing:
            s += f" ({missing} closed without P&L)"
    if by:
        s += "; by instrument: " + ", ".join(f"{k} {v}" for k, v in by.most_common())
    return s


def gaps(trades: list, today: date) -> list:
    out, seen = [], set()
    for t in trades:
        label = f"{t.get('date')} {t.get('instrument')}"
        key = (t.get("date"), t.get("instrument"), t.get("entry"), t.get("stop"))
        if key in seen:
            out.append(f"Possible duplicate: {label}")
        seen.add(key)
        if t.get("status") == "closed":
            for f in ("exit", "pnl", "setup", "notes"):
                if t.get(f) in (None, ""):
                    out.append(f"{label}: missing {f}")
        elif t.get("status") == "open":
            try:
                if (today - date.fromisoformat(t["date"])).days > 5:
                    out.append(f"{label}: open for more than 5 days. Still open?")
            except (KeyError, ValueError):
                pass
    return out


def main() -> None:
    cfg = settings()
    ccy = cfg.get("currency", "")
    today = date.fromisoformat(today_local())
    # Week just ended: previous Monday..Sunday relative to this run (runs on Sunday).
    week_end = today if today.weekday() == 6 else today - timedelta(days=today.weekday() + 1)
    week_start = week_end - timedelta(days=6)
    label = f"{week_start.isocalendar()[0]}-W{week_start.isocalendar()[1]:02d}"
    trades = load("trades")
    summary = ("Week: " + totals(trades, week_start.isoformat(), week_end.isoformat(), ccy) + ". "
               "Month to date: " + totals(trades, today.replace(day=1).isoformat(), today.isoformat(), ccy) + ". "
               "Year to date: " + totals(trades, today.replace(month=1, day=1).isoformat(), today.isoformat(), ccy) + ".")
    rec = {"id": f"week-{label}", "period": f"Week {label} · MTD · YTD", "summary": summary,
           "missing": gaps(trades, today), "createdAt": iso(now_utc()), "bot": "ops"}
    ops = [o for o in load("ops") if o.get("id") != rec["id"]]
    ops.insert(0, rec)
    save("ops", ops[:26])

    # Housekeeping: drop resolved blocked items older than 30 days.
    cutoff = iso(now_utc() - timedelta(days=30))
    save("blocked", [b for b in load("blocked") if not (b.get("status") == "resolved" and b.get("createdAt", "") < cutoff)])
    log_run("ops", "ok", f"Records for {label}: {len(rec['missing'])} gaps")


if __name__ == "__main__":
    main()
