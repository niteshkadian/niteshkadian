"""
Loadout: a Create-a-Class screen with a Gunsmith view.

Layout (viewBox 1000 x H)
  header      02 // LOADOUT  CREATE-A-CLASS                 CLASS 1 · <name>
  gunsmith    stage (left): the rifle in right profile, eight attachment
              callouts hung off named anchor points on the art
              panel (right): weapon name, type, chamber, camo, six stats
  class       row 1: secondary · lethal · tactical · field upgrade
              row 2: perk 1 · perk 2 · perk 3

The rifle is drawn from scratch in its own coordinates (butt at x=0, bore axis
at y=0, muzzle at x=640) and dropped into the stage with one translate, so the
callouts stay in register with the parts whatever the config says.

Timeline (seconds)
  0.0  header, stage and panel fade in
  0.3  the rifle resolves; a scan line sweeps the stage left to right
  0.6  callouts drop in as the scan passes their part; stat bars wipe in
  1.6  class cards rise in, left to right
  4.0  attachment points ping in sequence (decorative, hidden at rest)
"""
from __future__ import annotations

import math
import random

from ui import C, W, bar, canvas, chamfer, d, esc, fit, frame, header, svg

H = 768
SEED = 26

# stage (gunsmith viewport) and the weapon panel beside it
SX, SY, SW, SH = 36, 96, 700, 386
PX, PY, PW, PH = 748, 96, 216, 386
OX, OY = 66, 264            # where the rifle's origin lands on the canvas
SWEEP_T0, SWEEP_DUR, SWEEP_EASE = .35, 1.5, (.45, 0, .3, 1)   # the one-shot scan across the stage

# DIN Condensed Bold advance widths (em). COND text is squeezed to these
# lengths with textLength, so the layout holds with any fallback font.
CW = {
    "A": .407, "B": .426, "C": .407, "D": .426, "E": .37, "F": .37, "G": .426, "H": .426, "I": .204,
    "J": .333, "K": .426, "L": .37, "M": .556, "N": .444, "O": .426, "P": .407, "Q": .426, "R": .426,
    "S": .406, "T": .332, "U": .426, "V": .407, "W": .593, "X": .389, "Y": .388, "Z": .333, " ": .186,
    "-": .389, ".": .186, "·": .186, ":": .186, "/": .222, "&": .481, "+": .6, "'": .186, "(": .222,
    ")": .222, "#": .372, ",": .186, "_": .5,
}
MONO_EM = .6                # SF Mono / Menlo / Consolas advance


def cw(text: str, size: float) -> float:
    return sum(CW.get(ch, .372 if ch.isdigit() else .42) for ch in text) * size


def mw(text: str, size: float = 11, ls: float = 0) -> float:
    return len(text) * (size * MONO_EM + ls)


def cond(x, y, text, size, cls="", anchor="start", maxw=None, extra=""):
    """COND text pinned to its DIN width (or squeezed into maxw)."""
    w = cw(text, size)
    if maxw:
        w = min(w, maxw)
    return fit(x, y, text, size, round(w, 1), cls=f"cond {cls}".strip(), anchor=anchor, extra=extra)


def mono(x, y, text, size=11, cls="sub", anchor="start", ls=1.6, weight=700, maxw=None, extra=""):
    tl = ""
    if maxw and mw(text, size, ls) > maxw:
        tl = f' textLength="{maxw:.0f}" lengthAdjust="spacingAndGlyphs"'
    return (f'<text x="{x}" y="{y}" class="mono {cls}" font-size="{size}" font-weight="{weight}" '
            f'letter-spacing="{ls}" text-anchor="{anchor}"{tl} {extra}>{esc(text)}</text>')


def wrap(text: str, width: float, size: float = 13, em: float = .5):
    """Greedy wrap, then balance two-line results so there is no orphan word."""
    words, per = text.split(), size * em
    lines, cur = [], ""
    for wd in words:
        t = f"{cur} {wd}".strip()
        if len(t) * per <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    if len(lines) == 2:
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            if len(a) * per <= width and len(b) * per <= width:
                # even lines; never open a line on a separator; prefer breaking after ':' or '.'
                score = max(len(a), len(b)) + (40 if b[0] in "·-–—/" else 0) - (8 if a[-1] in ":." else 0)
                if best is None or score < best[0]:
                    best = (score, [a, b])
        if best:
            lines = best[1]
    return lines


# --------------------------------------------------------------------------
# defs: gunmetal, polymer, glass, camo
# --------------------------------------------------------------------------

EDGE = "#030404"
HI = "#B4BDB7"     # specular edge
RIM = "#9CC3D6"    # cool rim light on undersides


def _lin(id_, stops, x2=0, y2=1):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"{f" stop-opacity={chr(34)}{a}{chr(34)}" if a != 1 else ""}/>'
                for o, c, a in stops)
    return f'<linearGradient id="{id_}" x1="0" y1="0" x2="{x2}" y2="{y2}">{s}</linearGradient>'


def _camo() -> str:
    """Seamless splinter camo tile in slate and sky: the Tailwind palette, field issue."""
    rnd = random.Random(SEED)
    tw, th = 150, 72
    tones = ["#36495A", "#18222B", "#24404F", "#425666", "#121A21"]
    shapes = []
    for i in range(22):
        cx, cy = rnd.uniform(0, tw), rnd.uniform(0, th)
        ang = rnd.uniform(-.5, .5)
        L, T = rnd.uniform(18, 44), rnd.uniform(5, 13)
        ca, sa = math.cos(ang), math.sin(ang)
        k = rnd.uniform(.25, .75)
        pts = [(-L / 2, -T * k), (L / 2, -T / 2), (L / 2 - T, T / 2), (-L / 2 + rnd.uniform(0, T), T * (1 - k))]
        pts = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts]
        col = tones[i % len(tones)]
        for dx in (0, -tw):
            for dy in (0, -th):
                p = " ".join(f"{x + dx:.1f},{y + dy:.1f}" for x, y in pts)
                shapes.append(f'<polygon points="{p}" fill="{col}"/>')
    for i in range(9):
        x, y = rnd.uniform(0, tw - 6), rnd.uniform(0, th - 3)
        shapes.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{rnd.choice((3, 4, 6))}" height="1.6" fill="#38BDF8" opacity=".6"/>')
    return (f'<pattern id="camo" width="{tw}" height="{th}" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(-8)">{"".join(shapes)}</pattern>')


