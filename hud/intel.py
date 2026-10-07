"""
Live intel: pulls the contribution calendar and language mix from the GitHub
GraphQL API and turns it into game stats (level, rank, prestige, streaks).

Falls back to the last good snapshot in hud/intel.json when offline.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "intel.json"

QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { stargazerCount languages(first: 10) { edges { size node { name } } } }
    }
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""

# Call of Duty 4 rank ladder: (first level, title, short form)
RANKS = [
    (1, "Private", "Pvt."), (4, "Private First Class", "PFC"), (7, "Specialist", "Spc."),
    (10, "Corporal", "Cpl."), (13, "Sergeant", "Sgt."), (16, "Staff Sergeant", "SSgt."),
    (19, "Sergeant First Class", "SFC"), (22, "Master Sergeant", "MSgt."), (25, "First Sergeant", "1st Sgt."),
    (28, "Sergeant Major", "SgtMaj."), (31, "Command Sergeant Major", "CSM"), (34, "Second Lieutenant", "2nd Lt."),
    (37, "First Lieutenant", "1st Lt."), (40, "Captain", "Capt."), (43, "Major", "Maj."),
    (46, "Lieutenant Colonel", "Lt. Col."), (49, "Colonel", "Col."), (52, "Brigadier General", "Brig. Gen."),
    (55, "Commander", "Cmdr."),
]
MAX_LEVEL = 55
K = 1.45  # level = 1 + floor(K * sqrt(contributions in the last year))


def _token() -> str | None:
    if os.environ.get("GITHUB_TOKEN"):
        return os.environ["GITHUB_TOKEN"]
    try:  # local runs: borrow the gh CLI's token
        return subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def _fetch(login: str) -> dict:
    token = _token()
    if not token:
        raise RuntimeError("no GitHub token")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"Bearer {token}", "User-Agent": "hud-intel", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    user = body["data"]["user"]
    langs: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    return {
        "created_at": user["createdAt"],
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["repositories"]["nodes"]),
        "languages": dict(sorted(langs.items(), key=lambda kv: -kv[1])),
        "total": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "days": [
            [d["date"], d["contributionCount"]]
            for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
            for d in w["contributionDays"]
        ],
    }


def level_for(total: int) -> int:
    return min(MAX_LEVEL, 1 + int(K * math.sqrt(total)))


def total_for(level: int) -> int:
    """Fewest contributions that reach `level`."""
    return 0 if level <= 1 else math.ceil(((level - 1) / K) ** 2)


def derive(raw: dict, cfg: dict, today: dt.date) -> dict:
    days = [(dt.date.fromisoformat(a), n) for a, n in raw["days"]]
    counts = [n for _, n in days]

    longest = run = 0
    for n in counts:
        run = run + 1 if n else 0
        longest = max(longest, run)
    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts  # no commit yet today is not a break
    for n in reversed(tail):
        if not n:
            break
        current += 1

    joined = dt.date.fromisoformat(raw["created_at"][:10])
    months = (today.year - joined.year) * 12 + today.month - joined.month - (today.day < joined.day)
    total = raw["total"]
    level = level_for(total)
    tier = max(i for i, (lv, _, _) in enumerate(RANKS) if lv <= level)
    lang_total = sum(raw["languages"].values()) or 1
    top_lang, top_bytes = next(iter(raw["languages"].items()), ("", 0))

    # calendar as weeks of 7 (Sunday first); the first week may be partial
    weeks, week = [], []
    for day, n in days:
        if week and day.weekday() == 6:  # Sunday starts a new week
            weeks.append(week)
            week = []
        week.append({"date": day.isoformat(), "count": n, "weekday": (day.weekday() + 1) % 7})
    if week:
        weeks.append(week)

    return {
        "today": today.isoformat(),
        "joined": joined.isoformat(),
        "day_number": (today - joined).days + 1,
        "service_years": months // 12,
        "service_months": months % 12,
        "total": total,
        "active_days": sum(1 for n in counts if n),
        "best_day": max(counts, default=0),
        "longest_streak": longest,
        "current_streak": current,
        "repos": raw["repos"],
        "stars": raw["stars"],
        "top_language": top_lang,
        "top_language_share": round(100 * top_bytes / lang_total),
        "languages": [[k, round(100 * v / lang_total, 1)] for k, v in raw["languages"].items()],
        "level": level,
        "rank": RANKS[tier][1],
        "rank_short": RANKS[tier][2],
        "rank_tier": tier,
        "prestige": max(0, months // 12),
        "xp": total * 100,
        "xp_level_floor": total_for(level) * 100,
        "xp_next": total_for(level + 1) * 100 if level < MAX_LEVEL else total * 100,
        "weeks": weeks,
    }


def load(cfg: dict, offline: bool = False) -> dict:
    raw = None
    if not offline:
        try:
            raw = _fetch(cfg["login"])
            CACHE.write_text(json.dumps(raw, indent=1) + "\n")
        except Exception as e:  # network or auth trouble: last good snapshot
            print(f"intel: live fetch failed ({e}); using cache", file=sys.stderr)
    if raw is None:
        raw = json.loads(CACHE.read_text())
    offset = dt.timedelta(minutes=cfg.get("utc_offset_minutes", 0))
    today = (dt.datetime.now(dt.timezone.utc) + offset).date()
    return derive(raw, cfg, today)
