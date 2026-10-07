"""
Combat record panel: the service record screen.

Left: rank plate (drawn insignia for intel.rank_tier, level, rank title,
prestige emblem, XP bar). Right: a 3 x 2 grid of career stats, each with its
game label and what it means in developer terms. Bottom: the engagement map,
the last year's contribution calendar, with the best day under a crosshair.
"""
from __future__ import annotations

import datetime as dt
import math
import re

from ui import C, W, chamfer, canvas, d, esc, fit, frame, header, roman, svg

try:  # rank ladder, for "next rank" (read-only use of the intel module)
    from intel import RANKS
except Exception:  # pragma: no cover
    RANKS = []

X0, X1 = 36, W - 36
TOP = 100
RANK_W = 300
PANEL_H = 250
GGAP = 10
CELL, CGAP = 14, 2.8   # leaves the weekday labels a clear gutter before the grid
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()

GOLD = ("#FFE7A3", "#F4B740", "#B9831C", "#FFD36B")
SILVER = ("#FFFFFF", "#C9CEC4", "#868C82", "#E9ECE4")
RAMP = ["#191D18", "#33450F", "#577419", "#8FB324", C["accent"]]


# DIN Condensed Bold advance widths (em), measured in Chrome on macOS. Used to pin
# condensed text to its designed width with textLength, so wider fallback fonts
# (Arial Bold on Linux) squeeze instead of overflowing their boxes.
_DIN = {**dict.fromkeys("0123456789", .37), **dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    (.41, .43, .41, .43, .37, .37, .43, .43, .20, .33, .43, .37, .56, .44, .43, .41, .43, .43, .41, .33,
     .43, .41, .59, .39, .39, .33))), " ": .16, "-": .39, ".": .19, "%": .35, "·": .19, "/": .3, ",": .19}


def cond_w(text: str, size: float, ls: float = 0.0) -> float:
    return sum(_DIN.get(ch, .43) for ch in text) * size + ls * len(text)


def cond(x, y, text, size, max_w=None, ls=0.0, anchor="start", extra=""):
    """Condensed text pinned to its DIN width (never wider than max_w)."""
    w = cond_w(text, size, ls)
    if max_w is not None:
        w = min(w, max_w)
    ex = (f'letter-spacing="{ls}" ' if ls else "") + extra
    return fit(x, y, text, size, round(w, 1), anchor=anchor, extra=ex)


# --------------------------------------------------------------------------- insignia
# Drawn around (0, 0) inside about 80 x 80; fills use the #rkGold / #rkSilver gradients.

def _star(cx, cy, r, fill):
    pts = []
    for i in range(10):
        rr = r if i % 2 == 0 else r * .42
        t = math.radians(-90 + 36 * i)
        pts.append(f"{cx + rr * math.cos(t):.2f} {cy + rr * math.sin(t):.2f}")
    return f'<path d="M{"L".join(pts)}Z" fill="{fill}"/>'


def _chevron(cy, fill):
    # point-up chevron band, 58 wide, 7 thick
    return (f'<path d="M-29 {cy + 10}L0 {cy - 8}L29 {cy + 10}V{cy + 17.5}L0 {cy - .5}L-29 {cy + 17.5}Z" '
            f'fill="{fill}"/>')


def _rocker(cy, fill):
    return (f'<path d="M-29 {cy}Q0 {cy + 15} 29 {cy}V{cy + 7}Q0 {cy + 22} -29 {cy + 7}Z" fill="{fill}"/>')


def _bar(cx, fill, h=62):
    return (
        f'<rect x="{cx - 10}" y="{-h / 2}" width="20" height="{h}" rx="2.5" fill="{fill}"/>'
        f'<rect x="{cx - 6.5}" y="{-h / 2 + 4.5}" width="13" height="{h - 9}" rx="1" fill="{fill}" '
        f'transform="rotate(180 {cx} 0)"/>'
        f'<rect x="{cx - 6.5}" y="{-h / 2 + 4.5}" width="13" height="{h - 9}" rx="1" fill="none" '
        f'stroke="#000" stroke-opacity=".25"/>'
        f'<rect x="{cx - 8.5}" y="{-h / 2 + 1.5}" width="2.4" height="{h - 3}" rx="1.2" fill="#fff" opacity=".45"/>'
    )