DEFS = "".join([
    _lin("mU", [(0, "#808A84", 1), (.05, "#5F6863", 1), (.22, "#454C48", 1), (.58, "#313734", 1), (.88, "#1E2321", 1), (1, "#131615", 1)]),
    _lin("mD", [(0, "#555D58", 1), (.08, "#373D3A", 1), (.55, "#202523", 1), (1, "#121514", 1)]),
    _lin("mP", [(0, "#575C4C", 1), (.06, "#43473A", 1), (.5, "#2E3128", 1), (1, "#191B16", 1)]),
    _lin("cyl", [(0, "#181C1A", 1), (.22, "#7C857F", 1), (.38, "#4B524E", 1), (.72, "#252A28", 1), (1, "#101312", 1)]),
    _lin("tooth", [(0, "#8A938D", 1), (.4, "#454C48", 1), (1, "#222725", 1)]),
    _lin("shade", [(0, "#FFFFFF", .16), (.12, "#FFFFFF", 0), (.55, "#000000", 0), (1, "#000000", .55)]),
    _lin("glass", [(0, "#2C6A70", .9), (.55, "#0F2F34", .95), (1, "#071416", .95)], x2=1, y2=1),
    '<linearGradient id="sheen" x1="0" y1="0" x2="1" y2=".35">'
    '<stop offset=".3" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".42" stop-color="#FFFFFF" stop-opacity=".07"/>'
    '<stop offset=".5" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".7" stop-color="#FFFFFF" stop-opacity="0"/>'
    '<stop offset=".76" stop-color="#FFFFFF" stop-opacity=".045"/><stop offset=".82" stop-color="#FFFFFF" stop-opacity="0"/>'
    '</linearGradient>',
    _lin("band", [(0, "#FFFFFF", 0), (.18, "#FFFFFF", .07), (.45, "#FFFFFF", .025), (.75, "#FFFFFF", .08), (1, "#FFFFFF", 0)], x2=1, y2=0),
    '<radialGradient id="floor"><stop offset="0" stop-color="#000" stop-opacity=".6"/>'
    '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>',
    _lin("sweep", [(0, C["accent"], 0), (.85, C["accent"], .10), (1, C["accent"], .55)], x2=1, y2=0),
    '<radialGradient id="spot" cx=".46" cy=".5" r=".62">'
    '<stop offset="0" stop-color="#1F2620"/><stop offset=".55" stop-color="#121612"/>'
    f'<stop offset="1" stop-color="{C["panel"]}" stop-opacity="0"/></radialGradient>',
    '<pattern id="stip" width="3.2" height="3.2" patternUnits="userSpaceOnUse">'
    '<circle cx="1" cy="1" r=".75" fill="#000" opacity=".55"/><circle cx="2.6" cy="2.6" r=".5" fill="#6E7671" opacity=".35"/></pattern>',
    _camo(),
])

CSS = f"""
text.sub{{fill:{C['sub']}}}text.dim{{fill:{C['dim']}}}text.acc{{fill:{C['accent']}}}
text.fr{{fill:{C['friend']}}}text.en{{fill:{C['enemy']}}}text.gold{{fill:{C['gold']}}}
.draw{{animation:draw .5s cubic-bezier(.4,0,.2,1) backwards}}
@keyframes draw{{from{{stroke-dasharray:0 1}}to{{stroke-dasharray:1 0}}}}
.sweep{{opacity:0;animation:sweep {SWEEP_DUR}s {SWEEP_T0}s cubic-bezier({','.join(map(str, SWEEP_EASE))})}}
@keyframes sweep{{0%{{opacity:0;transform:translateX(0)}}12%{{opacity:1}}88%{{opacity:1}}100%{{opacity:0;transform:translateX({SW - 60}px)}}}}
.ping{{opacity:0;animation:ping 8s ease-out infinite;transform-box:fill-box;transform-origin:center}}
@keyframes ping{{0%{{opacity:.9;transform:scale(1)}}7%{{opacity:0;transform:scale(2.8)}}100%{{opacity:0}}}}
.lead{{fill:none;stroke:{C['sub']};stroke-width:1;opacity:.75}}
"""


# --------------------------------------------------------------------------
# the rifle (local coordinates: butt x=0, bore y=0, muzzle tip x=L)
# --------------------------------------------------------------------------

def _rail(x0, x1, y, down=False, pitch=7.2):
    """Picatinny section: body plus tooth row (teeth up, or down for a bottom rail)."""
    body = (f'<rect x="{x0}" y="{y if down else y - 4}" width="{x1 - x0}" height="4" fill="#2A302D" stroke="{EDGE}" stroke-width=".8"/>')
    teeth, x = [], x0 + 2
    ty = y + 4 if down else y - 8
    while x + 4.4 <= x1 - 1:
        teeth.append(f"M{x:.1f} {ty}h4.4v4h-4.4Z")
        x += pitch
    return body + f'<path d="{"".join(teeth)}" fill="url(#tooth)" stroke="{EDGE}" stroke-width=".6"/>'


L = 640                                         # butt pad to muzzle tip
MAG_R, MAG_CX, MAG_CY, MAG_S = 230, 522, 54, 78  # magazine spine: an arc curving forward


def _mp(s, n=0.0):
    """Point on the curved magazine: s along its spine below the magwell, n toward the rear (+) or front (-)."""
    a = s / MAG_R
    r = MAG_R + n
    return MAG_CX - r * math.cos(a), MAG_CY + r * math.sin(a)


def _band(s0, s1, n0, n1) -> str:
    """Closed path of the curved strip between spine lengths s0..s1 and offsets n0 (rear) .. n1 (front)."""
    (ax, ay), (bx, by) = _mp(s0, n0), _mp(s1, n0)
    (cx, cy), (dx, dy) = _mp(s1, n1), _mp(s0, n1)
    r0, r1 = MAG_R + n0, MAG_R + n1
    return (f"M{ax:.1f} {ay:.1f}A{r0} {r0} 0 0 0 {bx:.1f} {by:.1f}L{cx:.1f} {cy:.1f}"
            f"A{r1} {r1} 0 0 1 {dx:.1f} {dy:.1f}Z")


def _seg(s, n0, n1) -> str:
    (ax, ay), (bx, by) = _mp(s, n0), _mp(s, n1)
    return f"M{ax:.1f} {ay:.1f}L{bx:.1f} {by:.1f}"


