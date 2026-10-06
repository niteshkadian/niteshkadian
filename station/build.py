#!/usr/bin/env python3
"""
Builds every image on the profile: the departure board (live), the network
map, the route cards, the section signs and the ticket.

    python station/build.py             # live data from the GitHub API
    python station/build.py --offline   # rebuild from station/cache.json

Content lives in station/routes.json. Standard library only. Output is
deterministic, so the scheduled workflow only commits when something changed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import random
import sys
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATION = ROOT / "station"
ASSETS = ROOT / "assets"

SANS = "'Helvetica Neue', Helvetica, Arial, 'Nimbus Sans', 'Liberation Sans', sans-serif"
MONO = "ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace"
DEVA = "'Kohinoor Devanagari', 'Devanagari Sangam MN', 'Nirmala UI', 'Noto Sans Devanagari', Mangal, sans-serif"

# key: (name, line colour, bullet text colour)
LINES = {
    "W": ("Web", "#E8432E", "#FFFFFF"),
    "A": ("AI & Data", "#2F6FDE", "#FFFFFF"),
    "S": ("Systems", "#1E9E5A", "#FFFFFF"),
    "B": ("Backend", "#F5B800", "#141414"),
    "M": ("Mobile", "#F47B20", "#FFFFFF"),
    "D": ("Design", "#A65CC7", "#FFFFFF"),
}

THEMES = {
    "light": dict(bg="#F7F5F0", ink="#141414", sub="#6E6A62", rule="#E0DBD0", pearl="#FFFFFF"),
    "dark": dict(bg="#0E1116", ink="#EEEBE4", sub="#8C919A", rule="#262C35", pearl="#F4F1EA"),
}


def tx(s) -> str:
    return escape(str(s), quote=False)


def at(s) -> str:
    return escape(str(s), quote=True)


def svg(w, h, title, style, body) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{at(title)}"><title>{tx(title)}</title>'
        f"<style>{style}</style>{body}</svg>\n"
    )


def bullet(x, y, key, r=14) -> str:
    _, color, fg = LINES[key]
    fs = r * 1.12
    return (
        f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>'
        f'<text x="{x}" y="{y + fs * 0.36:.1f}" text-anchor="middle" font-size="{fs:.1f}" '
        f'font-weight="700" fill="{fg}" class="sans">{key}</text>'
    )


# ---------------------------------------------------------------------------
# data
# ---------------------------------------------------------------------------

def fetch_repos(user: str) -> list[dict]:
    url = f"https://api.github.com/users/{user}/repos?per_page=100&type=owner&sort=pushed"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "departures-board"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.load(r)


def load_repos(cfg, offline: bool) -> list[dict]:
    cache = STATION / "cache.json"
    keep = ("name", "pushed_at", "language", "description")
    if not offline:
        try:
            excluded = set(cfg["board"]["exclude"])
            repos = [
                {k: r.get(k) for k in keep}
                for r in fetch_repos(cfg["user"])
                # the profile repo itself is excluded, or every bot commit would
                # change its pushed_at and the board would never settle
                if not r["fork"] and not r["archived"] and r["name"] not in excluded
            ]
            repos.sort(key=lambda r: r["pushed_at"], reverse=True)
            cache.write_text(json.dumps(repos, indent=2) + "\n")
            return repos
        except Exception as e:  # network trouble: fall back to the last good snapshot
            print(f"GitHub API unavailable ({e}); using cache", file=sys.stderr)
    return json.loads(cache.read_text()) if cache.exists() else []


def guess_line(language: str | None) -> str:
    lang = (language or "").lower()
    if lang in ("typescript", "javascript", "html", "css", "vue", "svelte"):
        return "W"
    if lang in ("python", "jupyter notebook", "r"):
        return "A"
    if lang in ("kotlin", "dart", "swift", "java"):
        return "M"
    if lang in ("c", "c++", "rust", "assembly", "verilog", "hack", "go"):
        return "S"
    return "B"


def remark(age: dt.timedelta) -> str:
    if age < dt.timedelta(days=1):
        return "BOARDING"
    if age < dt.timedelta(days=7):
        return "ON TIME"
    if age < dt.timedelta(days=30):
        return "DEPARTED"
    return "IN DEPOT"


def departures(cfg, repos, now) -> list[dict]:
    board = cfg["board"]
    offset = dt.timedelta(minutes=cfg["timezone"]["offset_minutes"])
    rows = [dict(p) for p in board["pinned"]]
    for r in repos:
        meta = board["repos"].get(r["name"], {})
        if meta.get("hide"):
            continue
        pushed = dt.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
        rows.append(
            dict(
                time=(pushed + offset).strftime("%H:%M"),
                line=meta.get("line") or guess_line(r.get("language")),
                dest=meta.get("dest") or r["name"].replace("-", " ").replace("_", " "),
                via=meta.get("via") or r.get("description") or r.get("language") or "",
                remark=meta.get("remark") or remark(now - pushed),
            )
        )
    return rows[: board["rows"]]


# ---------------------------------------------------------------------------
# departure board
# ---------------------------------------------------------------------------

FLAPS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
# (tile w, tile h, pitch, font size)
TILE = {"n": (46, 64, 50, 44), "g": (20, 28, 22, 19), "r": (22, 32, 24, 22)}
REMARK_TONE = {"BOARDING": "amber pulse", "ON DUTY": "amber", "ON TIME": "ink", "DEPARTED": "ink", "IN DEPOT": "dim"}


class Flaps:
    """Split-flap tiles. Each tile riffles through a few random characters
    before settling on its own, staggered so the board fills left to right."""

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.parts: list[str] = []

    def word(self, x, y, text, n, size, start, stagger, step, spins, tone="ink"):
        w, h, pitch, fs = TILE[size]
        base = h / 2 + fs * 0.36
        for i, ch in enumerate(text.upper()[:n].ljust(n)):
            t0 = start + i * stagger
            k = spins + self.rng.randint(-1, 1) if ch != " " else self.rng.randint(0, 1)
            glyphs = []
            for j in range(max(k, 0)):
                c = self.rng.choice(FLAPS)
                glyphs.append(
                    f'<text class="c" x="{w / 2}" y="{base:.1f}" '
                    f'style="animation-duration:{step:.2f}s;animation-delay:{t0 + j * step:.2f}s">{c}</text>'
                )
            done = t0 + max(k, 0) * step
            if ch != " ":
                delays = f"{done:.2f}s,{done + 0.4:.2f}s" if "pulse" in tone else f"{done:.2f}s"
                glyphs.append(
                    f'<text class="f {tone}" x="{w / 2}" y="{base:.1f}" '
                    f'style="animation-delay:{delays}">{tx(ch)}</text>'
                )
            self.parts.append(
                f'<g class="t {size}" transform="translate({x + i * pitch} {y})">'
                f'<use href="#b{size}"/>{"".join(glyphs)}<use href="#s{size}"/></g>'
            )
        return start + n * stagger + spins * step


def build_board(cfg, rows) -> str:
    board = cfg["board"]
    seed = hashlib.sha1(json.dumps([board, rows], sort_keys=True).encode()).hexdigest()
    flaps = Flaps(random.Random(seed))
    W, H = 1000, 648

    defs = [
        '<linearGradient id="housing" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#242424"/>'
        '<stop offset="1" stop-color="#121212"/></linearGradient>',
        '<linearGradient id="tg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2C2C2C"/>'
        '<stop offset=".499" stop-color="#232323"/><stop offset=".5" stop-color="#191919"/>'
        '<stop offset="1" stop-color="#131313"/></linearGradient>',
        '<linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".055"/>'
        '<stop offset=".45" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        '<pattern id="led" width="3" height="3" patternUnits="userSpaceOnUse">'
        '<rect x="2" width="1" height="3" fill="#050505"/><rect y="2" width="3" height="1" fill="#050505"/></pattern>',
        '<filter id="glow" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="1.6" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '<clipPath id="tickclip"><rect x="48" y="586" width="904" height="34"/></clipPath>',
    ]
    for k, (w, h, _, _) in TILE.items():
        defs.append(
            f'<g id="b{k}"><rect width="{w}" height="{h}" rx="3" fill="url(#tg)" stroke="#000" stroke-width=".8"/></g>'
            f'<g id="s{k}"><rect y="{h / 2 - 0.8}" width="{w}" height="1.6" fill="#050505"/>'
            f'<rect y="{h / 2 + 0.8}" width="{w}" height=".6" fill="#fff" opacity=".05"/></g>'
        )

    body = [
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="22" fill="url(#housing)" stroke="#2E2E2E" stroke-width="1.5"/>',
        f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" rx="14" fill="#0A0A0A" stroke="#000" stroke-width="2"/>',
    ]
    for sx, sy in ((26, 26), (W - 26, 26), (26, H - 26), (W - 26, H - 26)):
        body.append(
            f'<circle cx="{sx}" cy="{sy}" r="3.4" fill="#2A2A2A" stroke="#000" stroke-width=".8"/>'
            f'<path d="M{sx - 2} {sy + 2}L{sx + 2} {sy - 2}" stroke="#0C0C0C" stroke-width="1"/>'
        )

    # header
    body.append('<text x="40" y="58" class="sans hdr">DEPARTURES</text>')
    body.append('<rect x="186" y="49" width="5" height="5" fill="#FFB547"/>')
    body.append('<text x="202" y="59" class="deva">प्रस्थान</text>')
    body.append('<circle class="live" cx="842" cy="53.5" r="4.5" fill="#5BE37D"/>')
    body.append('<text x="960" y="58" text-anchor="end" class="sans cap">LIVE · GITHUB</text>')

    # name and tagline
    name, tag = board["name"], board["tagline"]
    nx = (W - (len(name) * TILE["n"][2] - (TILE["n"][2] - TILE["n"][0]))) / 2
    gx = (W - (len(tag) * TILE["g"][2] - (TILE["g"][2] - TILE["g"][0]))) / 2
    flaps.word(nx, 86, name, len(name), "n", 0.25, 0.07, 0.075, 6)
    flaps.word(gx, 164, tag, len(tag), "g", 0.75, 0.03, 0.06, 3)

    body.append('<rect x="40" y="213" width="920" height="1" fill="#242424"/>')
    for x, label in ((40, "TIME"), (172, "LINE"), (215, "DESTINATION"), (746, "REMARKS")):
        body.append(f'<text x="{x}" y="240" class="sans col fd" style="animation-delay:1.1s">{label}</text>')
    body.append('<rect x="40" y="249" width="920" height="1" fill="#1C1C1C"/>')

    # rows
    for i in range(board["rows"]):
        y = 258 + i * 64
        row = rows[i] if i < len(rows) else None
        t0 = 1.25 + i * 0.22
        if row:
            flaps.word(40, y, row["time"], 5, "r", t0, 0.03, 0.06, 3)
            body.append(f'<g class="fd" style="animation-delay:{t0:.2f}s">{bullet(186, y + 16, row["line"], 13)}</g>')
            flaps.word(215, y, row["dest"], 18, "r", t0 + 0.1, 0.025, 0.06, 3)
            tone = REMARK_TONE.get(row["remark"], "ink")
            flaps.word(746, y, row["remark"], 9, "r", t0 + 0.35, 0.03, 0.06, 4, tone)
            body.append(
                f'<text x="215" y="{y + 49}" class="sans via fd" style="animation-delay:{t0 + 0.9:.2f}s">'
                f"{tx(row['via'])}</text>"
            )
        else:
            flaps.word(40, y, "", 5, "r", t0, 0.03, 0.06, 0)
            flaps.word(215, y, "", 18, "r", t0, 0.025, 0.06, 0)
            flaps.word(746, y, "", 9, "r", t0, 0.03, 0.06, 0)
        if i < board["rows"] - 1:
            body.append(f'<rect x="40" y="{y + 58}" width="920" height="1" fill="#161616"/>')
    body.extend(flaps.parts)

    # ticker: dot-matrix LED strip that scrolls forever
    msg = "   ✦   ".join(a.upper() for a in board["announcements"]) + "   ✦   "
    cw = 9.0
    length = round(len(msg) * cw, 1)
    span = lambda x: (
        f'<text x="{x}" y="609" class="mono tick" textLength="{length}" lengthAdjust="spacing">{tx(msg)}</text>'
    )
    body.append('<rect x="40" y="586" width="920" height="34" rx="6" fill="#060606" stroke="#1C1C1C"/>')
    body.append(
        f'<g clip-path="url(#tickclip)"><g filter="url(#glow)"><g class="tk">{span(48)}{span(48 + length)}</g></g>'
        '<rect x="40" y="586" width="920" height="34" fill="url(#led)" opacity=".75"/></g>'
    )
    body.append(f'<rect x="14" y="14" width="{W - 28}" height="{H - 28}" rx="14" fill="url(#glass)" pointer-events="none"/>')

    style = f"""