def _oak(fill):
    pts = []
    for i in range(96):
        t = 2 * math.pi * i / 96
        lobe = 1 + .14 * abs(math.sin(3.5 * t))
        x = 20 * math.sin(t) * lobe
        y = -27 * math.cos(t) * (1 + .04 * abs(math.sin(3.5 * t)))
        pts.append(f"{x:.2f} {y - 3:.2f}")
    return (
        f'<path d="M{"L".join(pts)}Z" fill="{fill}"/>'
        f'<path d="M0 -26V30" stroke="#000" stroke-opacity=".28" stroke-width="1.6"/>'
        f'<path d="M0 -12L-11 -20M0 -12L11 -20M0 0L-14 -7M0 0L14 -7M0 12L-12 6M0 12L12 6" '
        f'stroke="#000" stroke-opacity=".22" stroke-width="1.2" fill="none"/>'
    )


def _eagle(fill):
    wing = [(-4, -6), (-14, -14), (-26, -22), (-36, -28), (-33, -20), (-38, -18), (-33, -12),
            (-37, -8), (-31, -4), (-33, 1), (-24, 2), (-10, 6)]
    wing_r = [(-x, y) for x, y in wing]
    poly = lambda p: "M" + "L".join(f"{x} {y}" for x, y in p) + "Z"
    return (
        f'<path d="{poly(wing)}" fill="{fill}"/><path d="{poly(wing_r)}" fill="{fill}"/>'
        f'<path d="M-7 -10Q0 -14 7 -10L8 14L0 18L-8 14Z" fill="{fill}"/>'
        f'<path d="M-10 16L0 30L10 16L5 18L0 16L-5 18Z" fill="{fill}"/>'
        f'<circle cx="0" cy="-15" r="6" fill="{fill}"/>'
        f'<path d="M2 -13L9 -11L3 -9Z" fill="{fill}"/>'
        f'<path d="M-4 0H4M-4 5H4M-4 10H4" stroke="#000" stroke-opacity=".25"/>'
        f'<path d="M-14 -6L-28 -16M-12 -2L-30 -6M14 -6L28 -16M12 -2L30 -6" stroke="#000" stroke-opacity=".2"/>'
    )


def insignia(tier: int) -> str:
    g, s = "url(#rkGold)", "url(#rkSilver)"
    if tier <= 10:
        chev = [1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 3][tier]
        rock = [0, 1, 0, 1, 0, 1, 2, 3, 3, 3, 3][tier]
        device = tier >= 8
        out = [_chevron(i * 11, g) for i in range(chev)]
        last = (chev - 1) * 11
        ry = last + (26 if device else 9)
        out += [_rocker(ry + j * 11, g) for j in range(rock)]
        mid = (last - .5 + ry + 7.5) / 2
        if tier == 8:
            out.append(f'<path d="M0 {mid - 8}L6 {mid}L0 {mid + 8}L-6 {mid}Z" fill="{g}"/>')
        elif tier >= 9:
            out.append(_star(0, mid + (1 if tier == 10 else 0), 8 if tier == 9 else 6.5, g))
            if tier == 10:
                out.append(f'<path d="M-10 {mid - 3}A10.5 10.5 0 0 0 10 {mid - 3}" fill="none" '
                           f'stroke="{g}" stroke-width="2.2"/>')
        y0 = -8
        y1 = (ry + (rock - 1) * 11 + 22) if rock else last + 17.5
        sc = min(1.0, 70 / (y1 - y0))
        return f'<g transform="scale({sc:.3f}) translate(0 {-(y0 + y1) / 2:.2f})">{"".join(out)}</g>'
    if tier == 11:
        return _bar(0, g)
    if tier == 12:
        return _bar(0, s)
    if tier == 13:
        return _bar(-12, s) + _bar(12, s)
    if tier == 14:
        return _oak(g)
    if tier == 15:
        return _oak(s)
    if tier == 16:
        return _eagle(s)
    n = min(4, tier - 16)  # 17: one star, 18: two, beyond: three or four
    xs = [0] if n == 1 else [-15, 15] if n == 2 else [-24, 0, 24] if n == 3 else [-27, -9, 9, 27]
    r = 21 if n == 1 else 15 if n == 2 else 11
    return "".join(_star(x, 0, r, s) for x in xs)