def rifle() -> tuple[str, dict]:
    """AR-pattern carbine, right side. Proportions follow a 14.5in carbine with a 13in free-float
    handguard (about 19 units to the inch): bore at y=0, rail top at y=-22."""
    e = f'stroke="{EDGE}" stroke-width="1" stroke-linejoin="round"'
    hi = f'fill="none" stroke="{HI}" stroke-width="1" stroke-linecap="round"'
    rim = f'fill="none" stroke="{RIM}" stroke-width="1" stroke-linecap="round" opacity=".28"'
    o = []

    # receiver extension (buffer tube), castle nut, end plate
    o.append(f'<rect x="100" y="-9" width="60" height="20" fill="url(#cyl)" {e}/>'
             f'<rect x="149" y="-11.5" width="10" height="25" rx="1" fill="url(#mD)" {e}/>'
             '<path d="M152.5 -11V13M155.5 -11V13" stroke="#0B0D0C" stroke-width="1"/>'
             f'<rect x="159" y="-13" width="6" height="28" fill="#2B302D" {e}/>'
             f'<path d="M113 -8.5H148" {hi} opacity=".35"/>')

    # collapsible stock: sleeve over the tube, concave toe, rubber pad
    stock = "M12 -16H94Q100 -16 104 -12.5L112 -10V14H97C71 21 37 37 21 57L12 60Z"
    o.append(f'<path d="{stock}" fill="url(#mP)" {e}/>'
             f'<path d="M13 -15.2H94Q99.5 -15.2 103.5 -11.8L111.2 -9.6" {hi} opacity=".42"/>'
             '<path d="M22 -9.5H100" stroke="#000" stroke-width="1" opacity=".3"/>'
             '<path d="M24 12H106" stroke="#0B0D0C" stroke-width="1" opacity=".7"/>'
             '<path d="M24 13H106" stroke="#6E7671" stroke-width=".6" opacity=".25"/>'
             '<path d="M86 21C67 26.5 47 36 34 46.5" fill="none" stroke="#0A0C0B" stroke-width="6" stroke-linecap="round"/>'
             '<path d="M86.5 23.8C67.5 29.2 48 38.6 35.6 48.6" fill="none" stroke="#69726C" stroke-width=".7" opacity=".35"/>'
             '<path d="M22 22V40" stroke="#0A0C0B" stroke-width="4.5" stroke-linecap="round"/>'
             f'<path d="M96.5 14.5C71 21.5 37.5 37.5 21.5 57" {rim}/>'
             f'<path d="M88 14H108L105 18.5H92Z" fill="#2B302D" {e}/>'
             f'<circle cx="104" cy="2" r="3" fill="#181B1A" {e}/><circle cx="104" cy="2" r="1.2" fill="{EDGE}"/>')
    o.append(f'<path d="M0 -12Q0 -18 6 -18H13V61H6Q0 61 0 55Z" fill="#141716" {e}/>'
             + "".join(f'<path d="M2.5 {y}H10.5" stroke="#262B28" stroke-width="1.4"/>' for y in range(-11, 58, 7))
             + f'<path d="M1 -12Q1 -17 6 -17H12" {hi} opacity=".3"/>')

    # pistol grip, raked back ~20 degrees, stippled
    grip = ("M212 28H180Q172 28 170 33Q169 37 174 39C172 53 167 70 162 84Q159 94 168 96L184 98"
            "Q190 98 191 92C194 76 200 58 205 44Q207 36 212 31Z")
    o.append(f'<path d="{grip}" fill="url(#mP)" {e}/>'
             '<path d="M181 43C179 57 175 72 171 87L185 89C188 74 193 59 198 45Z" fill="url(#stip)"/>'
             f'<path d="M174.5 40C172.5 54 167.5 71 162.5 85" {hi} opacity=".22"/>'
             '<path d="M163 89.5L190 93" stroke="#0B0D0C" stroke-width="1.1"/>'
             f'<path d="M168.5 95.5L184 97.5Q189 97.5 190.5 92" {rim}/>')

    # trigger guard + trigger
    tg = "M212 30V38Q212 46 220 46H254Q262 46 262 38V30"
    o.append(f'<path d="{tg}" fill="none" stroke="{EDGE}" stroke-width="5.5"/>'
             f'<path d="{tg}" fill="none" stroke="#353B38" stroke-width="3.4"/>'
             '<path d="M227 30C230 34 229.5 38 225.5 41.5L228.5 42.5C233 38 233.5 34 232 30Z" fill="#848D87" stroke="#050706" stroke-width=".8"/>')

    # magazine: polymer, curved forward, witness window showing the top of the stack
    rb, fb = _mp(MAG_S, 21), _mp(MAG_S, -21)
    mag = (f"M271 40V54A{MAG_R + 21} {MAG_R + 21} 0 0 0 {rb[0]:.1f} {rb[1]:.1f}"
           f"L{fb[0]:.1f} {fb[1]:.1f}A{MAG_R - 21} {MAG_R - 21} 0 0 1 313 54V40Z")
    o.append(f'<path d="{mag}" fill="url(#mP)" {e}/>'
             + "".join(f'<path d="{_seg(s, 20.5, -20.5)}" stroke="#0C0E0D" stroke-width="1.4"/>'
                       f'<path d="{_seg(s + 1.5, 20.5, -20.5)}" stroke="#58605B" stroke-width=".6" opacity=".55"/>'
                       for s in (4, 9.5, 15))
             + f'<path d="{_band(64, 75, 18, -18)}" fill="url(#stip)" stroke="#3A403D" stroke-width=".6"/>'
             f'<path d="{_band(22, 60, -6, -16)}" fill="#7A5A22" stroke="{EDGE}" stroke-width="1.2"/>'
             + "".join(f'<path d="{_seg(s, -6.5, -15.5)}" stroke="#3B2A0E" stroke-width="1.2"/>'
                       f'<path d="{_seg(s + 1.3, -6.5, -15.5)}" stroke="#E9C77A" stroke-width="1" opacity=".75"/>'
                       for s in (24.5, 30.5, 36.5, 42.5, 48.5, 54.5))
             + f'<path d="{_band(22, 60, -6, -16)}" fill="none" stroke="#000" stroke-width="1" opacity=".5"/>'
             f'<path d="M272 56A{MAG_R + 20} {MAG_R + 20} 0 0 0 {_mp(MAG_S - 2, 20)[0]:.1f} {_mp(MAG_S - 2, 20)[1]:.1f}" {hi} opacity=".16"/>'
             f'<path d="M312.4 56A{MAG_R - 20.4} {MAG_R - 20.4} 0 0 0 {_mp(MAG_S - 2, -20.4)[0]:.1f} {_mp(MAG_S - 2, -20.4)[1]:.1f}" {rim}/>')
    bx, by = _mp(MAG_S)
    ang = -math.degrees(MAG_S / MAG_R)
    o.append(f'<g transform="translate({bx:.1f} {by:.1f}) rotate({ang:.2f})">'
             f'<path d="M-23 -1.5H23Q26 -1.5 26.5 1.5L27 4.5Q27 8 23.5 8H-20Q-24 8 -24 4.5V1Q-24 -1.5 -23 -1.5Z" fill="url(#mD)" {e}/>'
             f'<path d="M-22 -.6H23.5" {hi} opacity=".4"/><path d="M-19 7.4H23" {rim}/>'
             '<path d="M-14 3.2H16" stroke="#0B0D0C" stroke-width="1" opacity=".7"/></g>')

    # lower receiver (buffer tower, fire-control housing, flared magwell)
    lower = "M164 -12H178V9H322L328 12V23Q328 27 324 28L322 50L318 54H266L262 50V30H182Q174 30 170 25L164 16Z"
    o.append(f'<path d="{lower}" fill="url(#mU)" {e}/>')
    # upper receiver
    upper = "M178 -14H322V9H178Z"
    o.append(f'<path d="{upper}" fill="url(#mU)" {e}/>')
    # free-float handguard: top bevel, flat, bottom bevel, chamfered nose
    hg = "M322 -14H568L574 -9V9L568 14H330L324 12L322 9Z"
    o.append(f'<path d="{hg}" fill="url(#mU)" {e}/>')

    # camo, studio shading and a soft diagonal sheen over receiver and handguard
    o.append(f'<clipPath id="rcv"><path d="{upper}"/><path d="{lower}"/><path d="{hg}"/></clipPath>')
    o.append('<g clip-path="url(#rcv)"><rect x="150" y="-30" width="440" height="100" fill="url(#camo)" opacity=".5"/>'
             '<rect x="160" y="-14" width="420" height="28" fill="url(#shade)"/>'
             '<rect x="160" y="9" width="162" height="46" fill="url(#shade)"/>'
             '<rect x="160" y="-14" width="420" height="68" fill="url(#sheen)"/>'
             '<rect x="178" y="-12.5" width="396" height="4" fill="url(#band)"/>'
             '<rect x="322" y="-14" width="252" height="5" fill="#FFFFFF" opacity=".05"/>'
             '<rect x="322" y="9" width="252" height="5" fill="#000" opacity=".3"/></g>')

    # receiver lines: parting line, joints, bevel breaks, rim light
    o.append('<path d="M178 9H322" stroke="#070908" stroke-width="1.3"/>'
             '<path d="M322 -14V12" stroke="#070908" stroke-width="1.4"/>'
             '<path d="M178 -14V9" stroke="#070908" stroke-width="1"/>'
             '<path d="M323 -9H572M323 9H572" stroke="#000" stroke-width=".8" opacity=".55"/>'
             f'<path d="M323 -8.2H572" stroke="{HI}" stroke-width=".6" opacity=".2"/>'
             '<path d="M567.5 -13.5V13.5" stroke="#070908" stroke-width="1"/>'
             f'<path d="M179 -13.3H321M323 -13.3H567" {hi} opacity=".5"/>'
             f'<path d="M331 13.5H567.5L573.5 8.5" {rim}/><path d="M183 29.5H262M267 53.5H317" {rim}/>'
             '<rect x="188" y="12" width="68" height="15" rx="2" fill="#000" opacity=".12"/>')
    # ejection port + dust cover, brass deflector, forward assist, charging handle
    o.append(f'<rect x="228" y="-7" width="42" height="11" rx="1" fill="#1A1D1C" {e}/>'
             '<path d="M230 -1.5H268" stroke="#3E4541" stroke-width="1.2"/>'
             f'<path d="M229.5 -6H268.5" {hi} opacity=".22"/>'
             '<path d="M226 6.5H272" stroke="#59615C" stroke-width="1.1"/>'
             f'<path d="M210 -14H226V-1Q217 -3 212 -10Z" fill="#3D4440" {e}/>'
             f'<path d="M211 -13H225" {hi} opacity=".5"/>'
             f'<circle cx="195" cy="-1" r="6.5" fill="url(#mD)" {e}/>'
             '<circle cx="195" cy="-1" r="3.4" fill="#191C1B" stroke="#4E5651" stroke-width=".7"/>'
             f'<path d="M190.4 -5.6A6.5 6.5 0 0 1 199.6 -5.6" {hi} opacity=".45"/>'
             f'<path d="M157 -14H180V-9H161Q157 -9 157 -11.5Z" fill="#2C312E" {e}/>'
             f'<path d="M158 -13.3H179" {hi} opacity=".35"/>')
    # lower detail: magwell lip, pins, selector, mag release, roll mark
    o.append('<path d="M263 50H321" stroke="#4A524D" stroke-width=".8" opacity=".6"/>'
             + "".join(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#0E100F" stroke="#59615C" stroke-width=".7"/>'
                       for x, y, r in ((171, 3, 2.4), (325, 17, 2.4), (214, 19, 1.7), (230, 21, 1.7)))
             + f'<path d="M188 14.2L201 12.5Q203 14.5 201 16.3L188 19.8Z" fill="#59615C" {e}/>'
             f'<circle cx="188" cy="17" r="4.2" fill="#1B1F1D" {e}/>'
             f'<circle cx="254" cy="20" r="3.6" fill="url(#mD)" {e}/>'
             '<path d="M248.5 15.5A7 7 0 0 0 248.5 24.5" fill="none" stroke="#000" stroke-width="1" opacity=".4"/>'
             f'<text x="292" y="46" class="mono" font-size="11" font-weight="700" text-anchor="middle" fill="#9AA39D" '
             f'opacity=".42" letter-spacing="1">NK-26</text>')

    # M-LOK slots: side flat and bottom bevel
    o.append("".join(f'<rect x="{342 + i * 31}" y="-3" width="24" height="6" rx="3" fill="#070908"/>'
                     f'<path d="M{345 + i * 31} 3.6H{363 + i * 31}" stroke="#7A837D" stroke-width=".8" opacity=".45"/>'
                     for i in range(7))
             + "".join(f'<rect x="{347 + i * 31}" y="10.2" width="14" height="2.6" rx="1.3" fill="#070908"/>'
                       for i in range(7)))

    # full-length top rail, broken at the upper / handguard joint
    o.append(_rail(178, 320, -14) + _rail(324, 572, -14))

    # angled foregrip on the handguard's bottom face
    afg = "M428 14H516L518 18Q514 32 502 41Q497 44 490 43L434 20Q428 17 428 14Z"
    o.append(f'<path d="{afg}" fill="url(#mP)" {e}/>'
             '<path d="M448 18.5L486 34M462 18.5L494 31.5M476 18.5L502 29" stroke="#0C0E0D" stroke-width="1.3" stroke-linecap="round"/>'
             '<path d="M448.5 20L486.5 35.5M462.5 20L494.5 33M476.5 20L502.5 30.5" stroke="#5E6661" stroke-width=".6" opacity=".45"/>'
             f'<path d="M429 15H515" {hi} opacity=".3"/><path d="M517.5 18.5Q513.5 32 502 40.5Q497 43.5 490 42.5L435 20" {rim}/>')

    # barrel stub, shim, muzzle brake
    o.append(f'<rect x="574" y="-5" width="24" height="10" fill="url(#cyl)" {e}/>'
             f'<rect x="597" y="-7.5" width="4" height="15" fill="#1A1D1C" {e}/>'
             f'<path d="M601 -8.5H634L640 -5V5L634 8.5H601Z" fill="url(#mD)" {e}/>'
             + "".join(f'<rect x="{x}" y="-6" width="5" height="12" rx="1" fill="#060807"/>' for x in (607, 616, 625))
             + f'<path d="M602 -7.6H633.5L638.6 -4.6" {hi} opacity=".55"/><path d="M602 8H633.5" {rim}/>')

    # holographic sight on the upper's rail
    o.append(f'<path d="M226 -28H302V-22H226Z" fill="url(#mD)" {e}/>'
             f'<path d="M288 -26.6L299 -27.2Q301.5 -25 299 -23.4L288 -24Z" fill="#5A625D" {e}/>'
             f'<rect x="228" y="-41" width="74" height="13" rx="2" fill="url(#mD)" {e}/>'
             f'<rect x="231" y="-48" width="21" height="9" rx="2" fill="url(#mD)" {e}/>'
             '<rect x="234" y="-37.5" width="7" height="5" rx="1.5" fill="#0F1211" stroke="#4E5651" stroke-width=".6"/>'
             '<rect x="243" y="-37.5" width="7" height="5" rx="1.5" fill="#0F1211" stroke="#4E5651" stroke-width=".6"/>'
             '<rect x="257" y="-64" width="40" height="24" fill="url(#glass)"/>'
             '<path d="M260 -64L273 -64L263 -40L259 -40Z" fill="#FFFFFF" opacity=".09"/>'
             '<path d="M277 -64L281.5 -64L271.5 -40L268.5 -40Z" fill="#FFFFFF" opacity=".05"/>'
             f'<circle cx="277" cy="-52" r="9.5" fill="{C["enemy"]}" opacity=".07"/>'
             f'<circle cx="277" cy="-52" r="6.5" fill="none" stroke="{C["enemy"]}" stroke-width=".9" opacity=".9"/>'
             f'<path d="M277 -60.5V-58M277 -46V-43.5M268.5 -52H271M283 -52H285.5" stroke="{C["enemy"]}" stroke-width=".9" opacity=".9"/>'
             f'<circle cx="277" cy="-52" r="1.3" fill="{C["enemy"]}"/>'
             f'<path d="M252 -40V-64Q252 -69 257 -69H297Q302 -69 302 -64V-40H297V-64H257V-40Z" fill="url(#mD)" {e}/>'
             f'<path d="M253.5 -64Q253.5 -67.5 257 -67.5H297" {hi} opacity=".7"/>'
             f'<path d="M229 -40H251M298 -40H301" {hi} opacity=".35"/>'
             f'<path d="M232 -47H251" {hi} opacity=".3"/>')

    mx, my = bx + 3.5 * math.sin(math.radians(-ang)), by + 3.5 * math.cos(math.radians(ang))
    ax, ay = _mp(41, -11)
    anchors = {
        # name: (dot x, dot y, row, flag direction, waypoint x or None)
        "STOCK": (58, -7, "up", 1, None),
        "OPTIC": (277, -66.5, "up", 1, None),
        "BARREL": (470, -11.5, "up", 1, None),
        "MUZZLE": (619, 0, "up", -1, None),
        "REAR GRIP": (178, 88, "down", -1, None),
        "MAGAZINE": (round(mx, 1), round(my, 1), "down", -1, None),
        "AMMUNITION": (round(ax, 1), round(ay, 1), "down", 1, 352),
        "UNDERBARREL": (490, 33, "down", 1, None),
    }
    return "".join(o), anchors


