"""Shared helpers for the free ClaudeBot Desk bots.

All state lives in JSON files under data/. Every bot reads, changes and writes
those files; the GitHub Actions workflow commits them back to the repo.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Default shapes, used when a file does not exist yet.
DEFAULTS = {
    "research": [],
    "briefs": [],
    "ideas": [],
    "trades": [],
    "decisions": [],
    "reviews": [],
    "ops": [],
    "blocked": [],
    "runs": [],
}


def load(name: str):
    path = DATA / f"{name}.json"
    if not path.exists():
        return json.loads(json.dumps(DEFAULTS.get(name, {})))
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save(name: str, value) -> None:
    DATA.mkdir(exist_ok=True)
    path = DATA / f"{name}.json"
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(value, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


def settings() -> dict:
    return load("settings")


def tz() -> ZoneInfo:
    return ZoneInfo(settings().get("timezone") or "Indian/Mauritius")


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def today_local() -> str:
    return now_utc().astimezone(tz()).date().isoformat()


def symbol_for(instrument: str) -> str | None:
    """Map a watchlist name (or a bare symbol) to its price symbol."""
    for w in settings().get("watchlist", []):
        if instrument in (w.get("name"), w.get("symbol")):
            return w.get("symbol")
    return None


def log_run(bot: str, status: str, summary: str, keep_days: int = 30) -> None:
    runs = load("runs")
    runs.insert(0, {"bot": bot, "at": iso(now_utc()), "status": status, "summary": summary})
    cutoff = now_utc() - timedelta(days=keep_days)
    # Keep the tracker's own log short: it runs every hour.
    trimmed, tracker_kept = [], 0
    for r in runs:
        at = parse_iso(r.get("at"))
        if at and at < cutoff:
            continue
        if r.get("bot") == "tracker":
            tracker_kept += 1
            if tracker_kept > 72:
                continue
        trimmed.append(r)
    save("runs", trimmed)


def add_blocked(bot: str, task: str, reason: str) -> None:
    blocked = load("blocked")
    for b in blocked:
        if b.get("bot") == bot and b.get("task") == task and b.get("status") != "resolved":
            return  # already flagged; don't stack duplicates
    blocked.insert(0, {
        "id": f"{bot}-{now_utc().strftime('%Y%m%d%H%M%S')}",
        "bot": bot, "task": task, "reason": reason,
        "status": "open", "createdAt": iso(now_utc()),
    })
    save("blocked", blocked)


def trade_r(t: dict) -> float | None:
    """R multiple of a logged trade: (exit - entry) / |entry - stop|, sign-flipped for shorts."""
    try:
        e, s, x = float(t["entry"]), float(t["stop"]), t.get("exit")
        if x in (None, ""):
            return None
        x = float(x)
    except (KeyError, TypeError, ValueError):
        return None
    risk = abs(e - s)
    if not risk:
        return None
    return (x - e) / risk * (-1 if t.get("direction") == "short" else 1)