def prestige_emblem(cx, cy, level: int) -> str:
    lit = level > 0
    edge = "url(#rkGold)" if lit else C["line2"]
    hexa = lambda r: "M" + "L".join(
        f"{cx + r * math.cos(math.radians(60 * i - 90)):.2f} {cy + r * math.sin(math.radians(60 * i - 90)):.2f}"
        for i in range(6)) + "Z"
    num = roman(level) if lit else "0"
    return (
        f'<path d="{hexa(29)}" fill="{edge}"/>'
        + f'<path d="{hexa(24.5)}" fill="{C["bg"]}"/>'
        + f'<path d="{hexa(21)}" fill="none" stroke="{C["gold"] if lit else C["line2"]}" stroke-opacity=".45"/>'
        + _star(cx, cy - 29, 5.5, edge)
        + cond(cx, cy + 9, num, 26, 34, ls=1, anchor="middle", extra=f'fill="{C["gold"] if lit else C["dim"]}"')
    )


# --------------------------------------------------------------------------- panels

def _num(n) -> str:
    return f"{int(n):,}"


def rank_panel(intel) -> str:
    x, y, w, h = X0, TOP, RANK_W, PANEL_H
    tier = int(intel["rank_tier"])
    level = int(intel["level"])
    out = [f'<g class="in-left" {d(.15)}>', frame(x, y, w, h, 12)]

    # insignia plate
    px, py, ps = x + 16, y + 16, 100
    pcx, pcy = px + ps / 2, py + ps / 2
    out.append(f'<path d="{chamfer(px, py, ps, ps, 10)}" fill="url(#rkPlate)" stroke="{C["line2"]}"/>')
    ticks = "".join(
        f'M{pcx + 38 * math.cos(math.radians(a)):.1f} {pcy + 38 * math.sin(math.radians(a)):.1f}'
        f'L{pcx + 42 * math.cos(math.radians(a)):.1f} {pcy + 42 * math.sin(math.radians(a)):.1f}'
        for a in range(0, 360, 30))
    out.append(f'<circle cx="{pcx}" cy="{pcy}" r="42" fill="none" stroke="{C["line2"]}"/>'
               f'<path d="{ticks}" stroke="{C["dim"]}"/>')
    out.append(f'<g class="in-scale" {d(.55)}><g transform="translate({pcx} {pcy})" filter="url(#rkShadow)">'
               f'{insignia(tier)}</g></g>')

    # level
    lx = px + ps + 16
    out.append(f'<text x="{lx}" y="{y + 34}" class="mono sub cap">LEVEL</text>')
    digits = str(level)
    out.append(f'<g class="in" {d(.6)}>' + fit(lx - 2, y + 110, digits, 84, 39 * len(digits) - 2) + "</g>")

    # prestige
    ex, ey = x + w - 46, y + 58
    out.append(f'<g class="in-scale" {d(.8)}>{prestige_emblem(ex, ey, int(intel["prestige"]))}</g>')
    out.append(f'<text x="{ex}" y="{y + 110}" text-anchor="middle" class="mono {"gold" if int(intel["prestige"]) else "dim"}" font-size="11" '
               f'font-weight="700" letter-spacing="1.6">PRESTIGE</text>')

    # rank title
    title = str(intel["rank"]).upper()
    out.append(cond(x + 18, y + 152, title, 32, w - 36, ls=.3))
    nxt = RANKS[tier + 1] if 0 <= tier + 1 < len(RANKS) else None
    sub = esc(str(intel.get("rank_short", "")).upper())
    if nxt:
        name = nxt[1].upper()
        if len(sub) + len(name) + len(str(nxt[0])) + 16 > 35:  # ~264px of 11px mono
            name = nxt[2].upper()
        sub += f' · NEXT <tspan fill="{C["text"]}">{esc(name)}</tspan> AT LVL {nxt[0]}'
    else:
        sub += " · TOP OF THE LADDER"
    out.append(f'<text x="{x + 18}" y="{y + 172}" class="mono sub" font-size="11" font-weight="700" '
               f'letter-spacing=".8">{sub}</text>')

    # XP bar
    xp, lo, hi = int(intel["xp"]), int(intel["xp_level_floor"]), int(intel["xp_next"])
    frac = 1.0 if hi <= lo else max(0.0, min(1.0, (xp - lo) / (hi - lo)))
    bx, bw, by = x + 18, w - 36, y + 207
    out.append(f'<text x="{bx}" y="{by - 9}" class="mono cap gold">XP</text>')
    out.append(f'<text x="{bx + bw}" y="{by - 9}" text-anchor="end" class="mono" font-size="12" '
               f'font-weight="700" letter-spacing=".6">{_num(xp)}<tspan fill="{C["sub"]}"> / {_num(hi)} XP</tspan></text>')
    out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="8" fill="{C["line"]}"/>')
    out.append(f'<rect class="in-wipe" {d(.9)} x="{bx}" y="{by}" width="{bw * frac:.1f}" height="8" fill="url(#rkXp)"/>')
    out.append("<path d=\"" + "".join(f"M{bx + bw * t / 10:.1f} {by}v8" for t in range(1, 10))
               + f'" stroke="{C["panel"]}" stroke-width="2"/>')
    if hi > xp:
        left = f"{_num(hi - xp)} XP TO LEVEL {level + 1}"
    else:
        left = "MAX LEVEL"
    out.append(f'<text x="{bx}" y="{by + 25}" class="mono sub" font-size="11" letter-spacing=".6">{left}</text>')
    out.append(f'<text x="{bx + bw}" y="{by + 25}" text-anchor="end" class="mono gold" font-size="11" '
               f'font-weight="700" letter-spacing=".6">{int(frac * 100)}%</text>')
    out.append("</g>")
    return "".join(out)