# --------------------------------------------------------------------------
# small icons for the class row (local coords, ~0..64 x 0..48)
# --------------------------------------------------------------------------

def pistol() -> str:
    """Striker-fired service pistol, right side: slide, polymer frame with rail, raked grip."""
    e = f'stroke="{EDGE}" stroke-width="1" stroke-linejoin="round"'
    hi = f'fill="none" stroke="{HI}" stroke-width=".9" stroke-linecap="round"'
    rim = f'fill="none" stroke="{RIM}" stroke-width=".9" opacity=".3"'
    grip = "M50 38C48 50 44 62 40 72L39 75H8L7 72C9 62 12 52 15 41Q11 38 8 34Q7 30 12 30H50Z"
    tg = "M50 40V49Q50 55 56 55H74Q79 55 80 50L82 40"
    return (
        f'<path d="{grip}" fill="url(#mP)" {e}/>'
        '<path d="M20 44H44C42 54 39 63 36 70H13C15 61 17 52 20 44Z" fill="url(#stip)"/>'
        f'<path d="M14.5 42C12 52 9.5 62 7.8 71" {hi} opacity=".25"/>'
        f'<path d="M5 74H42L41 80H8Q4.5 80 5 77Z" fill="url(#mD)" {e}/><path d="M8 79.5H40" {rim}/>'
        f'<path d="{tg}" fill="none" stroke="{EDGE}" stroke-width="4.6"/>'
        f'<path d="{tg}" fill="none" stroke="#3A403D" stroke-width="2.8"/>'
        '<path d="M60 40C62 43 62 47 59 50L61.5 51C65 47 65 43 64 40Z" fill="#848D87" stroke="#050706" stroke-width=".7"/>'
        f'<path d="M12 29H109V37L105 41H50V36Q50 33 46 33H12Z" fill="#2E322B" {e}/>'
        + "".join(f'<rect x="{84 + k * 5}" y="37.5" width="2.6" height="3" fill="#0B0D0C"/>' for k in range(4))
        + f'<path d="M13 30H108" stroke="#000" stroke-width="1" opacity=".6"/>'
        f'<rect x="70" y="31" width="7" height="3" rx="1" fill="#59615C"/>'
        f'<circle cx="30" cy="35" r="1.6" fill="#0E100F" stroke="#535B56" stroke-width=".6"/>'
        f'<path d="M6 12Q6 10 8 10H112L116 14V29H6Z" fill="url(#mU)" {e}/>'
        f'<path d="M7 11.2H111.5" {hi} opacity=".6"/><path d="M7 15H115" stroke="#000" stroke-width=".8" opacity=".35"/>'
        + "".join(f'<path d="M{12 + k * 4} 16.5V27" stroke="#0B0D0C" stroke-width="1.6"/>' for k in range(6))
        + "".join(f'<path d="M{94 + k * 4} 16.5V27" stroke="#0B0D0C" stroke-width="1.6"/>' for k in range(3))
        + f'<rect x="56" y="13" width="24" height="9" fill="#101312" {e}/>'
        f'<rect x="57.5" y="14.5" width="21" height="6" fill="url(#cyl)"/>'
        f'<path d="M9 10V6.5H19V10M105 10V7.5H110V10" fill="#2B302D" {e}/>'
        f'<rect x="115.5" y="16" width="3.5" height="9" fill="url(#cyl)" {e}/>'
        f'<path d="M7 28.4H115" {rim}/>'
    )


