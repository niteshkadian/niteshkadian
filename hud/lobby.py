"""
Squad lobby: the top menu bar, the party lobby and the exfil footer.

These are small SVGs the README stacks with plain <img> tags:

    tab-*.svg        five 200x56 tabs set side by side at 20% width each,
                     reading as one console-style top menu (Q / E bumpers)
    squad-header.svg section header for the lobby
    squad-*.svg      1000x76 lobby rows: the party leader (live rank, level,
                     prestige) and three open slots that are contact links
    exfil.svg        mission-end footer

Every row is a self-contained card, so the few pixels GitHub leaves between
stacked images read as list spacing rather than a broken panel.
"""
from __future__ import annotations

import math
import re

from ui import C, W, canvas, chamfer, d, esc, fit, header, roman, svg

# DIN Condensed Bold advance widths (per 100px) for ASCII 32..126, measured in
# Chrome. Used to size fitted text so macOS renders at its natural width and
# every other platform is pinned to the same footprint.
_CW = [18.6, 24, 27.8, 37.2, 37.2, 35.2, 48.1, 18.6, 22.2, 22.2, 37, 60, 18.6, 38.9, 18.6, 22.2,
       37.2, 37.2, 37.2, 37.2, 37.2, 37.2, 37.2, 37.2, 37.2, 37.2, 18.6, 18.6, 60, 60, 60, 37, 80,
       40.7, 42.6, 40.7, 42.6, 37, 37, 42.6, 42.6, 20.4, 33.3, 42.6, 37, 55.6, 44.4, 42.6, 40.7,
       42.6, 42.6, 40.6, 33.2, 42.6, 40.7, 59.3, 38.9, 38.8, 33.3, 22.2, 22.2, 22.2, 60, 50, 18.6,
       37, 38.9, 37, 38.9, 37, 22.2, 38.9, 38.9, 18.6, 18.6, 38.9, 18.6, 59.2, 38.9, 37, 38.9, 38.9,
       27.8, 35.2, 20.4, 38.9, 35.2, 53.6, 33.2, 35.2, 31.5, 22.2, 22.2, 22.2, 60]


def cw(s: str, size: float, ls: float = 0.0) -> float:
    """Natural width of condensed text (letter-spacing included)."""
    return sum(_CW[ord(c) - 32] if 32 <= ord(c) < 127 else 45 for c in s) * size / 100 + ls * len(s)


def mw(s: str, size: float, ls: float = 0.0) -> float:
    """Width of monospaced text."""
    return len(s) * (size * 0.602 + ls)


def paint(col) -> str:
    """Text colour as an inline style: it outranks every rule in the base
    stylesheet, so a run's colour never depends on selector specificity."""
    return f'style="fill:{col}"'


# ui's base rule `text:not([fill])` (specificity 0,1,1) outranks its own colour
# classes (.sub, .acc, ...: 0,1,0), which ui.header() relies on. Restate them at
# equal specificity; later in the sheet wins.
TEXT_CLASSES = "".join(f"text.{k}{{fill:{C[v]}}}" for k, v in (
    ("sub", "sub"), ("dim", "dim"), ("acc", "accent"), ("fr", "friend"), ("en", "enemy"), ("gold", "gold")))


def ftext(x, y, s, size, ls=0.0, fill=None, anchor="start", extra="") -> str:
    """Condensed text pinned to its macOS width on every platform."""
    return fit(x, y, s, size, round(cw(s, size, ls), 1), anchor=anchor,
               extra=f'{paint(fill) if fill else ""} letter-spacing="{ls}" {extra}'.strip())


def mono(x, y, parts, size=11, fill=None, ls=1.6, anchor="start", weight=700) -> str:
    """Mono caption; `parts` is a string or a list of (text, colour) runs."""
    if isinstance(parts, str):
        parts = [(parts, fill or C["sub"])]
    runs = "".join(f'<tspan {paint(col)}>{esc(t)}</tspan>' for t, col in parts)
    return (f'<text x="{x}" y="{y}" class="mono" font-size="{size}" font-weight="{weight}" '
            f'letter-spacing="{ls}" text-anchor="{anchor}">{runs}</text>')


# ---------------------------------------------------------------- glyphs