def glyph(kind, x, y, col):
    """Tiny 16 x 16 stat glyphs, top-left at (x, y)."""
    s = f'fill="none" stroke="{col}" stroke-width="1.5"'
    cx, cy = x + 8, y + 8
    if kind == "kills":
        return (f'<circle cx="{cx}" cy="{cy}" r="5.5" {s}/>'
                f'<path d="M{cx} {y}v4M{cx} {y + 12}v4M{x} {cy}h4M{x + 12} {cy}h4" {s}/>')
    if kind == "days":
        return (f'<rect x="{x + 1}" y="{y + 2.5}" width="14" height="12.5" {s}/>'
                f'<path d="M{x + 1} {y + 6.5}h14M{x + 5} {y}v4M{x + 11} {y}v4" {s}/>')
    if kind == "streak":
        return f'<path d="M{x + 2} {y + 15}L{x + 6} {y + 7}L{x + 10} {y + 11}L{x + 15} {y + 1}M{x + 10} {y + 1}h5v5" {s}/>'
    if kind == "best":
        return _star(cx, cy + .5, 8, "none").replace('fill="none"', s)
    if kind == "time":
        return (f'<circle cx="{cx}" cy="{cy}" r="7" {s}/>'
                f'<path d="M{cx} {cy - 4}V{cy}L{cx + 3.5} {cy + 2}" {s}/>')
    return (f'<path d="M{x + 5} {y + 15.5}V{y + 6.5}Q{x + 5} {y + 1} {x + 8} {y}Q{x + 11} {y + 1} {x + 11} {y + 6.5}'
            f'V{y + 15.5}ZM{x + 5} {y + 7}H{x + 11}M{x + 5} {y + 13}H{x + 11}" {s}/>')


def stat_cell(x, y, w, h, label, big, meaning, kind, delay, extra=""):
    out = [f'<g class="in-up" {d(delay)}>']
    out.append(f'<path d="{chamfer(x, y, w, h, 8, corners=("br",))}" fill="{C["panel"]}" stroke="{C["line2"]}"/>')
    out.append(f'<rect x="{x}" y="{y}" width="3" height="22" fill="{C["accent"]}"/>')
    out.append(f'<text x="{x + 16}" y="{y + 23}" class="mono cap" fill="{C["text"]}">{esc(label)}</text>')
    out.append(glyph(kind, x + w - 30, y + 11, C["dim"]))
    out.append(big)
    for j, ln in enumerate(meaning):
        out.append(f'<text x="{x + 16}" y="{y + 90 + j * 17}" font-size="13" class="sub">{ln}</text>')
    out.append(extra)
    out.append("</g>")
    return "".join(out)