def c4() -> str:
    e = f'stroke="{EDGE}" stroke-width="1" stroke-linejoin="round"'
    return (
        f'<rect x="2" y="16" width="58" height="28" rx="2" fill="#4A4F3C" {e}/>'
        '<rect x="2" y="16" width="58" height="9" rx="2" fill="#FFFFFF" opacity=".08"/>'
        '<rect x="2" y="36" width="58" height="8" fill="#000" opacity=".25"/>'
        '<rect x="12" y="16" width="7" height="28" fill="#23261D"/><rect x="43" y="16" width="7" height="28" fill="#23261D"/>'
        f'<rect x="20" y="6" width="20" height="11" rx="1.5" fill="url(#mD)" {e}/>'
        '<path d="M36 6L44 -2" stroke="#8A938D" stroke-width="1.4" stroke-linecap="round"/>'
        f'<circle class="blink" cx="25.5" cy="11.5" r="2.2" fill="{C["enemy"]}"/>'
        '<path d="M31 11.5H37" stroke="#4A514D" stroke-width="1.2"/>'
    )


def stim() -> str:
    e = f'stroke="{EDGE}" stroke-width="1" stroke-linejoin="round"'
    return (
        '<g transform="rotate(-24 32 24)">'
        '<path d="M50 24H64" stroke="#B5BDB7" stroke-width="1.4" stroke-linecap="round"/>'
        f'<rect x="44" y="20" width="7" height="8" fill="#2B302D" {e}/>'
        f'<rect x="8" y="16" width="38" height="16" rx="3" fill="url(#mU)" {e}/>'
        f'<rect x="16" y="20" width="20" height="8" rx="1" fill="{C["accent"]}" opacity=".85"/>'
        '<rect x="16" y="20" width="20" height="3" fill="#FFFFFF" opacity=".25"/>'
        f'<rect x="38" y="16" width="4" height="16" fill="{C["gold"]}"/>'
        f'<rect x="0" y="19" width="9" height="10" rx="2" fill="url(#mD)" {e}/>'
        '</g>'
    )


