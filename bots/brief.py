"""Chief of Staff bot (free): writes the morning brief from the event map,
open trades, the latest review and your rules. Facts only: no bias.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from common import iso, load, log_run, now_utc, save, settings, today_local


def shift(t: str, minutes: int) -> str:
    d = datetime.strptime(t, "%H:%M") + timedelta(minutes=minutes)
    return d.strftime("%H:%M")


def build(day: str, cfg: dict, research: list, trades: list, reviews: list) -> dict:
    todays = [e for e in research if e.get("date") == day]
    high = [e for e in todays if e.get("impact") == "high"]
    med = [e for e in todays if e.get("impact") == "medium"]
    window = int(cfg.get("noTradeMinutes") or 15)

    if high:
        first = ", ".join(f"{e['title']} at {e['time'] or 'all day'}" for e in high[:3])
        headline = f"{len(high)} high-impact event{'s' if len(high) > 1 else ''}: {first}" + ("…" if len(high) > 3 else "")
    elif med:
        headline = f"No high-impact releases; {len(med)} medium-impact on the calendar"
    else:
        headline = "Quiet calendar: no high- or medium-impact releases for your watchlist"

    summary = []
    if high:
        touched = sorted({i.strip() for e in high for i in e.get("instrument", "").split(",") if i.strip()})
        summary.append("High-impact times (your time zone): " + "; ".join(f"{e['time'] or 'all day'} {e['title']}" for e in high) + ".")
        summary.append("These touch " + ", ".join(touched) + ".")
    if med:
        summary.append("Medium impact: " + "; ".join(f"{e['time'] or 'all day'} {e['title']}" for e in med[:6]) + ("…" if len(med) > 6 else "") + ".")
    holidays = [e for e in todays if "holiday" in e.get("title", "").lower()]
    if holidays:
        summary.append("Holiday or thin liquidity: " + ", ".join(e["title"] for e in holidays) + ".")
    if not summary:
        summary.append("Nothing scheduled that touches your watchlist.")

    open_trades = [t for t in trades if t.get("status") == "open"]
    if open_trades:
        parts = []
        for t in open_trades:
            try:
                dist = abs(float(t["entry"]) - float(t["stop"]))
                parts.append(f"{t['instrument']} {t['direction']} from {t['entry']}, stop {t['stop']} ({dist:g} away)")
            except (KeyError, TypeError, ValueError):
                parts.append(f"{t.get('instrument')} {t.get('direction')} (stop missing)")
        open_risk = "; ".join(parts) + "."
    else:
        open_risk = "No open trades."

    reminders = [
        f"Max risk per trade: {cfg.get('maxRiskPct')}%. Daily stop: {cfg.get('dailyStopR')}R.",
    ]
    for e in high:
        if e.get("time"):
            reminders.append(f"No-trade window {shift(e['time'], -window)}–{shift(e['time'], window)} around {e['title']}.")
    last_fix = next((r["fixes"][0] for r in reviews if r.get("fixes")), None)
    if last_fix:
        reminders.append(f"From your last review: {last_fix}")

    checklist = list(cfg.get("rules", []))[:7] or [
        "Stop set before entry", "Risk within limit", "Reason written down", "Not inside a release window",
    ]
    return {
        "date": day, "headline": headline, "summary": " ".join(summary), "openRisk": open_risk,
        "reminders": reminders, "checklist": checklist, "unverified": [],
        "createdAt": iso(now_utc()), "bot": "chief",
    }


def main() -> None:
    day = today_local()
    brief = build(day, settings(), load("research"), load("trades"), load("reviews"))
    briefs = [b for b in load("briefs") if b.get("date") != day]
    briefs.insert(0, brief)
    save("briefs", briefs[:14])
    log_run("chief", "ok", brief["headline"])


if __name__ == "__main__":
    main()