def stat_grid(intel) -> str:
    gx0 = X0 + RANK_W + 12
    cw = (X1 - gx0 - 2 * GGAP) / 3
    ch = (PANEL_H - GGAP) / 2

    def big(x, y, value, unit=""):
        # digits big, unit letters small: "23D", "2Y 1M"
        parts, prev = [], ""
        for c in unit.replace(" ", ""):
            if c.isalpha():
                parts.append(f'<tspan font-size="28" fill="{C["sub"]}" dx="2">{esc(c)}</tspan>')
            else:
                parts.append(f'<tspan dx="{9 if prev.isalpha() else 0}">{esc(c)}</tspan>')
            prev = c
        u = "".join(parts)
        return (f'<text x="{x + 15}" y="{y + 69}" class="cond" font-size="50" letter-spacing=".5">'
                f'{esc(value)}{u}</text>')

    days = [dd for wk in intel["weeks"] for dd in wk]
    best = max(days, key=lambda dd: dd["count"]) if days else None
    best_date = dt.date.fromisoformat(best["date"]) if best else None
    joined = dt.date.fromisoformat(intel["joined"])
    cur = int(intel["current_streak"])

    cells = []
    pos = [(gx0 + c * (cw + GGAP), TOP + r * (ch + GGAP)) for r in range(2) for c in range(3)]

    x, y = pos[0]
    cells.append(stat_cell(x, y, cw, ch, "ELIMINATIONS", big(x, y, _num(intel["total"])),
                           ["contributions", "in the last year"], "kills", .35))
    x, y = pos[1]
    cells.append(stat_cell(x, y, cw, ch, "DAYS DEPLOYED", big(x, y, _num(intel["active_days"])),
                           ["days with a contribution", "in the last year"], "days", .42))
    x, y = pos[2]
    cells.append(stat_cell(x, y, cw, ch, "LONGEST STREAK", big(x, y, str(intel["longest_streak"]), "D"),
                           ["days in a row",
                            f'current run: <tspan fill="{C["text"]}">{cur} day{"s" if cur != 1 else ""}</tspan>'],
                           "streak", .49))
    x, y = pos[3]
    when = f"{MONTHS[best_date.month - 1].title()} {best_date.day}, {best_date.year}" if best_date else "-"
    cells.append(stat_cell(x, y, cw, ch, "BEST MATCH", big(x, y, str(intel["best_day"])),
                           ["most in one day", f'on <tspan fill="{C["text"]}">{when}</tspan>'], "best", .56))
    x, y = pos[4]
    yrs, mos = int(intel["service_years"]), int(intel["service_months"])
    cells.append(stat_cell(x, y, cw, ch, "TIME IN SERVICE",
                           big(x, y, "", f"{yrs}Y {mos}M" if yrs else f"{mos}M"),
                           ["on GitHub since",
                            f'<tspan fill="{C["text"]}">{MONTHS[joined.month - 1].title()} {joined.year}</tspan>'],
                           "time", .63))
    x, y = pos[5]
    lang = str(intel.get("top_language") or "N/A").upper()
    share = int(intel.get("top_language_share") or 0)
    lang_txt = cond(x + 15, y + 69, lang, 50, cw - 32, ls=.5)
    bw = cw - 32 - 44
    meter = (
        f'<rect x="{x + 16}" y="{y + 100}" width="{bw:.1f}" height="5" fill="{C["line"]}"/>'
        f'<rect class="in-wipe" {d(1.1)} x="{x + 16}" y="{y + 100}" width="{bw * share / 100:.1f}" height="5" '
        f'fill="{C["accent"]}"/>'
        f'<text x="{x + cw - 16}" y="{y + 106}" text-anchor="end" class="mono" font-size="12" '
        f'font-weight="700">{share}%</text>'
    )
    cells.append(stat_cell(x, y, cw, ch, "PRIMARY", lang_txt, ["top language by code"], "primary", .70, meter))
    return "".join(cells)