def trophy() -> str:
    e = f'stroke="{EDGE}" stroke-width="1" stroke-linejoin="round"'
    return (
        f'<path d="M12 8Q32 -6 52 8" fill="none" stroke="{C["accent"]}" stroke-width="1.4" stroke-dasharray="3 3" opacity=".8"/>'
        f'<path d="M20 12.5Q32 4 44 12.5" fill="none" stroke="{C["accent"]}" stroke-width="1.4" opacity=".55"/>'
        '<path d="M18 36L8 46M32 38V47M46 36L56 46" stroke="#6E7671" stroke-width="2.4" stroke-linecap="round"/>'
        f'<rect x="14" y="26" width="36" height="13" rx="2" fill="url(#mU)" {e}/>'
        f'<path d="M20 26Q20 14 32 14Q44 14 44 26Z" fill="url(#mD)" {e}/>'
        f'<rect x="28" y="18" width="8" height="5" rx="1" fill="url(#glass)" stroke="#3E4642" stroke-width=".6"/>'
        f'<circle cx="21" cy="32.5" r="1.8" fill="{C["accent"]}"/>'
    )


def hexagon(cx, cy, r, col) -> str:
    def pts(rr):
        return " ".join(f"{cx + rr * math.cos(math.radians(a)):.1f},{cy + rr * math.sin(math.radians(a)):.1f}"
                        for a in range(-90, 270, 60))
    return (f'<polygon points="{pts(r)}" fill="{C["panel2"]}" stroke="{col}" stroke-width="1.6"/>'
            f'<polygon points="{pts(r - 5)}" fill="{col}" fill-opacity=".1" stroke="{col}" stroke-opacity=".35"/>')


def glyph(name: str, idx: int, cx, cy, col) -> str:
    n = name.upper()
    g = f'transform="translate({cx} {cy})"'
    if "OVERKILL" in n or "DOUBLE" in n:
        b = "M{x} 10V-3Q{x} -9 {m} -13Q{r} -9 {r} -3V10Z"
        return (f'<g {g} fill="{col}">'
                + "".join(f'<path d="{b.format(x=x, m=x + 3.5, r=x + 7)}"/><rect x="{x - .8}" y="11" width="8.6" height="2.4"/>'
                          for x in (-10, 3)) + "</g>")
    if "COLD" in n or "GHOST" in n:
        arms = "".join(f'<g transform="rotate({a})"><path d="M0 -13V13M-3.5 -10L0 -6.5L3.5 -10M-3.5 10L0 6.5L3.5 10"/></g>'
                       for a in (0, 60, 120))
        return f'<g {g} fill="none" stroke="{col}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{arms}</g>'
    if "AMPED" in n or "FAST" in n:
        return f'<path {g} d="M2.5 -14L-8 2H-1L-3.5 14L8 -3H1Z" fill="{col}"/>'
    return (f'<path {g} d="M-9 -2L0 -9L9 -2M-9 6L0 -1L9 6" fill="none" stroke="{col}" stroke-width="2.6" '
            f'stroke-linejoin="miter"/>')


ICON_BOX = {"c4": (2, -3, 60, 45), "stim": (-1, 3, 65, 45), "trophy": (7, -3, 57, 48)}


def place(fn, right, top, h):
    """Scale an icon to a zone height and right-align it, centred vertically."""
    x0, y0, x1, y1 = ICON_BOX[fn.__name__]
    s = min(1.0, h / (y1 - y0))
    tx, ty = right - x1 * s, top + (h - (y1 - y0) * s) / 2 - y0 * s
    return f'<g transform="translate({tx:.1f} {ty:.1f}) scale({s:.3f})">{fn()}</g>'


# --------------------------------------------------------------------------
# panel
# --------------------------------------------------------------------------