def keycap(x, y, label="", glyph="", w=24, h=22, color=None) -> str:
    """PC key prompt: a small raised key with a letter or a drawn glyph."""
    col = color or C["text"]
    out = [
        f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="3.5" fill="#1B1F1A" stroke="{C["sub"]}" stroke-opacity=".75"/>',
        f'<rect x="{x + 2}" y="{y + h - 4.5}" width="{w - 4}" height="3" rx="1.5" fill="#000" opacity=".45"/>',
    ]
    if label:
        out.append(f'<text x="{x + w / 2}" y="{y + h / 2 + 4.2}" text-anchor="middle" font-size="12" font-weight="700" {paint(col)}>{esc(label)}</text>')
    if glyph:
        out.append(f'<g transform="translate({x + w / 2} {y + h / 2 - 1})" fill="none" stroke="{col}" stroke-width="1.7" '
                   f'stroke-linecap="square" stroke-linejoin="miter">{glyph}</g>')
    return "".join(out)


G_ENTER = '<path d="M5 -5V2H-5"/><path d="M-2 -1L-5 2L-2 5"/>'
G_UP = '<path d="M-5 3L0 -2L5 3"/>'


def star(cx, cy, r, fill) -> str:
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rr = r if k % 2 == 0 else r * .42
        pts.append(f"{cx + rr * math.cos(a):.2f},{cy + rr * math.sin(a):.2f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'


def insignia(cx, cy, tier) -> str:
    """Rank insignia in a shield patch. Tiers follow intel.RANKS (0..18):
    enlisted chevrons and rockers, then officer bars, leaves, eagle, stars."""
    w, h = 32, 36
    x0, y0 = cx - w / 2, cy - h / 2
    patch = (f'<path d="M{cx} {y0}L{x0 + w} {y0 + 7}V{y0 + h - 10}L{cx} {y0 + h}L{x0} {y0 + h - 10}V{y0 + 7}Z" '
             f'fill="url(#patch)" stroke="{C["line2"]}"/>'
             f'<path d="M{cx} {y0 + 3}L{x0 + w - 3} {y0 + 8.7}V{y0 + h - 11.6}L{cx} {y0 + h - 3.4}L{x0 + 3} {y0 + h - 11.6}V{y0 + 8.7}Z" '
             f'fill="none" stroke="#fff" stroke-opacity=".08" stroke-dasharray="1.5 1.5"/>')
    silver, gold = "url(#silver)", "url(#goldm)"
    s = []

    def chev(y):
        s.append(f'<path d="M{cx - 9} {y + 5}L{cx} {y}L{cx + 9} {y + 5}" fill="none" stroke="{silver}" stroke-width="2.6"/>')

    def rocker(y):
        s.append(f'<path d="M{cx - 9} {y}Q{cx} {y + 7} {cx + 9} {y}" fill="none" stroke="{silver}" stroke-width="2.2"/>')

    if tier <= 10:
        chevs = [1, 1, 2, 2, 3, 3, 3, 3, 3, 3, 3][tier]
        rocks = [0, 1, 0, 1, 0, 1, 2, 3, 3, 3, 3][tier]
        total = chevs * 4.6 + rocks * 4.2 + (6 if tier >= 8 else 0)
        y = cy - total / 2 - 1
        for _ in range(chevs):
            chev(y)
            y += 4.6
        if tier == 8:
            s.append(f'<path d="M{cx} {y + 1}l3 3l-3 3l-3 -3z" fill="{silver}"/>')
            y += 7
        elif tier >= 9:
            s.append(star(cx, y + 4, 3.6, silver))
            if tier == 10:
                s.append(f'<circle cx="{cx}" cy="{y + 4}" r="5.4" fill="none" stroke="{silver}" stroke-width="1"/>')
            y += 7
        for _ in range(rocks):
            rocker(y + 2)
            y += 4.2
    elif tier in (11, 12):
        s.append(f'<rect x="{cx - 3.5}" y="{cy - 10}" width="7" height="20" rx="1" fill="{gold if tier == 11 else silver}"/>')
        s.append(f'<rect x="{cx - 1.5}" y="{cy - 8}" width="1.2" height="16" fill="#fff" opacity=".55"/>')
    elif tier == 13:
        for off in (-5, 5):
            s.append(f'<rect x="{cx + off - 3}" y="{cy - 10}" width="6" height="20" rx="1" fill="{silver}"/>')
    elif tier in (14, 15):
        fill = gold if tier == 14 else silver
        s.append(f'<path d="M{cx} {cy - 11}C{cx + 9} {cy - 5} {cx + 8} {cy + 5} {cx} {cy + 9}C{cx - 8} {cy + 5} {cx - 9} {cy - 5} {cx} {cy - 11}Z" fill="{fill}"/>'
                 f'<path d="M{cx} {cy - 7}V{cy + 11}" stroke="#1B1F1A" stroke-width="1.2"/>')
    elif tier == 16:
        s.append(f'<path d="M{cx} {cy - 7}L{cx + 3} {cy}L{cx} {cy + 9}L{cx - 3} {cy}Z" fill="{silver}"/>')
        for sign in (-1, 1):
            for k, (ln, dy) in enumerate(((11, -4), (9, 0), (7, 4))):
                s.append(f'<path d="M{cx + sign * 4} {cy + dy}L{cx + sign * (4 + ln)} {cy + dy - 5 + k}" stroke="{silver}" stroke-width="2"/>')
    else:
        n = 1 if tier == 17 else 2
        for k in range(n):
            s.append(star(cx + (k - (n - 1) / 2) * 11, cy - 1, 7 if n == 1 else 5.6, silver))
    k = 1 if tier < 6 or tier > 10 else (.86 if tier == 6 else .74)  # keep tall stacks inside the patch
    inner = "".join(s)
    if k != 1:
        inner = f'<g transform="translate({cx} {cy}) scale({k}) translate({-cx} {-cy})">{inner}</g>'
    return patch + inner


def emblem(x, y, size=52) -> str:
    """Player emblem: winged spearhead on a dark plate."""
    s = size / 52
    a, t = C["accent"], C["text"]
    feathers = "".join(
        f'<path d="M{20 if sgn < 0 else 32} {yy}L{26 + sgn * ln} {yy - rise}" stroke="{t}" stroke-width="2.6" opacity="{op}"/>'
        for sgn in (-1, 1) for (yy, ln, rise, op) in ((22, 21, 6, .95), (27, 19, 4, .8), (32, 15, 2, .6))
    )
    return (
        f'<g transform="translate({x} {y}) scale({s:.3f})">'
        f'<rect x=".5" y=".5" width="51" height="51" fill="url(#emb)" stroke="{C["line2"]}"/>'
        f'<rect x=".5" y=".5" width="51" height="51" fill="url(#hatch)" opacity=".35"/>'
        f'<circle cx="26" cy="26" r="19" fill="none" stroke="{C["line2"]}" stroke-width="1.2"/>'
        f'{feathers}'
        f'<path d="M26 7L33 19L29.5 19L29.5 41L26 45L22.5 41L22.5 19L19 19Z" fill="{a}"/>'
        f'<path d="M26 7L33 19L29.5 19L29.5 41L26 45Z" fill="#000" opacity=".22"/>'
        f'<path d="M3 3h6M3 3v6M49 49h-6M49 49v-6" stroke="{a}" stroke-width="1.4" fill="none"/>'
        f"</g>"
    )


def platform(kind: str, cx, cy, col) -> str:
    """Contact platform glyphs; deliberately generic, never a brand mark."""
    if kind == "email":
        return (f'<g fill="none" stroke="{col}" stroke-width="1.8" stroke-linejoin="round">'
                f'<rect x="{cx - 13}" y="{cy - 9}" width="26" height="18" rx="1.5"/>'
                f'<path d="M{cx - 12} {cy - 8}L{cx} {cy + 1.5}L{cx + 12} {cy - 8}"/></g>')
    if kind == "linkedin":
        return (f'<rect x="{cx - 12}" y="{cy - 12}" width="24" height="24" rx="4" fill="none" stroke="{col}" stroke-width="1.8"/>'
                f'<rect x="{cx - 7.2}" y="{cy - 2.5}" width="3" height="9.5" fill="{col}"/>'
                f'<rect x="{cx - 7.2}" y="{cy - 7.6}" width="3" height="3" fill="{col}"/>'
                f'<path d="M{cx - 1.2} {cy + 7}V{cy - 2.5}M{cx - 1.2} {cy + 1.6}C{cx - 1.2} {cy - 2.6} {cx + 6.8} {cy - 3.6} {cx + 6.8} {cy + 1.6}V{cy + 7}" '
                f'fill="none" stroke="{col}" stroke-width="2.8"/>')
    # discord: a generic controller
    return (f'<g fill="none" stroke="{col}" stroke-width="1.8" stroke-linejoin="round">'
            f'<path d="M{cx - 8} {cy - 8}H{cx + 8}C{cx + 12} {cy - 8} {cx + 13.5} {cy - 5} {cx + 14.5} {cy}L{cx + 15.5} {cy + 5}'
            f'C{cx + 16.5} {cy + 10} {cx + 11} {cy + 11} {cx + 9} {cy + 7}L{cx + 7} {cy + 4}H{cx - 7}L{cx - 9} {cy + 7}'
            f'C{cx - 11} {cy + 11} {cx - 16.5} {cy + 10} {cx - 15.5} {cy + 5}L{cx - 14.5} {cy}C{cx - 13.5} {cy - 5} {cx - 12} {cy - 8} {cx - 8} {cy - 8}Z"/></g>'
            f'<path d="M{cx - 8.5} {cy - 4.5}V{cy + 1.5}M{cx - 11.5} {cy - 1.5}H{cx - 5.5}" stroke="{col}" stroke-width="1.8"/>'
            f'<circle cx="{cx + 7.5}" cy="{cy - 3}" r="1.6" fill="{col}"/><circle cx="{cx + 10.5}" cy="{cy}" r="1.6" fill="{col}"/>')


# ---------------------------------------------------------------- tabs

TABS = [("01", "BRIEFING"), ("02", "LOADOUT"), ("03", "KILLSTREAKS"), ("04", "RECORD"), ("05", "SQUAD")]
TW, TH = 200, 56


def tab(i: int, idx: str, label: str, active: bool) -> str:
    n = len(TABS)
    first, last = i == 0, i == n - 1
    corners = (("tl",) if first else ()) + (("br",) if last else ())
    shape = chamfer(0, 0, TW, TH, 12, corners)
    # open outline: top and bottom rails, outer ends closed on first/last tab
    if first:
        rail = f"M{TW} .5H12.2L.5 12.2V{TH - .5}H{TW}"
    elif last:
        rail = f"M0 .5H{TW - .5}V{TH - 12.2}L{TW - 12.2} {TH - .5}H0"
    else:
        rail = f"M0 .5H{TW}M0 {TH - .5}H{TW}"

    lw = cw(label, 22, 1.2)
    iw = mw(idx, 11, .6)
    gx = (TW - (iw + 7 + lw)) / 2
    base = 36.5
    out = [
        f'<clipPath id="tc"><path d="{shape}"/></clipPath>',
        f'<path d="{shape}" fill="{C["bg"]}"/>',
        f'<path d="{shape}" fill="url(#grid8)" opacity=".35"/>',
        f'<path d="{shape}" fill="#000" filter="url(#grain)"/>',
        f'<rect width="{TW}" height="{TH}" fill="url(#tshade)"/>',
    ]
    if active:
        out += [
            f'<g class="in" {d(.15)}><rect width="{TW}" height="{TH}" fill="url(#lit)" clip-path="url(#tc)"/></g>',
        ]
    out.append(f'<path d="{rail}" fill="none" stroke="{C["line2"]}"/>')
    if not first:  # seam tick shared with the previous tab
        out.append(f'<rect x="0" y="17" width="1" height="22" fill="{C["line2"]}"/>')
    if active:
        out.append(f'<g class="in" {d(.45)}><rect x="0" y="{TH - 5}" width="{TW}" height="5" fill="{C["accent"]}" opacity=".5" '
                   f'filter="url(#glow)" clip-path="url(#tc)"/></g>')
        out.append(f'<rect class="in-wipe" {d(.3)} x="0" y="{TH - 3}" width="{TW}" height="3" fill="{C["accent"]}" clip-path="url(#tc)"/>')
        cxm = gx + (iw + 7 + lw) / 2
        out.append(f'<g class="in" {d(.55)}><path d="M{cxm - 5:.1f} {TH - 3}L{cxm:.1f} {TH - 8}L{cxm + 5:.1f} {TH - 3}Z" fill="{C["accent"]}"/></g>')
    if first:
        out.append(f'<g class="in" {d(.1)}>{keycap(14, 17, "Q")}</g>')
    if last:
        out.append(f'<g class="in" {d(.1)}>{keycap(TW - 38, 17, "E")}</g>')
    out.append(
        f'<g class="in-down" {d(.05 + .07 * i)}>'
        + mono(round(gx, 1), base - 9, idx, 11, C["accent"] if active else C["dim"], ls=.6)
        + ftext(round(gx + iw + 7, 1), base, label, 22, 1.2, fill=C["text"] if active else C["sub"])
        + "</g>"
    )
    return "".join(out)


TAB_DEFS = f"""
<linearGradient id="lit" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{C['accent']}" stop-opacity="0"/>
  <stop offset="1" stop-color="{C['accent']}" stop-opacity=".16"/>
</linearGradient>
<filter id="glow" x="-10%" y="-200%" width="120%" height="500%"><feGaussianBlur stdDeviation="3.5"/></filter>
<linearGradient id="tshade" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#fff" stop-opacity=".035"/>
  <stop offset=".5" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
"""


# ---------------------------------------------------------------- lobby rows

RW, RH = W, 76
COL_SLOT, COL_ICON, COL_NAME, COL_RIGHT = 29, 74, 144, 748
CARD_R = 536  # right edge of the leader's calling card; the rank block starts 20 later

ROW_DEFS = f"""
<linearGradient id="rowg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['panel2']}" stop-opacity="1"/>
  <stop offset=".6" stop-color="{C['panel2']}" stop-opacity="0"/>
</linearGradient>
<linearGradient id="leadg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['accent']}" stop-opacity=".13"/>
  <stop offset=".55" stop-color="{C['accent']}" stop-opacity="0"/>
</linearGradient>
<linearGradient id="glint" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".22"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<linearGradient id="emb" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#1E231C"/><stop offset="1" stop-color="{C['bg']}"/>
</linearGradient>
<linearGradient id="patch" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#1E221D"/><stop offset="1" stop-color="{C['bg']}"/>
</linearGradient>
<linearGradient id="silver" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#FFFFFF"/><stop offset=".55" stop-color="#C9CEC3"/><stop offset="1" stop-color="#7D8378"/>
</linearGradient>
<linearGradient id="goldm" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#FFE29A"/><stop offset=".5" stop-color="{C['gold']}"/><stop offset="1" stop-color="#A8741C"/>
</linearGradient>
"""

ROW_CSS = """
@keyframes nudge{0%,60%,100%{transform:translateX(0)}30%{transform:translateX(4px)}}
.nudge{animation:nudge 1.8s ease-in-out infinite}
@keyframes glint{0%{transform:translateX(0)}16%,100%{transform:translateX(330px)}}
.glint{animation:glint 7s cubic-bezier(.5,0,.3,1) 1.2s infinite}
"""


def plate(slot: int, lead: bool) -> str:
    shape = chamfer(.5, .5, RW - 1, RH - 1, 12)
    out = [
        f'<path d="{shape}" fill="{C["bg"]}"/>',
        f'<path d="{shape}" fill="url(#grid8)" opacity=".3"/>',
        f'<path d="{shape}" fill="url(#{"leadg" if lead else "rowg"})"/>',
        f'<path d="{shape}" fill="none" stroke="{"#4A5536" if lead else C["line2"]}"/>',
        f'<path d="M13 1.5H{RW - 1.5}" stroke="#fff" stroke-opacity=".06"/>',
        f'<rect x="{COL_SLOT * 2}" y="14" width="1" height="48" fill="{C["line2"]}"/>',
        f'<text x="{COL_SLOT}" y="48" text-anchor="middle" class="cond" font-size="28" '
        f'{paint(C["accent"] if lead else C["dim"])}>{slot}</text>',
    ]
    if lead:
        out.append(f'<rect x="1" y="13" width="3" height="62" fill="{C["accent"]}"/>')
    return "".join(out)


def row_svg(slot: int, title: str, body: str, lead: bool = False) -> str:
    dl = .08 * (slot - 1)
    inner = (
        f'<g class="in-left" {d(dl)}>{plate(slot, lead)}</g>'
        f'<g class="in" {d(dl + .2)}>{body}</g>'
    )
    return svg(RW, RH, title, inner, css=ROW_CSS, defs=ROW_DEFS + (CARD_DEFS if lead else ""))


def signal(x, y, col) -> str:
    """Connection strength: four rising bars."""
    return "".join(f'<rect x="{x + k * 5}" y="{y - 4 - k * 3}" width="3" height="{4 + k * 3}" fill="{col}"/>' for k in range(4))


def calling_card(x, y, w, h) -> str:
    """The leader's calling card: a banner behind the name, as in the game's
    party list. Topographic rings (a nod to the briefing map) fade in from
    the left so the name always sits on clean ground."""
    cx, cy = x + w + 6, y + h * .15
    rings = []
    for k in range(1, 12):
        r = 4 + k * 17
        pts = []
        for j in range(73):
            t = j / 72 * 2 * math.pi
            rr = r * (1 + .1 * math.sin(3 * t + k * .7) + .06 * math.sin(5 * t - k * 1.3))
            pts.append(f"{cx + rr * math.cos(t):.1f} {cy + rr * .55 * math.sin(t):.1f}")
        minor = ' stroke-opacity=".13"' if k % 3 else ""  # every third ring is an index contour
        rings.append(f'<path d="M{"L".join(pts)}Z"{minor}/>')
    shape = chamfer(x, y, w, h, 8, ("tr", "bl"))
    return (
        f'<clipPath id="cardc"><path d="{shape}"/></clipPath>'
        f'<path d="{shape}" fill="url(#cardg)"/>'
        f'<g clip-path="url(#cardc)" mask="url(#cardm)" fill="none" stroke="{C["accent"]}" stroke-opacity=".3">{"".join(rings)}</g>'
        f'<path d="{shape}" fill="none" stroke="#fff" stroke-opacity=".07"/>'
    )


CARD_DEFS = f"""
<linearGradient id="cardg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#171D12"/><stop offset="1" stop-color="#121610"/>
</linearGradient>
<linearGradient id="cardf" x1="0" y1="0" x2="1" y2="0">
  <stop offset=".22" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity="1"/>
</linearGradient>
<mask id="cardm" maskContentUnits="userSpaceOnUse"><rect width="{W}" height="76" fill="url(#cardf)"/></mask>
"""


def leader_row(cfg, intel) -> str:
    clan = cfg.get("clan", "")
    tag = f"[{clan}]" if clan else ""
    name = (cfg.get("callsign") or cfg.get("login", "")).upper()
    chip_t = "PARTY LEADER"
    chip_w = round(mw(chip_t, 11, 1) + 31)
    ns = 28.0
    room = CARD_R - 12 - COL_NAME - chip_w - 14  # name line and chip stay on the card
    if cw(tag + " " + name, ns, .5) > room:
        ns = round(ns * room / cw(tag + " " + name, ns, .5), 1)
    tw = cw(tag + " ", ns) if tag else 0
    nw = cw(name, ns, .5)
    chip_x = round(COL_NAME + tw + nw + 14, 1)
    role = cfg.get("role", "").upper()
    sub_len = len(intel["rank"]) + 4 + len(role)
    sub_room = CARD_R - 12 - COL_NAME  # long ranks (Command Sergeant Major) tighten the tracking
    sub_ls = 1.4 if mw("x" * sub_len, 12, 1.4) <= sub_room else round(max(.2, sub_room / sub_len - 12 * .602), 2)
    lvl = str(intel["level"])
    pres = int(intel.get("prestige", 0))
    rx = CARD_R + 20
    right = [
        insignia(rx + 16, 38, int(intel["rank_tier"])),
        mono(rx + 44, 30, "LVL", 11, C["sub"], ls=1.2),
        ftext(rx + 43, 57, lvl, 30, .5, fill=C["text"]),
    ]
    if pres:
        px = round(rx + 44 + max(mw("LVL", 11, 1.2), cw(lvl, 30, .5)) + 24)
        right += [
            f'<rect x="{px - 12}" y="20" width="1" height="38" fill="{C["line2"]}"/>',
            mono(px, 30, "PRESTIGE", 11, C["sub"], ls=1.2),
            star(px + 8.5, 47.5, 9, "url(#goldm)"),
            ftext(px + 22, 57, roman(pres), 26, .5, fill=C["gold"]),
        ]
    crown = (f'<path d="M{chip_x + 8} {32}V{25}l3 3l2.5 -4l2.5 4l3 -3V{32}Z" fill="{C["bg"]}"/>')
    return "".join([
        calling_card(COL_ICON + 60, 10, CARD_R - COL_ICON - 60, 56),
        emblem(COL_ICON, 12),
        ftext(COL_NAME, 39, tag, ns, 0, fill=C["sub"]) if tag else "",
        ftext(round(COL_NAME + tw, 1), 39, name, ns, .5, fill=C["text"]),
        f'<g class="in-scale" {d(.55)}>'
        f'<rect x="{chip_x}" y="18" width="{chip_w}" height="21" fill="{C["gold"]}"/>{crown}'
        f'<text x="{chip_x + 23:.1f}" y="32.5" class="mono" font-size="11" font-weight="700" {paint(C["bg"])} '
        f'letter-spacing="1">{esc(chip_t)}</text></g>',
        mono(COL_NAME, 58, [(intel["rank"].upper(), C["sub"]), (" // ", C["dim"]), (role, C["sub"])], 12, ls=sub_ls),
        "".join(right),
        f'<rect x="{COL_RIGHT - 18}" y="14" width="1" height="48" fill="{C["line2"]}"/>',
        f'<g class="in-scale" {d(.7)}><rect x="{COL_RIGHT + 15}" y="27" width="22" height="22" fill="{C["accent"]}"/>'
        f'<path d="M{COL_RIGHT + 20} 38.5l4.5 4.5l8 -9" fill="none" stroke="{C["bg"]}" stroke-width="2.6"/></g>',
        ftext(COL_RIGHT + 49, 46, "READY", 22, 1.2, fill=C["accent"]),
        signal(RW - 52, 47, C["accent"]),
    ])


def open_row(kind: str, value: str, channel: str, cta: str, slot: int = 2) -> str:
    bx, by, bw, bh = COL_RIGHT, 16, RW - 24 - COL_RIGHT, 44
    a = C["accent"]
    room = bx - 24 - COL_NAME
    vs = 28.0 if cw(value, 28, .3) <= room else round(28 * room / cw(value, 28, .3), 1)
    return "".join([
        f'<rect x="{COL_ICON + .5}" y="12.5" width="51" height="51" fill="{C["panel"]}" stroke="{C["dim"]}" stroke-dasharray="4 3"/>',
        platform(kind, COL_ICON + 26, 38, C["sub"]),
        f'<path d="M{COL_ICON + 44} 15.5v8M{COL_ICON + 40} 19.5h8" stroke="{a}" stroke-width="1.8"/>',  # invite marker
        ftext(COL_NAME, 39, value, vs, .3, fill=C["text"]),
        mono(COL_NAME, 58, [("OPEN SLOT", C["accent2"]), (" // ", C["dim"]), (channel, C["sub"])], 12, ls=1.4),
        # call-to-action button, styled like ui.frame: chamfered with corner ticks
        f'<path d="{chamfer(bx, by, bw, bh, 9)}" fill="{a}" fill-opacity=".07" stroke="{a}" stroke-opacity=".55"/>',
        f'<path d="M{bx + bw - 12} {by + .5}H{bx + bw - .5}V{by + 12}M{bx + .5} {by + bh - 12}V{by + bh - .5}H{bx + 12}" '
        f'fill="none" stroke="{a}" stroke-width="1.8"/>',
        f'<clipPath id="bc"><path d="{chamfer(bx, by, bw, bh, 9)}"/></clipPath>'
        f'<g clip-path="url(#bc)"><path class="glint" {d(1.2 + .25 * (slot - 2))} d="M{bx - 70} {by + bh}L{bx - 48} {by}H{bx - 20}L{bx - 42} {by + bh}Z" fill="url(#glint)"/></g>',
        keycap(bx + 15, 27, glyph=G_ENTER),
        ftext(bx + 49, 46, cta, 22, 1.2, fill=a),
        f'<g class="nudge"><path d="M{bx + bw - 34} 32l6 6l-6 6M{bx + bw - 26} 32l6 6l-6 6" fill="none" stroke="{a}" stroke-width="2"/></g>',
    ])


# ---------------------------------------------------------------- footer

EXFIL_CSS = f"""
.wipe-r{{animation:in-wipe .8s cubic-bezier(.6,0,.2,1) backwards;transform-box:fill-box;transform-origin:right center}}
.wipe-l{{animation:in-wipe .8s cubic-bezier(.6,0,.2,1) backwards;transform-box:fill-box;transform-origin:left center}}
"""


def exfil(cfg, intel) -> str:
    H = 156
    cx = W / 2
    name = (cfg.get("callsign") or cfg.get("login", "")).upper()
    title = "EXFIL COMPLETE"
    size, ls = 48, 2
    tw = cw(title, size, ls)
    base = 80
    mid = base - size * .36  # optical middle of the caps
    gap = 30
    rl, rr = cx - tw / 2 - gap, cx + tw / 2 + gap
    stats = [(f'DAY {intel["day_number"]}', C["sub"]), (" // ", C["dim"]),
             (f'{intel["total"]:,} CONTRIBUTIONS', C["sub"]), (" // ", C["dim"]),
             (f'LVL {intel["level"]}', C["sub"])]
    back_w = mw("BACK TO TOP", 11, 1.8)
    body = [
        canvas(W, H),
        f'<ellipse cx="{cx}" cy="{mid:.1f}" rx="{tw * .75:.0f}" ry="44" fill="url(#halo)"/>',
        f'<path d="M36 {mid - 5:.1f}v11M{W - 36} {mid - 5:.1f}v11" stroke="{C["line2"]}"/>',
        f'<g class="in" {d(.05)}>{mono(cx, 30, stats, 11, ls=1.8, anchor="middle")}</g>',
        f'<g class="wipe-r" {d(.3)}><rect x="36" y="{mid:.1f}" width="{rl - 36:.1f}" height="1" fill="{C["line2"]}"/>'
        f'<rect x="{rl - 44:.1f}" y="{mid - 1:.1f}" width="44" height="3" fill="{C["accent"]}"/></g>',
        f'<g class="wipe-l" {d(.3)}><rect x="{rr:.1f}" y="{mid:.1f}" width="{W - 36 - rr:.1f}" height="1" fill="{C["line2"]}"/>'
        f'<rect x="{rr:.1f}" y="{mid - 1:.1f}" width="44" height="3" fill="{C["accent"]}"/></g>',
        f'<g class="in-scale" {d(.1)}>{ftext(cx, base, title, size, ls, fill=C["text"], anchor="middle")}</g>',
        f'<g class="in-up" {d(.45)}>{ftext(cx, base + 26, name + " OUT.", 20, 4, fill=C["sub"], anchor="middle")}</g>',
        f'<rect x="36" y="{H - 36}" width="{W - 72}" height="1" fill="{C["line"]}"/>',
        f'<g class="in" {d(.8)}>',
        f'<circle class="spin" cx="44" cy="{H - 18}" r="6" fill="none" stroke="{C["accent"]}" stroke-width="2" stroke-dasharray="26 12"/>',
        mono(58, H - 14, "PROGRESS SAVED", 11, C["sub"], ls=1.8),
        f'<g class="blink">{mono(cx, H - 13.5, "[ PRESS ANY KEY ]", 12, C["text"], ls=2.4, anchor="middle")}</g>',
        mono(W - 36, H - 14, "BACK TO TOP", 11, C["sub"], ls=1.8, anchor="end"),
        keycap(round(W - 36 - back_w - 32), H - 29, glyph=G_UP),
        "</g>",
    ]
    halo = (f'<radialGradient id="halo"><stop offset="0" stop-color="{C["accent"]}" stop-opacity=".07"/>'
            f'<stop offset="1" stop-color="{C["accent"]}" stop-opacity="0"/></radialGradient>')
    return svg(W, H, f"Exfil complete. {name} out.", "".join(body), css=EXFIL_CSS, defs=halo)


# ---------------------------------------------------------------- render

def render(cfg, intel):
    out = {}
    for i, (idx, label) in enumerate(TABS):
        active = i == 0
        out[f"tab-{label.lower()}.svg"] = svg(
            TW, TH, f"Menu tab {idx}: {label.title()}{' (selected)' if active else ''}",
            tab(i, idx, label, active), defs=TAB_DEFS)

    contact = cfg.get("contact", {})
    def bare(url):  # the address as a player would type it
        return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    linkedin, discord = bare(contact.get("linkedin", "")), bare(contact.get("discord", ""))
    slots = [
        ("email", contact.get("email", ""), "EMAIL", "SEND INVITE", "squad-email.svg"),
        ("linkedin", linkedin, "LINKEDIN", "CONNECT", "squad-linkedin.svg"),
        ("discord", discord, "DISCORD", "JOIN", "squad-discord.svg"),
    ]
    party = 1 + len(slots)
    ready_w = mw(f"1/{party} READY", 11, 2.4)
    pips = "".join(
        f'<rect x="{W - 36 - ready_w - 22 - (party - 1 - k) * 14:.1f}" y="57.5" width="8" height="8" '
        + (f'fill="{C["accent"]}"/>' if k == 0 else f'fill="none" stroke="{C["dim"]}"/>')
        for k in range(party))
    out["squad-header.svg"] = svg(
        W, 96, f"Squad: party lobby, 1 of {party} ready",
        canvas(W, 96)
        + mono(W - 36, 32, [("PARTY PRIVACY", C["sub"]), (" // ", C["dim"]), ("OPEN", C["accent"])], 11, ls=2.4, anchor="end")
        + header("05", "SQUAD", "PARTY LOBBY", right=f"1/{party} READY")
        + f'<g class="in" {d(.4)}>{pips}</g>', css=TEXT_CLASSES)

    name = (cfg.get("callsign") or cfg.get("login", "")).upper()
    out["squad-leader.svg"] = row_svg(
        1, f"Slot 1: [{cfg.get('clan', '')}] {name}, {intel['rank']}, level {intel['level']}, party leader, ready",
        leader_row(cfg, intel), lead=True)
    for n, (kind, value, channel, cta, fname) in enumerate(slots, start=2):
        out[fname] = row_svg(n, f"Slot {n}: open. {cta.title()} via {channel.title()}: {value}",
                             open_row(kind, value, channel, cta, n))

    out["exfil.svg"] = exfil(cfg, intel)
    return out