def engagement_map(intel, y) -> tuple[str, int]:
    weeks = intel["weeks"][-53:]
    n = len(weeks)
    pitch = CELL + CGAP
    gx = X1 - (n * pitch - CGAP)
    my = y + 46  # top of the cells

    counts = sorted(dd["count"] for wk in weeks for dd in wk if dd["count"] > 0)

    def q(p):
        return counts[min(len(counts) - 1, int(p * len(counts)))] if counts else 0

    cuts = [q(.25), q(.5), q(.75)]

    def level(c):
        if c <= 0:
            return 0
        return 1 + sum(c > t for t in cuts)

    out = []
    # section title + legend
    title_end = X0 + 12 + cond_w("ENGAGEMENT MAP", 22, .6)
    out.append(f'<g class="in" {d(.8)}>'
               f'<rect x="{X0}" y="{y}" width="3" height="20" fill="{C["accent"]}"/>'
               + cond(X0 + 12, y + 17, "ENGAGEMENT MAP", 22, ls=.6) +
               f'<text x="{title_end + 18:.1f}" y="{y + 16}" class="mono sub cap">// PAST YEAR</text>')
    sw_x = X1 - 46 - (5 * 15 - 3)
    out.append(f'<text x="{X1}" y="{y + 16}" text-anchor="end" class="mono sub cap">MORE</text>')
    for i, col in enumerate(RAMP):
        out.append(f'<rect x="{sw_x + i * 15}" y="{y + 5}" width="12" height="12" fill="{col}"/>')
    out.append(f'<text x="{sw_x - 10}" y="{y + 16}" text-anchor="end" class="mono sub cap">LESS</text>')
    best_n = max((dd["count"] for wk in weeks for dd in wk), default=0)
    if best_n > 0:
        bl = f"BEST DAY {best_n}"
        be = sw_x - 10 - 4 * 9.2 - 26
        gx0 = be - len(bl) * 9.2 - 22
        gc = gx0 + 7
        out.append(
            f'<rect x="{gc - 5}" y="{y + 6}" width="10" height="10" fill="none" stroke="#fff" stroke-width="1.4"/>'
            f'<path d="M{gc} {y + 1}v3M{gc} {y + 18}v3M{gc - 10} {y + 11}h3M{gc + 7} {y + 11}h3" stroke="#fff" stroke-width="1.4"/>'
            f'<text x="{be:.1f}" y="{y + 16}" text-anchor="end" class="mono cap" fill="{C["text"]}">{bl}</text>'
        )
    out.append("</g>")

    # weekday labels
    out.append(f'<g class="in" {d(.8)}>')
    for row, name in ((1, "MON"), (3, "WED"), (5, "FRI")):
        out.append(f'<text x="{X0}" y="{my + row * pitch + 11}" class="mono sub" font-size="11" '
                   f'font-weight="700">{name}</text>')

    # month labels where a week's first day enters a new month
    labels, prev = [], None
    for c, wk in enumerate(weeks):
        m = dt.date.fromisoformat(wk[0]["date"]).month
        if m != prev:
            labels.append((c, MONTHS[m - 1]))
            prev = m
    shown = []
    for c, name in labels:
        if shown and c - shown[-1][0] < 3:
            shown.pop()  # a stub month at the left edge: keep the later one
        shown.append((c, name))
    if shown and n - shown[-1][0] < 3 and len(shown) > 1:
        shown.pop()  # a stub month at the right edge would hang past the grid
    for c, name in shown:
        out.append(f'<text x="{gx + c * pitch:.1f}" y="{my - 9}" class="mono sub" font-size="11" '
                   f'font-weight="700" letter-spacing=".6">{name}</text>')
    out.append("</g>")

    # cells, column by column
    best = None
    for c, wk in enumerate(weeks):
        cells = []
        for dd in wk:
            r = int(dd["weekday"])
            cx, cy = gx + c * pitch, my + r * pitch
            cells.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{CELL}" height="{CELL}" fill="{RAMP[level(dd["count"])]}"/>')
            if best is None or dd["count"] > best[0]:
                best = (dd["count"], cx, cy)
        out.append(f'<g class="in" {d(.9 + c * .022)}>{"".join(cells)}</g>')

    # transient scan bar (hidden at rest)
    out.append(f'<rect class="rk-scan" x="{gx - 2:.1f}" y="{my - 4}" width="2" height="{7 * pitch + 5:.1f}" '
               f'fill="{C["accent"]}"/>')

    # crosshair on the best day
    if best and best[0] > 0:
        _, bx, by = best
        cx, cy = bx + CELL / 2, by + CELL / 2
        r0, r1 = CELL / 2 + 3, CELL / 2 + 8
        hair = (f"M{cx:.1f} {cy - r1:.1f}V{cy - r0:.1f}M{cx:.1f} {cy + r0:.1f}V{cy + r1:.1f}"
                f"M{cx - r1:.1f} {cy:.1f}H{cx - r0:.1f}M{cx + r0:.1f} {cy:.1f}H{cx + r1:.1f}")
        hit = (f"M{cx - 13:.1f} {cy - 13:.1f}l5 5M{cx + 13:.1f} {cy - 13:.1f}l-5 5"
               f"M{cx - 13:.1f} {cy + 13:.1f}l5 -5M{cx + 13:.1f} {cy + 13:.1f}l-5 -5")
        out.append(
            f'<g class="in-scale" {d(2.2)}>'
            f'<rect x="{bx - 2:.1f}" y="{by - 2:.1f}" width="{CELL + 4}" height="{CELL + 4}" fill="none" stroke="#fff" stroke-width="1.5"/>'
            f'<path d="{hair}" stroke="#fff" stroke-width="2"/></g>'
            f'<path class="rk-hit" d="{hit}" stroke="{C["enemy"]}" stroke-width="2.2"/>'
        )
    bottom = my + 7 * pitch - CGAP
    return "".join(out), bottom