def _callout(name, value, ax, ay, row, side, via, delay, ping_delay):
    """Leader from a dot on the part to a flag label above or below the rifle."""
    R_UP, R_DN = 178, 428
    px, py = OX + ax, OY + ay
    vw = cw(value, 20)
    lw = mw(name, 11, 1.6)
    w = max(vw, lw) + 6
    rule_y = R_UP if row == "up" else R_DN
    sx = px if via is None else OX + via
    # leader
    pts = [(px, py)]
    if via is not None:
        pts.append((sx, py))
    pts.append((sx, rule_y))
    path = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    x0, x1 = (sx, sx + w) if side > 0 else (sx - w, sx)
    tx, anchor = (sx, "start") if side > 0 else (sx, "end")
    if row == "up":
        ly, vy = rule_y - 27, rule_y - 7
    else:
        ly, vy = rule_y + 19, rule_y + 40
    tab = (f'<rect x="{x0 if side > 0 else x1 - 14}" y="{rule_y - 1}" width="14" height="2" fill="{C["accent"]}"/>')
    return (
        f'<g class="in" {d(delay)}>'
        f'<path class="lead draw" pathLength="1" {d(delay)} d="{path}"/>'
        f'<path d="M{x0:.1f} {rule_y}H{x1:.1f}" stroke="{C["line2"]}" stroke-width="1"/>{tab}'
        + mono(tx, ly, name, 11, "sub", anchor, ls=1.6)
        + cond(tx, vy, value, 20, anchor=anchor)
        + "</g>"
        f'<g class="in-scale" {d(delay - .1)}><circle cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="{C["bg"]}" fill-opacity=".6" '
        f'stroke="{C["accent"]}" stroke-width="1.2"/><circle cx="{px:.1f}" cy="{py:.1f}" r="2.2" fill="{C["text"]}"/></g>'
        f'<circle class="ping" {d(ping_delay)} cx="{px:.1f}" cy="{py:.1f}" r="5.5" fill="none" stroke="{C["accent"]}" stroke-width="1.2"/>'
    )


def _scan_time(x: float) -> float:
    """When the scan line reaches canvas x: invert the sweep's cubic-bezier so callouts land in sync."""
    x1, y1, x2, y2 = SWEEP_EASE
    f = max(0.0, min(1.0, (x - (SX + 59.75)) / (SW - 60)))

    def bz(t, a, b):
        return 3 * a * t * (1 - t) ** 2 + 3 * b * t * t * (1 - t) + t ** 3

    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bz(mid, y1, y2) < f else (lo, mid)
    return SWEEP_T0 + SWEEP_DUR * bz(lo, x1, x2)


def _stage(prim, wildcard) -> str:
    out = [frame(SX, SY, SW, SH, c=12, fill=C["panel"], ticks=False)]
    out.append(f'<path d="{chamfer(SX + 1, SY + 1, SW - 2, SH - 2, 11)}" fill="url(#spot)"/>')
    # corner brackets + centre marks: a clinical viewport
    b = []
    for (x, y, dx, dy) in ((SX + 14, SY + 14, 1, 1), (SX + SW - 14, SY + 14, -1, 1),
                           (SX + 14, SY + SH - 14, 1, -1), (SX + SW - 14, SY + SH - 14, -1, -1)):
        b.append(f"M{x} {y + 12 * dy}V{y}H{x + 12 * dx}")
    out.append(f'<path d="{"".join(b)}" fill="none" stroke="{C["dim"]}" stroke-width="1"/>')
    cy = OY
    out.append(f'<path d="M{SX + 14} {cy}h8M{SX + SW - 22} {cy}h8" stroke="{C["dim"]}"/>')
    # top bar: breadcrumb + badge
    out.append(f'<g class="in" {d(.2)}>'
               + mono(SX + 30, SY + 30, "GUNSMITH", 11, "acc", ls=2.4)
               + mono(SX + 30 + mw("GUNSMITH", 11, 2.4) + 10, SY + 30, "// PRIMARY", 11, "dim", ls=2.4)
               + "</g>")
    n = len(prim["attachments"])
    cap = 8 if wildcard.upper() == "GUNFIGHTER" else 5
    left = f"{n}/{max(cap, n)}"
    rest = f"ATTACHMENTS · WILDCARD: {wildcard.upper()}"
    lw_, rw_ = mw(left, 11, 1) + 16, mw(rest, 11, 1) + 18
    bx = SX + SW - 30 - lw_ - rw_
    out.append(f'<g class="in" {d(.3)}>'
               f'<rect x="{bx:.1f}" y="{SY + 16}" width="{lw_:.1f}" height="20" fill="{C["accent"]}"/>'
               f'<text x="{bx + 8:.1f}" y="{SY + 30}" class="mono" font-size="11" font-weight="700" fill="{C["bg"]}" letter-spacing="1">{esc(left)}</text>'
               f'<rect x="{bx + lw_:.1f}" y="{SY + 16.5}" width="{rw_:.1f}" height="19" fill="{C["panel2"]}" stroke="{C["accent2"]}" stroke-width="1"/>'
               f'<text x="{bx + lw_ + 9:.1f}" y="{SY + 30}" class="mono" font-size="11" font-weight="700" letter-spacing="1">{esc(rest)}</text>'
               "</g>")

    art, anchors = rifle()
    # soft floor shadow under the rifle
    out.append(f'<ellipse cx="{OX + L / 2:.0f}" cy="{OY + 150}" rx="310" ry="12" fill="url(#floor)"/>')
    out.append(f'<g class="in" {d(.25)}><g transform="translate({OX} {OY})">{art}</g></g>')
    # scan line sweeping the stage once (decorative)
    out.append(f'<g class="sweep"><rect x="{SX + 4}" y="{SY + 48}" width="56" height="{SH - 62}" fill="url(#sweep)"/>'
               f'<rect x="{SX + 59}" y="{SY + 48}" width="1.5" height="{SH - 62}" fill="{C["accent"]}" opacity=".8"/></g>')

    # callouts, revealed as the scan passes their part
    fallback = [(60 + i * 70, -30, "up", 1, None) for i in range(8)]
    order = []
    for i, (slot, val) in enumerate(prim["attachments"][:8]):
        a = anchors.get(slot.upper(), fallback[i])
        order.append((slot.upper(), val, a))
    seq = sorted(range(len(order)), key=lambda k: order[k][2][0])
    for rank, k in enumerate(seq):
        slot, val, (ax, ay, row, side, via) = order[k]
        delay = _scan_time(OX + ax) + .05
        out.append(_callout(slot, val.upper(), ax, ay, row, side, via, delay, 4 + rank))
    return "".join(out)


