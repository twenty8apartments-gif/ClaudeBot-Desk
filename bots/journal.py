"""Journal bot (free): grades each day's PROCESS against your rules with plain
checks. It never comments on what to trade next.
"""
from __future__ import annotations

from datetime import datetime

from common import iso, load, log_run, now_utc, save, settings, today_local, trade_r


def minutes(t: str | None) -> int | None:
    try:
        h, m = map(int, (t or "").split(":"))
        return h * 60 + m
    except ValueError:
        return None


def grade_day(day: str, cfg: dict, trades: list, research: list) -> dict | None:
    todays = sorted([t for t in trades if t.get("date") == day], key=lambda t: t.get("time") or "99:99")
    if not todays:
        return None
    window = int(cfg.get("noTradeMinutes") or 15)
    max_risk = cfg.get("maxRiskPct")
    daily_stop = float(cfg.get("dailyStopR") or 0)
    releases = [minutes(e.get("time")) for e in research
                if e.get("date") == day and e.get("impact") == "high" and e.get("time")]
    releases = [r for r in releases if r is not None]

    kept, broken, unknown = [], [], []
    running_r, stop_hit_at = 0.0, None
    for t in todays:
        label = f"{t.get('instrument')} {t.get('direction')} {t.get('time') or ''}".strip()
        tm = minutes(t.get("time"))
        if tm is None:
            unknown.append(f"{label}: no entry time, so the release-window rule can't be checked")
        elif any(abs(tm - r) <= window for r in releases):
            broken.append(f"Release window: {label} was within {window} min of a high-impact release")
        elif releases:
            kept.append(f"Release window kept on {label}")
        if t.get("stop") in (None, ""):
            broken.append(f"No stop recorded on {label}")
        else:
            kept.append(f"Stop set on {label}")
        if not (t.get("notes") or t.get("setup")):
            broken.append(f"No written reason on {label}")
        if max_risk is not None and t.get("riskPct") not in (None, ""):
            if float(t["riskPct"]) > float(max_risk):
                broken.append(f"Risk {t['riskPct']}% on {label}, above your {max_risk}% limit")
            else:
                kept.append(f"Risk within limit on {label}")
        if stop_hit_at is not None:
            broken.append(f"Traded after hitting the daily stop: {label}")
        r = trade_r(t)
        if r is not None:
            running_r += r
            if daily_stop and running_r <= -daily_stop and stop_hit_at is None:
                stop_hit_at = label
        if t.get("followedPlan") == "no":
            broken.append(f"You marked {label} as not following your plan")

    closed = [trade_r(t) for t in todays if trade_r(t) is not None]
    grade = "ABCDF"[min(len(broken), 4)]
    summary = (f"{len(todays)} trade{'s' if len(todays) != 1 else ''}, {len(closed)} closed for {running_r:+.2f}R. "
               f"{len(broken)} rule break{'s' if len(broken) != 1 else ''}, {len(kept)} checks passed.")
    if stop_hit_at:
        summary += f" Daily stop of {daily_stop:g}R reached on {stop_hit_at}."
    if unknown:
        summary += " " + unknown[0] + "."
    if broken:
        first = broken[0].split(":")[0]
        fix = f"Tomorrow, focus on: {first.lower()}."
    else:
        fix = "Keep doing exactly this."
    return {"id": f"daily-{day}", "period": "Daily", "date": day, "grade": grade, "summary": summary,
            "kept": kept[:8], "broken": broken, "fixes": [fix], "createdAt": iso(now_utc()), "bot": "journal"}


def main() -> None:
    day = today_local()
    review = grade_day(day, settings(), load("trades"), load("research"))
    if not review:
        log_run("journal", "ok", "No trades logged")
        return
    reviews = [r for r in load("reviews") if r.get("id") != review["id"]]
    reviews.insert(0, review)
    save("reviews", reviews[:60])
    log_run("journal", "ok", f"Grade {review['grade']}: {review['summary']}")


if __name__ == "__main__":
    main()