.sans{{font-family:{SANS}}}.mono{{font-family:{MONO}}}
.deva{{font-family:{DEVA};font-size:16px;fill:#8F8A80}}
.hdr{{font-size:15px;font-weight:700;letter-spacing:4px;fill:#F4F1E8}}
.cap{{font-size:11px;font-weight:700;letter-spacing:2.5px;fill:#8F8A80}}
.col{{font-size:11px;font-weight:700;letter-spacing:2.2px;fill:#6F6A61}}
.via{{font-size:13.5px;fill:#8F8A80;letter-spacing:.3px}}
.tick{{font-size:15px;font-weight:700;fill:#FFB547}}
.t text{{font-family:{SANS};font-weight:700;text-anchor:middle;fill:#F4F1E8}}
.t.n text{{font-size:44px}}.t.g text{{font-size:19px}}.t.r text{{font-size:22px}}
.t text.amber{{fill:#FFB547}}.t text.dim{{fill:#8D887C}}
.c{{opacity:0;animation:flash linear}}
.f{{animation:hold .01s linear backwards}}
.f.pulse{{animation:hold .01s linear backwards,pulse 1.8s ease-in-out infinite}}
.fd{{animation:fade .6s ease backwards}}
.live{{animation:pulse 1.6s ease-in-out infinite}}
.tk{{animation:tk {length / 55:.1f}s linear infinite}}
@keyframes flash{{from,to{{opacity:1}}}}@keyframes hold{{from,to{{opacity:0}}}}@keyframes fade{{from{{opacity:0}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
@keyframes tk{{to{{transform:translateX(-{length}px)}}}}
@media (prefers-reduced-motion:reduce){{.c{{display:none}}.f,.fd,.tk,.live{{animation:none}}}}
"""
    title = f"Departure board for {board['name'].title()}: " + "; ".join(
        f"{r['dest'].title()} ({r['remark'].lower()})" for r in rows
    )
    return svg(W, H, title, style, f"<defs>{''.join(defs)}</defs>{''.join(body)}")


# ---------------------------------------------------------------------------
# network map
# ---------------------------------------------------------------------------
# station: (x, y, label, kind, label position)
#   kind: s station, x interchange, t terminus, f future, tf future terminus
#   position: n above, s below, e right, w left, se below-right
NETWORK = {
    "W": dict(
        path=[(120, 310), (230, 200), (905, 200)],
        stations=[
            (288, 200, "HTML/CSS", "s", "n"), (368, 200, "JavaScript", "s", "n"),
            (440, 200, "React", "x", "s"), (520, 200, "Tailwind", "x", "n"),
            (600, 200, "TypeScript", "s", "n"), (680, 200, "Next.js", "x", "se"),
            (760, 200, "Turborepo", "s", "n"), (860, 200, "Prime Esports", "t", "n"),
        ],
        bullet=(905, 200),
    ),
    "A": dict(
        path=[(120, 310), (850, 310)],
        stations=[
            (210, 310, "Python", "s", "n"), (290, 310, "NumPy", "s", "n"), (370, 310, "Pandas", "s", "n"),
            (450, 310, "Matplotlib", "s", "n"), (590, 310, "PyTorch", "s", "n"),
            (680, 310, "FastAPI", "x", "se"), (800, 310, "Nirikshan AI", "t", "n"),
        ],
        bullet=(850, 310),
    ),
    "S": dict(
        path=[(120, 310), (230, 420), (430, 420)],
        future=[(430, 420), (945, 420)],
        stations=[
            (270, 420, "NAND", "s", "s"), (350, 420, "Logic gates", "s", "s"), (430, 420, "Adders", "s", "s"),
            (600, 420, "ALU", "f", "s"), (760, 420, "CPU", "f", "s"), (840, 420, "Compiler", "f", "s"),
            (900, 420, "OS", "tf", "s"),
        ],
        bullet=(945, 420),
    ),
    "M": dict(
        path=[(145, 90), (330, 90), (440, 200)],
        stations=[
            (200, 90, "Kotlin", "s", "n"), (265, 90, "Dart", "s", "n"), (330, 90, "Flutter", "s", "n"),
            (385, 145, "React Native", "s", "w"),
        ],
        bullet=(145, 90),
    ),
    "D": dict(
        path=[(520, 200), (520, 578)],
        stations=[
            (520, 258, "Figma", "s", "w"), (520, 365, "Framer", "s", "w"),
            (520, 478, "Photoshop", "s", "w"), (520, 535, "Blender", "s", "w"),
        ],
        bullet=(520, 578),
        bridge=True,
    ),
    "B": dict(
        path=[(680, 56), (680, 532)],
        stations=[
            (680, 100, "Node.js", "s", "e"), (680, 148, "Express", "s", "e"), (680, 255, "Prisma", "s", "e"),
            (680, 365, "PostgreSQL", "s", "e"), (680, 478, "Supabase", "s", "e"), (680, 532, "Docker", "s", "e"),
        ],
        bullet=(680, 56),
        bridge=True,
    ),
}


def pts(path) -> str:
    return " ".join(f"{x},{y}" for x, y in path)


def path_len(path) -> float:
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def build_map(theme: str) -> str:
    c = THEMES[theme]
    W, H = 1000, 620
    out = [f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="{c["bg"]}" stroke="{c["rule"]}"/>']
    lw = 9

    # flat lines first, then the vertical ones bridge over them
    for key in ("W", "A", "S", "M"):
        ln, color = NETWORK[key], LINES[key][1]
        out.append(f'<polyline points="{pts(ln["path"])}" class="ln" stroke="{color}"/>')
        if "future" in ln:
            out.append(
                f'<polyline points="{pts(ln["future"])}" class="ln" stroke="{color}" stroke-dasharray="14 9" opacity=".55"/>'
            )
    for key in ("D", "B"):
        ln, color = NETWORK[key], LINES[key][1]
        out.append(f'<polyline points="{pts(ln["path"])}" class="ln" stroke="{c["bg"]}" stroke-width="{lw + 8}"/>')
        out.append(f'<polyline points="{pts(ln["path"])}" class="ln" stroke="{color}"/>')

    # one train per line, running the built track on a loop
    for n, (key, ln) in enumerate(NETWORK.items()):
        d = "M" + " L".join(f"{x} {y}" for x, y in ln["path"])
        dur = path_len(ln["path"]) / 62
        out.append(
            f'<g class="train"><rect x="-9" y="-4" width="18" height="8" rx="4" fill="{c["pearl"]}" '
            f'stroke="{LINES[key][1]}" stroke-width="2"/>'
            f'<animateMotion dur="{dur:.1f}s" begin="{n * 0.9:.1f}s" repeatCount="indefinite" rotate="auto" path="{d}"/></g>'
        )

    # stations and labels
    labels = []
    for key, ln in NETWORK.items():
        color = LINES[key][1]
        for x, y, label, kind, pos in ln["stations"]:
            if kind == "s":
                out.append(f'<circle cx="{x}" cy="{y}" r="3.6" fill="{c["pearl"]}"/>')
            elif kind == "x":
                out.append(f'<circle cx="{x}" cy="{y}" r="8.5" fill="{c["pearl"]}" stroke="#141414" stroke-width="3"/>')
            elif kind == "t":
                out.append(f'<circle cx="{x}" cy="{y}" r="8.5" fill="{c["pearl"]}" stroke="{color}" stroke-width="3.5"/>')
            else:  # future stations are drawn hollow
                out.append(
                    f'<circle cx="{x}" cy="{y}" r="{7 if kind == "tf" else 5}" fill="{c["bg"]}" '
                    f'stroke="{color}" stroke-width="2.5"/>'
                )
            terminus = kind in ("t", "tf")
            text = label.upper() if terminus else label
            cls = "lbl term" if terminus else ("lbl fut" if kind == "f" else "lbl")
            dx, dy, anchor = {
                "n": (0, -16, "middle"), "s": (0, 26, "middle"), "e": (16, 4.5, "start"),
                "w": (-16, 4.5, "end"), "se": (16, 24, "start"),
            }[pos]
            if terminus and pos == "n":
                dy = -18
            labels.append(
                f'<text x="{x + dx}" y="{y + dy}" text-anchor="{anchor}" class="{cls}">{tx(text)}</text>'
            )
    out.extend(labels)

    # origin roundel: every line starts at zero
    out.append(
        f'<circle cx="120" cy="310" r="25" fill="{c["bg"]}" stroke="{c["ink"]}" stroke-width="4"/>'
        f'<text x="120" y="320" text-anchor="middle" class="zero">0</text>'
        f'<text x="104" y="358" text-anchor="middle" class="eyebrow">ORIGIN</text>'
    )
    for key, ln in NETWORK.items():
        out.append(bullet(*ln["bullet"], key))

    # legend
    out.append('<text x="770" y="42" class="eyebrow">LINES</text>')
    for i, key in enumerate(LINES):
        lx, ly = 780 + (i // 3) * 100, 64 + (i % 3) * 24
        out.append(bullet(lx, ly, key, 10))
        out.append(f'<text x="{lx + 17}" y="{ly + 4.5}" class="lgd">{tx(LINES[key][0])}</text>')
    out.append(
        f'<line x1="772" y1="138" x2="790" y2="138" stroke="{c["sub"]}" stroke-width="5" stroke-dasharray="6 4" opacity=".8"/>'
        '<text x="797" y="142" class="lgd sm">Under construction</text>'
        f'<circle cx="780" cy="158" r="6" fill="{c["pearl"]}" stroke="#141414" stroke-width="2.4"/>'
        '<text x="797" y="162" class="lgd sm">Interchange</text>'
    )

    # title block
    out.append(
        '<text x="40" y="508" class="eyebrow">NETWORK MAP · NITESH KADIAN</text>'
        '<text x="38" y="543" class="title">Every line starts at zero.</text>'
        '<text x="40" y="569" class="note">Lines are disciplines. Stations are tools I build with.</text>'
        '<text x="40" y="589" class="note">Dashed track is still under construction.</text>'
        f'<text x="960" y="589" text-anchor="end" class="eyebrow">DIAGRAM NOT TO SCALE</text>'
    )

    style = f"""
text{{font-family:{SANS}}}
.ln{{fill:none;stroke-width:{lw};stroke-linecap:round;stroke-linejoin:round}}
.lbl{{font-size:13.5px;font-weight:700;fill:{c["ink"]}}}
.lbl.fut{{fill:{c["sub"]};font-weight:600}}
.lbl.term{{font-size:12.5px;letter-spacing:1.2px}}
.zero{{font-size:28px;font-weight:700;fill:{c["ink"]}}}
.eyebrow{{font-size:10.5px;font-weight:700;letter-spacing:2.6px;fill:{c["sub"]}}}
.lgd{{font-size:13px;font-weight:700;fill:{c["ink"]}}}.lgd.sm{{font-size:11.5px;fill:{c["sub"]};font-weight:600}}
.title{{font-size:28px;font-weight:700;letter-spacing:-.5px;fill:{c["ink"]}}}
.note{{font-size:14px;fill:{c["sub"]}}}
@media (prefers-reduced-motion:reduce){{.train{{display:none}}}}
"""
    return svg(W, H, "Network map: six lines (Web, AI & Data, Systems, Backend, Mobile, Design), every one starting at zero", style, "".join(out))


# ---------------------------------------------------------------------------
# route cards
# ---------------------------------------------------------------------------

def build_card(route, theme: str) -> str:
    c = THEMES[theme]
    W, H = 500, 250
    key = route["line"]
    lname, color, _ = LINES[key]
    out = [
        f'<clipPath id="card"><rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16"/></clipPath>'
        '<clipPath id="hz"><rect width="12" height="12" rx="2.5"/></clipPath>',
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="16" fill="{c["bg"]}" stroke="{c["rule"]}"/>',
        f'<rect x="0" y="0" width="7" height="{H}" fill="{color}" clip-path="url(#card)"/>',
    ]
    out.append(bullet(48, 50, key, 16))
    out.append(f'<text x="76" y="40" class="eyebrow">{key} LINE · {tx(lname.upper())}</text>')
    out.append(f'<text x="75" y="64" class="name">{tx(route["name"])}</text>')

    # status pill
    building = route["status"] == "under construction"
    label = route["status"].upper()
    tw = len(label) * 8.1
    pw = tw + 44
    px = W - 24 - pw
    out.append(f'<rect x="{px:.1f}" y="30" width="{pw:.1f}" height="24" rx="12" fill="none" stroke="{c["rule"]}"/>')
    if building:
        out.append(
            f'<g transform="translate({px + 13:.1f} 36)"><g clip-path="url(#hz)"><rect width="12" height="12" fill="#F5B800"/>'
            '<path d="M-3 9L6-3M1 15L13 0M7 18L17 5" stroke="#141414" stroke-width="2.4"/></g></g>'
        )
    else:
        out.append(f'<circle class="live" cx="{px + 18:.1f}" cy="42" r="4.5" fill="#1E9E5A"/>')
    out.append(f'<text x="{px + 32:.1f}" y="46" class="pill" textLength="{tw:.1f}" lengthAdjust="spacing">{tx(label)}</text>')

    for i, line in enumerate(route["blurb"]):
        out.append(f'<text x="32" y="{106 + i * 22}" class="blurb">{tx(line)}</text>')

    # the project as its own little route
    stops = route["stops"]
    x0, x1, y = 54, 446, 176
    xs = [x0 + i * (x1 - x0) / (len(stops) - 1) for i in range(len(stops))]
    for i in range(len(stops) - 1):
        built = stops[i + 1][1]
        dash = "" if built else ' stroke-dasharray="10 7" opacity=".55"'
        out.append(
            f'<line x1="{xs[i]:.1f}" y1="{y}" x2="{xs[i + 1]:.1f}" y2="{y}" stroke="{color}" stroke-width="7" '
            f'stroke-linecap="round"{dash}/>'
        )
    for x, (label, built) in zip(xs, stops):
        if built:
            out.append(f'<circle cx="{x:.1f}" cy="{y}" r="7.5" fill="{c["pearl"]}" stroke="{c["ink"]}" stroke-width="2.5"/>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{y}" r="6" fill="{c["bg"]}" stroke="{color}" stroke-width="2.5"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 28}" text-anchor="middle" class="stop{"" if built else " fut"}">{tx(label)}</text>')

    out.append(f'<line x1="24" y1="{H - 38}" x2="{W - 24}" y2="{H - 38}" stroke="{c["rule"]}"/>')
    out.append(f'<text x="32" y="{H - 15}" class="foot">{tx(route["footer"])}</text>')
    out.append(f'<text x="{W - 32}" y="{H - 15}" text-anchor="end" class="go" fill="{color}">VIEW ROUTE →</text>')

    style = f"""
text{{font-family:{SANS}}}
.eyebrow{{font-size:10.5px;font-weight:700;letter-spacing:2.4px;fill:{c["sub"]}}}
.name{{font-size:25px;font-weight:700;letter-spacing:-.4px;fill:{c["ink"]}}}
.pill{{font-size:10.5px;font-weight:700;letter-spacing:1.6px;fill:{c["ink"]}}}
.blurb{{font-size:15.5px;fill:{c["sub"]}}}
.stop{{font-size:13.5px;font-weight:700;fill:{c["ink"]}}}.stop.fut{{fill:{c["sub"]};font-weight:600}}
.foot{{font-family:{MONO};font-size:12px;fill:{c["sub"]}}}
.go{{font-size:11px;font-weight:700;letter-spacing:1.8px}}
.live{{animation:pulse 1.8s ease-in-out infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
@media (prefers-reduced-motion:reduce){{.live{{animation:none}}}}
"""
    title = f"{route['name']}: {route['status']}. " + " ".join(route["blurb"])
    return svg(W, H, title, style, "".join(out))


# ---------------------------------------------------------------------------
# signs and ticket
# ---------------------------------------------------------------------------

def build_sign(label: str, right) -> str:
    W, H = 1000, 64
    out = [
        f'<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="9" fill="#151515" stroke="#2C2C2C" stroke-width="1.5"/>',
        f'<rect x="14" y="9" width="{W - 28}" height="2.5" fill="#F4F1EA"/>',
        f'<text x="26" y="47" class="lbl">{tx(label)}</text>',
    ]
    if right == "arrow":
        out.append(
            f'<g transform="translate({W - 52} 38)" fill="none" stroke="#F4F1EA" stroke-width="4" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M-14 0H14M3-11L14 0L3 11"/></g>'
        )
    elif right == "exit":
        out.append(
            f'<g transform="translate({W - 52} 38)" fill="none" stroke="#F4F1EA" stroke-width="4" '
            'stroke-linecap="round" stroke-linejoin="round"><path d="M-11 11L11-11M-4-11H11V4"/></g>'
        )
    else:
        for i, key in enumerate(reversed(right)):
            out.append(bullet(W - 40 - i * 38, 38, key, 15))
    style = f"text{{font-family:{SANS}}}.lbl{{font-size:25px;font-weight:700;fill:#F4F1EA;letter-spacing:-.2px}}"
    return svg(W, H, label, style, "".join(out))


def build_ticket(email: str) -> str:
    W, H = 640, 300
    ink, paper, stamp = "#3A2F25", "#E9DEC4", "#5B3E8F"
    stripe = "".join(
        f'<rect x="{248 + i * 24}" y="160" width="24" height="6" fill="{LINES[k][1]}"/>' for i, k in enumerate(LINES)
    )
    body = f"""
<defs>
<mask id="punch"><rect width="{W}" height="{H}" fill="#fff"/><circle cx="60" cy="92" r="9" fill="#000"/></mask>
<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".85" numOctaves="3" seed="7"/>
<feColorMatrix values="0 0 0 0 .23  0 0 0 0 .18  0 0 0 0 .14  0 0 0 .55 0"/><feComposite in2="SourceGraphic" operator="in"/></filter>
<filter id="worn"><feTurbulence type="fractalNoise" baseFrequency="1.1" numOctaves="2" seed="3" result="n"/>
<feColorMatrix in="n" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -2.4 1.75" result="m"/><feComposite in="SourceGraphic" in2="m" operator="in"/></filter>
</defs>
<g mask="url(#punch)">
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{paper}"/>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="14" fill="{paper}" filter="url(#grain)" opacity=".5"/>
<rect x="14" y="14" width="{W - 28}" height="{H - 28}" rx="8" fill="none" stroke="{ink}" stroke-width="1.4"/>
<rect x="19" y="19" width="{W - 38}" height="{H - 38}" rx="5" fill="none" stroke="{ink}" stroke-width=".6"/>
<text x="38" y="52" class="mono serial">No. 0000</text>
<text x="{W - 38}" y="52" text-anchor="end" class="mono serial">No. 0000</text>
<text x="{W / 2}" y="52" text-anchor="middle" class="small">NITESH KADIAN · ALL LINES</text>
<text x="{W / 2}" y="98" text-anchor="middle" class="big">SINGLE JOURNEY</text>
<rect x="38" y="116" width="{W - 76}" height="1" fill="{ink}"/>
<text x="38" y="146" class="small">FROM</text>
<text x="37" y="178" class="place">YOUR IDEA</text>
{stripe}
<path d="M392 163h8m-6-5l6 5-6 5" fill="none" stroke="{ink}" stroke-width="1.6"/>
<text x="{W - 38}" y="146" text-anchor="end" class="small">TO</text>
<text x="{W - 37}" y="178" text-anchor="end" class="place">PRODUCTION</text>
<rect x="38" y="198" width="{W - 76}" height="1" fill="{ink}"/>
<text x="38" y="222" class="small">CLASS</text><text x="38" y="243" class="val">ANY</text>
<text x="170" y="222" class="small">FARE</text><text x="170" y="243" class="val">ONE CONVERSATION</text>
<text x="380" y="222" class="small">VALID</text><text x="380" y="243" class="val">ALL LINES</text>
<text x="38" y="272" class="mono fine">{tx(email)}  ·  not transferable  ·  mind the gap</text>
<g transform="translate(540 236) rotate(-8)" filter="url(#worn)" opacity=".85">
<rect x="-74" y="-27" width="148" height="54" rx="8" fill="none" stroke="{stamp}" stroke-width="3"/>
<rect x="-68" y="-21" width="136" height="42" rx="5" fill="none" stroke="{stamp}" stroke-width="1.2"/>
<text x="0" y="-3" text-anchor="middle" class="stamp">OPEN TO</text>
<text x="0" y="14" text-anchor="middle" class="stamp" textLength="116" lengthAdjust="spacingAndGlyphs">COLLABORATE</text>
</g>
</g>
<circle cx="60" cy="92" r="9" fill="none" stroke="#000" stroke-opacity=".18" stroke-width="1.5"/>
"""
    style = f"""
text{{font-family:{SANS};fill:{ink}}}.mono{{font-family:{MONO}}}
.serial{{font-size:13px;font-weight:700}}
.small{{font-size:10.5px;font-weight:700;letter-spacing:3px}}
.big{{font-size:31px;font-weight:700;letter-spacing:7px}}
.place{{font-size:27px;font-weight:700;letter-spacing:.5px}}
.val{{font-size:15px;font-weight:700;letter-spacing:1px}}
.fine{{font-size:11px;fill:#6B5D4E}}
.stamp{{font-size:14px;font-weight:700;letter-spacing:2px;fill:{stamp}}}
"""
    return svg(W, H, f"Ticket: single journey from your idea to production. {email}", style, body)


# ---------------------------------------------------------------------------

def write(name: str, content: str) -> None:
    path = ASSETS / name
    if not path.exists() or path.read_text() != content:
        path.write_text(content)
        print(f"  wrote {name}")


def main() -> None:
    cfg = json.loads((STATION / "routes.json").read_text())
    ASSETS.mkdir(exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    rows = departures(cfg, load_repos(cfg, "--offline" in sys.argv), now)

    write("board.svg", build_board(cfg, rows))
    for theme in THEMES:
        write(f"map-{theme}.svg", build_map(theme))
        for route in cfg["routes"]:
            write(f"route-{route['id']}-{theme}.svg", build_card(route, theme))
    write("sign-map.svg", build_sign("Network map", list(LINES)))
    write("sign-routes.svg", build_sign("Routes in service", "arrow"))
    write("sign-exit.svg", build_sign("Exit · say hello", "exit"))
    write("ticket.svg", build_ticket(cfg["email"]))


if __name__ == "__main__":
    main()