def _panel(prim) -> str:
    x, y, w = PX, PY, PW
    ix, iw = x + 18, w - 36
    out = [f'<g class="in-right" {d(.15)}>', frame(x, y, w, PH, c=12, fill=C["panel"])]
    out.append(mono(ix, y + 30, "PRIMARY WEAPON", 11, "sub", ls=2.4))
    name = prim["name"].upper()
    model, _, variant = name.partition(" ")
    out.append(cond(ix - 1, y + 92, model, 64, maxw=iw))
    if variant:
        out.append(cond(ix, y + 122, variant, 30, cls="acc", maxw=iw))
    out.append(mono(ix, y + 146, prim["type"].upper(), 11, "sub", ls=2.4, maxw=iw))
    out.append(f'<rect x="{ix}" y="{y + 160}" width="{iw}" height="1" fill="{C["line2"]}"/>')
    ch = f"CHAMBERED IN {prim['chamber'].upper()}"
    out.append(f'<path d="M{ix} {y + 176}h6l3 4-3 4h-6z" fill="{C["accent"]}"/>')
    out.append(mono(ix + 15, y + 184, ch, 11, "", ls=1, maxw=iw - 15))
    sw_ = (f'<rect x="{ix}" y="{y + 193}" width="11" height="11" fill="#18222B"/>'
           f'<path d="M{ix} {y + 196}l7 -3h4v4l-11 3zM{ix + 3} {y + 204}l8 -5v5z" fill="#425666"/>'
           f'<rect x="{ix + 2}" y="{y + 200}" width="3" height="1.6" fill="#38BDF8"/>'
           f'<rect x="{ix}" y="{y + 193}" width="11" height="11" fill="none" stroke="{C["line2"]}"/>')
    out.append(sw_)
    out.append(mono(ix + 15, y + 203, f"CAMO: {prim['camo'].upper()}", 11, "", ls=1, maxw=iw - 15))
    out.append(f'<rect x="{ix}" y="{y + 218}" width="{iw}" height="1" fill="{C["line2"]}"/>')
    out.append("</g>")
    # stats
    sy = y + 244
    for i, (label, val) in enumerate(prim["stats"][:6]):
        ry = sy + i * 24
        out.append(f'<g class="in" {d(.6 + i * .08)}>'
                   + mono(ix, ry, label.upper(), 11, "sub", ls=1.6)
                   + cond(ix + iw, ry + 1, str(val), 18, anchor="end")
                   + "</g>")
        out.append(bar(ix, ry + 6, iw, val / 100, delay=.7 + i * .08, h=4))
        out.append(f'<path d="{"".join(f"M{ix + iw * k / 10:.1f} {ry + 6}v4" for k in range(1, 10))}" stroke="{C["panel"]}" stroke-width="1.5"/>')
    return "".join(out)


def _card(x, y, w, h, label, idx="") -> str:
    out = [f'<path d="{chamfer(x, y, w, h, 9)}" fill="{C["panel"]}" stroke="{C["line2"]}"/>',
           f'<rect x="{x}" y="{y + 12}" width="2" height="14" fill="{C["accent"]}"/>',
           mono(x + 14, y + 23, label, 11, "sub", ls=2.4)]
    if idx:
        out.append(mono(x + w - 14, y + 23, idx, 11, "dim", "end", ls=1.6))
    return "".join(out)


def _class(cfg) -> str:
    lo = cfg["loadout"]
    out = []
    y1, h1 = 496, 144
    # secondary
    sec = lo["secondary"]
    x, w = 36, 304
    g = [_card(x, y1, w, h1, "SECONDARY")]
    g.append(f'<g transform="translate({x + 16} {y1 + 34}) scale(.86)">{pistol()}</g>')
    tx = x + 138
    g.append(cond(tx, y1 + 68, sec["name"].upper(), 26, maxw=w - 152))
    g.append(mono(tx, y1 + 88, f"CHAMBERED IN {sec['chamber'].upper()}", 11, "sub", ls=1, maxw=w - 152))
    cx = x + 14
    for a in sec.get("attachments", [])[:5]:
        t = a.upper()
        cwid = mw(t, 11, 1) + 14
        if cx + cwid > x + w - 14:
            break
        g.append(f'<rect x="{cx:.1f}" y="{y1 + 112}" width="{cwid:.1f}" height="18" fill="{C["panel2"]}" stroke="{C["line2"]}"/>'
                 + mono(cx + 7, y1 + 125, t, 11, "", ls=1))
        cx += cwid + 6
    out.append(f'<g class="in-up" {d(1.5)}>{"".join(g)}</g>')

    # equipment
    eq = [("LETHAL", lo["lethal"], c4, True), ("TACTICAL", lo["tactical"], stim, False),
          ("FIELD UPGRADE", lo["field_upgrade"], trophy, False)]
    for i, (label, item, icon, is_cmd) in enumerate(eq):
        ex, ew = 352 + i * 208, 196
        g = [_card(ex, y1, ew, h1, label)]
        g.append(place(icon, ex + ew - 18, y1 + 34, 42))
        g.append(cond(ex + 14, y1 + 98, item["name"].upper(), 26, maxw=ew - 28))
        if is_cmd:
            g.append(mono(ex + 14, y1 + 120, item["line"], 13, "sub", ls=0, weight=400, maxw=ew - 28))
        else:
            for j, ln in enumerate(wrap(item["line"], ew - 28)[:2]):
                g.append(f'<text x="{ex + 14}" y="{y1 + 120 + j * 16}" class="sub" font-size="13">{esc(ln)}</text>')
        out.append(f'<g class="in-up" {d(1.6 + i * .1)}>{"".join(g)}</g>')

    # perks
    y2, h2 = 652, 96
    cols = [C["friend"], C["enemy"], C["gold"]]
    for i, p in enumerate(lo["perks"][:3]):
        px, pw = 36 + i * 314, 300
        col = cols[i % 3]
        g = [f'<path d="{chamfer(px, y2, pw, h2, 9)}" fill="{C["panel"]}" stroke="{C["line2"]}"/>']
        g.append(hexagon(px + 46, y2 + h2 / 2, 30, col))
        g.append(glyph(p["name"], i, px + 46, y2 + h2 / 2, col))
        tx = px + 92
        g.append(mono(tx, y2 + 26, f"PERK {i + 1}", 11, "sub", ls=2.4))
        g.append(cond(tx, y2 + 52, p["name"].upper(), 24, maxw=pw - 106))
        lines = wrap(p["line"], pw - 106)
        for j, ln in enumerate(lines[:2]):
            g.append(f'<text x="{tx}" y="{y2 + 72 + j * 16}" class="sub" font-size="13">{esc(ln)}</text>')
        out.append(f'<g class="in-up" {d(1.9 + i * .1)}>{"".join(g)}</g>')
    return "".join(out)


def render(cfg, intel):
    lo = cfg["loadout"]
    prim = lo["primary"]
    body = (
        canvas(W, H)
        + header("02", "LOADOUT", "CREATE-A-CLASS", right="CLASS 1 · " + lo["class_name"].upper())
        + _stage(prim, lo.get("wildcard", ""))
        + _panel(prim)
        + _class(cfg)
    )
    title = f"Loadout: {prim['name']}, {prim['type'].lower()} with {len(prim['attachments'])} attachments"
    return {"loadout.svg": svg(W, H, title, body, css=CSS, defs=DEFS)}