# ui's base rule `text:not([fill])` (specificity 0,1,1) outranks its own colour classes
# (.sub, .acc, ...: 0,1,0), so restate them at equal specificity; later in the sheet wins.
TEXT_CLASSES = "".join(f"text.{k}{{fill:{C[v]}}}" for k, v in (
    ("sub", "sub"), ("dim", "dim"), ("acc", "accent"), ("fr", "friend"), ("en", "enemy"), ("gold", "gold")))

CSS = TEXT_CLASSES + f"""
.rk-scan{{opacity:0;animation:rk-scan 1.25s linear .85s}}
@keyframes rk-scan{{0%{{opacity:0;transform:translateX(0)}}6%{{opacity:.9}}92%{{opacity:.9}}100%{{opacity:0;transform:translateX({53 * (CELL + CGAP) - CGAP + 2:.0f}px)}}}}
.rk-hit{{opacity:0;animation:rk-hit .5s ease-out 2.25s}}
@keyframes rk-hit{{0%{{opacity:1}}100%{{opacity:0}}}}
.live{{animation:blink 1.2s steps(2,jump-none) infinite}}
"""

DEFS = f"""
<linearGradient id="rkGold" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{GOLD[0]}"/><stop offset=".45" stop-color="{GOLD[1]}"/>
  <stop offset=".7" stop-color="{GOLD[2]}"/><stop offset="1" stop-color="{GOLD[3]}"/>
</linearGradient>
<linearGradient id="rkSilver" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{SILVER[0]}"/><stop offset=".45" stop-color="{SILVER[1]}"/>
  <stop offset=".7" stop-color="{SILVER[2]}"/><stop offset="1" stop-color="{SILVER[3]}"/>
</linearGradient>
<linearGradient id="rkXp" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#9A6E17"/><stop offset="1" stop-color="{C['gold']}"/>
</linearGradient>
<radialGradient id="rkPlate" cx=".5" cy=".5" r=".6">
  <stop offset="0" stop-color="#1D211C"/><stop offset="1" stop-color="{C['bg']}"/>
</radialGradient>
<filter id="rkShadow" x="-30%" y="-30%" width="160%" height="160%">
  <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000" flood-opacity=".7"/>
</filter>
"""


def render(cfg, intel):
    map_y = TOP + PANEL_H + 24
    map_svg, map_bottom = engagement_map(intel, map_y)
    H = math.ceil(map_bottom + 28)

    right = "LIVE INTEL · UPDATED DAILY"
    dot_x = X1 - len(right) * 9.1 - 12
    body = [
        canvas(W, H),
        header("04", "COMBAT RECORD", "SERVICE RECORD", right=right),
        f'<circle class="live" cx="{dot_x:.1f}" cy="{TOP - 38}" r="3.5" fill="{C["enemy"]}"/>',
        rank_panel(intel),
        stat_grid(intel),
        map_svg,
    ]
    title = (f'Combat record: level {intel["level"]} {intel["rank"]}, prestige {intel["prestige"]}. '
             f'{intel["total"]} contributions in the last year over {intel["active_days"]} active days; '
             f'longest streak {intel["longest_streak"]} days; best day {intel["best_day"]}; '
             f'top language {intel["top_language"]} ({intel["top_language_share"]}%).')
    # thirds of the grid width leave float noise (524.6666666666666): keep two decimals
    markup = re.sub(r"\d+\.\d{3,}", lambda m: f"{float(m.group()):.2f}", "".join(body))
    return {"record.svg": svg(W, H, title, markup, css=CSS, defs=DEFS)}
