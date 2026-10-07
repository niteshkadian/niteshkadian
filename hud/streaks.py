"""
Killstreaks panel: streak rewards unlocked by consecutive days of contributions.

Five reward cards from cfg["killstreaks"] (earned when intel.longest_streak
reaches the card's day count), then a segmented streak tracker in the style of
the in-match killstreak HUD: threshold pips, a fill that wipes to the best
streak, and a NOW marker at the current streak.
"""
from __future__ import annotations

import math

from ui import C, W, canvas, chamfer, d, esc, fit, header, svg

X0, X1 = 36, W - 36
TOP = 100          # first row under the header rule
GAP = 12           # between cards
WELL = 98          # icon well height
CARD_H = WELL + 106


# --------------------------------------------------------------------------- icons
# Each icon is drawn around (0, 0) inside roughly 124 x 54 units.
# f = body colour, k = cut lines / glass, a = accent light.

LOCKED = "#3B4139"   # body colour of a locked icon


def _solid(lit):
    """Solid body colour for strokes (gradients vanish on zero-width strokes)."""
    return C["text"] if lit else LOCKED


def _mirror_x(pts):
    """Symmetric outline from its left half (nose to tail, x <= 0)."""
    full = pts + [(-x, y) for x, y in reversed(pts) if x != 0]
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in full) + "Z"


def _mirror_y(pts):
    """Symmetric outline from its upper half (tail to nose, y <= 0)."""
    full = pts + [(x, -y) for x, y in reversed(pts) if y != 0]
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in full) + "Z"


def _poly(pts):
    return "M" + "L".join(f"{x:g} {y:g}" for x, y in pts) + "Z"


def icon_uav(f, k, a, lit):
    body = _mirror_x([
        (0, -26), (-2.6, -25.4), (-4.4, -23.4), (-5.2, -19.5), (-5.2, -9),
        (-57, -6.4), (-60, -5.6), (-61, -4), (-61, -2.4), (-59.5, -1.4),
        (-5.2, 1.2), (-4.4, 13), (-17.5, 21.5), (-18.2, 23.6), (-3.4, 18.6), (-2.6, 23.5), (0, 23.5),
    ])
    rings = (
        f'<circle r="36" fill="none" stroke="{a}" stroke-opacity=".16"/>'
        f'<circle r="22" fill="none" stroke="{a}" stroke-opacity=".12" stroke-dasharray="2 4"/>'
        f'<path d="M-44 0H-38M38 0H44M0 -36V-31M0 31V36" stroke="{a}" stroke-opacity=".3"/>'
    ) if lit else ""
    ping = (
        f'<circle class="ks-ping" r="34" fill="none" stroke="{a}" stroke-width="1.4"/>' if lit else ""
    )
    return (
        rings + ping
        + f'<path d="{body}" fill="{f}"/>'
        + f'<ellipse cy="25" rx="10" ry="1.6" fill="{f}" opacity=".55"/>'
        + f'<ellipse cy="-18" rx="2.6" ry="4.6" fill="{k}"/>'
        + f'<path d="M-50 -2.2H-34M34 -2.2H50" stroke="{k}" stroke-width="1"/>'
        + (f'<circle cx="-60" cy="-3.2" r="1.3" fill="{a}"/><circle cx="60" cy="-3.2" r="1.3" fill="{a}"/>' if lit else "")
    )


def icon_missile(f, k, a, lit):
    body = _mirror_y([
        (-44, 0), (-44, -4.6), (33, -4.6), (42, -4), (48, -2.8), (52.5, -1.2), (54, 0),
    ])
    fins = _poly([(-33, -4.6), (-43, -15), (-48, -15), (-44.5, -4.6)])
    fins_lo = _poly([(-33, 4.6), (-43, 15), (-48, 15), (-44.5, 4.6)])
    wing = _poly([(10, -4.6), (-5, -13), (-11, -13), (-3, -4.6)])
    wing_lo = _poly([(10, 4.6), (-5, 13), (-11, 13), (-3, 4.6)])
    flame = (
        f'<path d="M-44 -3.4L-70 0L-44 3.4Z" fill="url(#ksFlame)"/>'
        f'<path d="M-44 -1.8L-56 0L-44 1.8Z" fill="#FFF6D8"/>'
    ) if lit else ""
    trail = (
        f'<path d="M-74 -9H-58M-80 8H-62M-66 -15H-56" stroke="{a}" stroke-opacity=".35" stroke-width="1.2"/>'
        if lit else ""
    )
    return (
        '<g transform="rotate(17)">'
        + trail + flame
        + f'<path d="{fins}" fill="{f}"/><path d="{fins_lo}" fill="{f}"/>'
        + f'<path d="{wing}" fill="{f}"/><path d="{wing_lo}" fill="{f}"/>'
        + f'<path d="{body}" fill="{f}"/>'
        + f'<path d="M33 -4.6V4.6M-28 -4.6V4.6" stroke="{k}" stroke-width="1.1"/>'
        + f'<path d="M-20 -1H24" stroke="{k}" stroke-width=".9" opacity=".7"/>'
        + (f'<circle cx="46" cy="0" r="1.4" fill="{a}"/>' if lit else "")
        + "</g>"
    )


def icon_heli(f, k, a, lit):
    hull = _poly([
        (45, 3.5), (41, -2.5), (34, -6.5), (26, -8.5), (20, -13), (6, -14.5), (-5, -13.5),
        (-13, -9.5), (-23, -6.2), (-50, -4.2), (-53.5, -17), (-59, -18.5), (-59.5, -3),
        (-55, 2), (-23, 1.8), (-13, 6), (6, 9), (31, 9.5), (41, 7.5),
    ])
    canopy = (
        _poly([(40, -2.2), (34, -5.6), (28, -6.6), (29.5, -1.6)])
        + _poly([(25, -8), (20, -12.2), (13, -12.6), (14.5, -7.4)])
    )
    return (
        f'<ellipse cy="-21.5" rx="60" ry="1.7" fill="{f}" opacity=".9"/>'
        f'<rect x="-1.6" y="-21" width="3.2" height="7" fill="{f}"/>'
        f'<circle cx="-56" cy="-11" r="8" fill="none" stroke="{_solid(lit)}" stroke-width="1.3" opacity=".55"/>'
        f'<path d="{hull}" fill="{f}"/>'
        f'<path d="{canopy}" fill="{k}"/>'
        f'<path d="M-9 -6.5H-1" stroke="{k}" stroke-width="1.6"/>'
        f'<rect x="-8" y="1.5" width="20" height="3" fill="{f}"/>'
        f'<rect x="-6" y="4" width="15" height="6.4" rx="2" fill="{f}" stroke="{k}" stroke-width=".9"/>'
        f'<path d="M-2 4.6V10M4 4.6V10" stroke="{k}" stroke-width=".8"/>'
        f'<path d="M36 9L47 13.5" stroke="{_solid(lit)}" stroke-width="2.2"/>'
        f'<path d="M28 9.5V14M0 9V14M-52 2V6" stroke="{_solid(lit)}" stroke-width="1.4"/>'
        f'<circle cx="28" cy="15" r="2.6" fill="{f}"/><circle cx="0" cy="15" r="2.6" fill="{f}"/>'
        f'<circle cx="-52" cy="7" r="1.8" fill="{f}"/>'
        + (f'<circle cx="-58" cy="-17" r="1.3" fill="{a}"/>' if lit else "")
    )


def icon_jugg(f, k, a, lit):
    helmet = _mirror_x([(0, -28), (-12, -28), (-18, -23.5), (-20.5, -13), (-19.5, 1), (-14, 8), (0, 9.5)])
    torso = _mirror_x([(0, 7), (-22, 7), (-26, 28), (0, 28)])
    pauld = [(-21, 6), (-34, 7.5), (-42, 13.5), (-44.5, 27), (-29, 27), (-26.5, 13)]
    pauld_r = [(-x, y) for x, y in pauld]
    visor = _poly([(-15.5, -12.5), (15.5, -12.5), (13.5, -6.5), (-13.5, -6.5)])
    return (
        '<g mask="url(#ksFade)">'
        f'<path d="{torso}" fill="{f}"/>'
        f'<path d="{_poly(pauld)}" fill="{f}"/><path d="{_poly(pauld_r)}" fill="{f}"/>'
        f'<path d="M-43 19.5H-28.5M43 19.5H28.5M-25.5 12L-21 27M25.5 12L21 27M0 13V28M-16 19H16" '
        f'stroke="{k}" stroke-width="1.2" fill="none"/></g>'
        f'<path d="M-23 6.5H23L20 12H-20Z" fill="{f}" stroke="{k}" stroke-width="1.2"/>'
        f'<path d="{helmet}" fill="{f}"/>'
        f'<path d="M-18 -16.5H18M-19.5 -2L-13.5 5M19.5 -2L13.5 5" stroke="{k}" stroke-width="1.1" fill="none"/>'
        f'<path d="{visor}" fill="{a if lit else k}"/>'
        + (f'<path d="{visor}" fill="{a}" filter="url(#ksBloom)" opacity=".9"/>' if lit else "")
        + f'<path d="M-5 -1V5.5M0 -1V6.5M5 -1V5.5" stroke="{k}" stroke-width="1.5"/>'
    )


def icon_nuke(f, k, a, lit):
    def blade(centre):
        r1, r2, half = 7.2, 23.5, 30
        a0, a1 = math.radians(centre - half), math.radians(centre + half)
        p = lambda r, t: f"{r * math.cos(t):.2f} {r * math.sin(t):.2f}"
        return f"M{p(r1, a0)}L{p(r2, a0)}A{r2} {r2} 0 0 1 {p(r2, a1)}L{p(r1, a1)}A{r1} {r1} 0 0 0 {p(r1, a0)}Z"
    blades = "".join(blade(c) for c in (90, 210, 330))
    return (
        f'<circle r="28" fill="none" stroke="{_solid(lit)}" stroke-width="2.4"/>'
        f'<path d="{blades}" fill="{f}"/>'
        f'<circle r="4.8" fill="{f}"/>'
    )


def icon_generic(f, k, a, lit):
    return f'<path d="M-20 10L0 -10L20 10M-20 22L0 2L20 22" fill="none" stroke="{_solid(lit)}" stroke-width="5"/>'


def pick_icon(name: str):
    n = name.upper()
    for keys, fn in (
        (("UAV", "DRONE", "RADAR"), icon_uav),
        (("MISSILE", "ROCKET", "STRIKE"), icon_missile),
        (("CHOPPER", "HELI", "GUNNER", "GUNSHIP"), icon_heli),
        (("JUGG", "ARMOR", "ARMOUR"), icon_jugg),
        (("NUKE", "NUCLEAR"), icon_nuke),
    ):
        if any(key in n for key in keys):
            return fn
    return icon_generic


def lock(x, y, color):
    return (
        f'<path d="M{x - 3.6} {y}V{y - 3.2}A3.6 3.6 0 0 1 {x + 3.6} {y - 3.2}V{y}" '
        f'fill="none" stroke="{color}" stroke-width="1.8"/>'
        f'<rect x="{x - 5.4}" y="{y - .4}" width="10.8" height="8.4" rx="1" fill="{color}"/>'
        f'<rect x="{x - .8}" y="{y + 2.2}" width="1.6" height="3" fill="{C["panel"]}"/>'
    )


# --------------------------------------------------------------------------- text

def _sans_w(s: str, size: float) -> float:
    """Generous width estimate for the SANS stack."""
    w = 0.0
    for ch in s:
        if ch in "ijl.,:;'|!I ":
            w += 0.30
        elif ch in "frt-()":
            w += 0.40
        elif ch in "mwMW":
            w += 0.86
        elif ch.isupper() or ch.isdigit():
            w += 0.66
        else:
            w += 0.56
    return w * size


def wrap(text: str, size: float, width: float, max_lines: int = 3) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = f"{cur} {wd}".strip()
        if cur and _sans_w(trial, size) > width:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines[:max_lines]


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


# --------------------------------------------------------------------------- card

def card(i, ks, x, cw, longest, delay):
    days = int(ks["days"])
    earned = longest >= days
    y = TOP
    acc, dim, sub = C["accent"], C["dim"], C["sub"]
    f = "url(#ksIcon)" if earned else LOCKED
    k = C["panel"] if earned else "#1A1D19"
    out = [f'<g class="in-up" {d(delay)}>']

    # plate + icon well
    out.append(f'<path d="{chamfer(x, y, cw, CARD_H, 10)}" fill="url(#ksPlate)"/>')
    well = chamfer(x + 1, y + 1, cw - 2, WELL, 9, corners=("tl",))
    if earned:
        out.append(f'<path d="{well}" fill="url(#ksGlow)"/>')
    else:
        out.append(f'<path d="{well}" fill="url(#hatch)" opacity=".55"/>')
    out.append(f'<rect x="{x + 1}" y="{y + WELL + 1}" width="{cw - 2}" height="1" fill="{C["line2"]}"/>')
    out.append(
        f'<path d="{chamfer(x, y, cw, CARD_H, 10)}" fill="none" '
        f'stroke="{acc if earned else C["line2"]}" stroke-opacity="{.85 if earned else 1}"/>'
    )
    if earned:
        out.append(
            f'<path d="M{x + cw - 16} {y + .5}H{x + cw - .5}V{y + 16}M{x + .5} {y + CARD_H - 16}'
            f'V{y + CARD_H - .5}H{x + 16}" fill="none" stroke="{acc}" stroke-width="2"/>'
        )

    # top strip: index + state
    out.append(
        f'<text x="{x + 14}" y="{y + 23}" class="mono" font-size="11" font-weight="700" '
        f'fill="{acc if earned else dim}" letter-spacing="1">{i + 1:02d}</text>'
    )
    if earned:
        out.append(
            f'<g class="in-scale" {d(delay + .55)}>'
            f'<text x="{x + cw - 12}" y="{y + 23}" text-anchor="end" class="mono" font-size="11" '
            f'font-weight="700" fill="{acc}" letter-spacing="1.2">EARNED</text>'
            f'<path d="M{x + cw - 76} {y + 18}l3 3l6 -7" fill="none" stroke="{acc}" stroke-width="2"/></g>'
        )
    else:
        short = days - longest
        out.append(
            f'<text x="{x + cw - 12}" y="{y + 23}" text-anchor="end" class="mono" font-size="11" '
            f'font-weight="700" fill="{sub}" letter-spacing=".6">{short} DAY{"S" if short != 1 else ""} SHORT</text>'
        )

    # icon
    icx, icy = x + cw / 2, y + 30 + (WELL - 36) / 2
    draw = pick_icon(ks["name"])
    padlock = (f'<circle r="13" fill="{C["bg"]}" stroke="{C["line2"]}"/>{lock(0, 0, sub)}'
               if not earned else "")  # enters with its icon, never ahead of it
    out.append(
        f'<g class="in-scale" {d(delay + .25)}><g transform="translate({icx:.1f} {icy:.1f})">'
        f'{draw(f, k, acc, earned)}{padlock}</g></g>'
    )

    # segmented progress at the foot of the well: one segment per day
    sx0, sx1, sy = x + 12, x + cw - 12, y + WELL - 1
    n = days
    sg = 2 if n <= 12 else 1.4
    sw = (sx1 - sx0 - sg * (n - 1)) / n
    have = min(longest, days)
    for s in range(n):
        on = s < have
        col = acc if (on and earned) else (sub if on else C["line2"])
        out.append(
            f'<rect x="{sx0 + s * (sw + sg):.2f}" y="{sy}" width="{sw:.2f}" height="4" fill="{col}"/>'
        )

    # copy
    ty = y + WELL + 1
    out.append(cond(x + 14, ty + 33, ks["name"].upper(), 23, cw - 28, ls=.4,
                    extra=f'fill="{C["text"] if earned else C["sub"]}"'))
    out.append(
        f'<text x="{x + 14}" y="{ty + 51}" class="mono" font-size="11" font-weight="700" '
        f'fill="{acc if earned else sub}" letter-spacing="1.2">{days}-DAY STREAK</text>'
    )
    line = ks.get("line", "")
    head, _, tail = line.partition(". ")
    lines = wrap(line, 13, cw - 26, 2)
    ly = ty + 74
    for j, ln in enumerate(lines):
        # first sentence brighter than the rest
        if j == 0 and tail and ln.startswith(head + "."):
            rest = ln[len(head) + 1:]
            body = (f'<tspan fill="{C["text"] if earned else C["sub"]}" font-weight="600">{esc(head)}.</tspan>'
                    f'<tspan fill="{C["sub"]}">{esc(rest)}</tspan>')
        else:
            body = esc(ln)
        out.append(f'<text x="{x + 14}" y="{ly + j * 17}" font-size="13" fill="{C["sub"]}">{body}</text>')
    out.append("</g>")
    return "".join(out)


# --------------------------------------------------------------------------- tracker

def stage_scale(streaks, edges):
    """Days -> x on the tracker. Each reward's threshold lands under its card's right
    edge, so the stretch of track beneath a card is the run that earns it."""
    days = [int(s["days"]) for s in streaks]
    top = max(days)
    if days[0] <= 0 or any(b <= a for a, b in zip(days, days[1:])):  # not ascending: plain scale
        return lambda n: X0 + (X1 - X0) * max(0, min(n, top)) / top
    knots = list(zip([0] + days, [X0] + list(edges)))

    def xs(n):
        n = max(0, min(n, top))
        for (d0, x0), (d1, x1) in zip(knots, knots[1:]):
            if n <= d1:
                return x0 + (x1 - x0) * (n - d0) / (d1 - d0)
        return X1
    return xs


def tracker(streaks, longest, current, y, edges):
    acc, sub, dim = C["accent"], C["sub"], C["dim"]
    top = max(int(s["days"]) for s in streaks)
    tx0, tx1 = X0, X1
    xs = stage_scale(streaks, edges)
    th = 6
    out = []

    # track, fill, one segment per day (stage ends get the threshold poles instead)
    out.append(f'<rect x="{tx0}" y="{y}" width="{tx1 - tx0}" height="{th}" fill="{C["line"]}"/>')
    fill_w = xs(longest) - tx0
    if fill_w > 0:
        out.append(
            f'<rect class="in-wipe" {d(.95)} x="{tx0}" y="{y}" width="{fill_w:.1f}" height="{th}" fill="url(#ksFill)"/>'
        )
    if top <= 60:
        ends = {int(s["days"]) for s in streaks}
        gaps = "".join(f"M{xs(n):.1f} {y}v{th}" for n in range(1, top) if n not in ends)
        out.append(f'<path d="{gaps}" stroke="{C["bg"]}" stroke-width="2.4"/>')

    def lit_at(px):
        """When the fill's head passes px: inverse of the in-wipe ease (.95s start, .7s long),
        linearised over the stretch where the poles sit."""
        return .95 + .7 * (.3 + .45 * min(1.0, (px - tx0) / fill_w))

    # threshold poles: reward icon and day count, right-aligned to the pole like the cards' state tags
    for s in streaks:
        n = int(s["days"])
        px = xs(n)
        ok = longest >= n
        col = acc if ok else sub
        lbl = f"{n}D"
        lx = px - 7
        icx = lx - len(lbl) * 7.2 - 22
        mini = pick_icon(s["name"])(C["text"] if ok else "#4A5047", C["panel"] if ok else C["bg"], acc, False)
        out.append(
            f'<g class="in" {d(lit_at(px) if ok else 1.7)}>'
            f'<rect x="{min(px - 1, X1 - 2):.1f}" y="{y - 22}" width="2" height="{th + 26}" '
            f'fill="{acc if ok else C["line2"]}"/>'
            f'<g transform="translate({icx:.1f} {y - 13}) scale(.27)">{mini}</g>'
            f'<text x="{lx:.1f}" y="{y - 9}" text-anchor="end" class="mono" font-size="11" font-weight="700" '
            f'fill="{col}" letter-spacing=".6">{lbl}</text></g>'
        )
    out.append(
        f'<text x="{tx0}" y="{y - 9}" class="mono" font-size="11" font-weight="700" fill="{dim}">0</text>'
    )

    # BEST (fill head) and NOW marker, labels laid out so they never collide or leave the plate
    bx, nx = xs(longest), xs(current)
    lab_y = y + th + 24
    lw = lambda s: len(s) * 7.6
    labels = []  # [centre, width, svg-inner]
    if longest > 0 and longest == current:
        txt = f"NOW · BEST {longest}D"
        labels.append([bx, lw(txt), f'NOW · <tspan fill="{acc}">BEST {longest}D</tspan>'])
    else:
        if longest > 0:
            labels.append([bx, lw(f"BEST {longest}D"), f'<tspan fill="{acc}">BEST {longest}D</tspan>'])
        labels.append([nx, lw(f"NOW {current}D"), f"NOW {current}D"])
    labels.sort(key=lambda l: l[0])
    for l in labels:
        l[0] = min(max(l[0], X0 + l[1] / 2), X1 - l[1] / 2)
    if len(labels) == 2:
        (c1, w1, _), (c2, w2, _) = labels
        need = (w1 + w2) / 2 + 16
        if c2 - c1 < need:
            mid = (c1 + c2) / 2
            c1, c2 = mid - need / 2, mid + need / 2
            shift = max(0, X0 + w1 / 2 - c1) - max(0, c2 - (X1 - w2 / 2))
            labels[0][0], labels[1][0] = c1 + shift, c2 + shift

    if longest > 0:
        out.append(
            f'<g class="in" {d(1.6)}>'
            f'<rect x="{bx - 1.5:.1f}" y="{y - 4}" width="3" height="{th + 8}" fill="#FFFFFF"/></g>'
        )
    out.append(
        f'<g class="in-down" {d(1.8)}>'
        f'<path class="blink" d="M{nx:.1f} {y + th + 3}l5 7h-10Z" fill="{C["text"]}"/></g>'
    )
    out.append(f'<g class="in" {d(1.7)}>' + "".join(
        f'<text x="{c:.1f}" y="{lab_y}" text-anchor="middle" class="mono" font-size="11" '
        f'font-weight="700" letter-spacing="1">{inner}</text>' for c, _, inner in labels) + "</g>")
    return "".join(out)


# --------------------------------------------------------------------------- render

# ui's base rule `text:not([fill])` (specificity 0,1,1) outranks its own colour classes
# (.sub, .acc, ...: 0,1,0), so restate them at equal specificity; later in the sheet wins.
TEXT_CLASSES = "".join(f"text.{k}{{fill:{C[v]}}}" for k, v in (
    ("sub", "sub"), ("dim", "dim"), ("acc", "accent"), ("fr", "friend"), ("en", "enemy"), ("gold", "gold")))

CSS = TEXT_CLASSES + f"""
.ks-ping{{opacity:0;animation:ks-ping 3.2s ease-out 2.2s infinite;transform-box:fill-box;transform-origin:center}}
@keyframes ks-ping{{0%{{opacity:.7;transform:scale(.3)}}70%{{opacity:0;transform:scale(1)}}100%{{opacity:0}}}}
"""

DEFS = f"""
<linearGradient id="ksPlate" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="{C['panel2']}"/><stop offset="1" stop-color="{C['panel']}"/>
</linearGradient>
<radialGradient id="ksGlow" cx=".5" cy=".62" r=".62">
  <stop offset="0" stop-color="{C['accent']}" stop-opacity=".2"/>
  <stop offset=".55" stop-color="{C['accent']}" stop-opacity=".05"/>
  <stop offset="1" stop-color="{C['accent']}" stop-opacity="0"/>
</radialGradient>
<linearGradient id="ksFlame" x1="1" y1="0" x2="0" y2="0">
  <stop offset="0" stop-color="{C['gold']}"/><stop offset=".5" stop-color="{C['enemy']}" stop-opacity=".7"/>
  <stop offset="1" stop-color="{C['enemy']}" stop-opacity="0"/>
</linearGradient>
<linearGradient id="ksFill" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['accent2']}"/><stop offset="1" stop-color="{C['accent']}"/>
</linearGradient>
<linearGradient id="ksIcon" x1="0" y1="0" x2="0" y2="1">
  <stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#B9BFB3"/>
</linearGradient>
<linearGradient id="ksFadeG" x1="0" y1="0" x2="0" y2="1">
  <stop offset=".55" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
</linearGradient>
<mask id="ksFade" maskUnits="userSpaceOnUse" x="-60" y="-40" width="120" height="70">
  <rect x="-60" y="-40" width="120" height="70" fill="url(#ksFadeG)"/>
</mask>
<filter id="ksBloom" x="-50%" y="-200%" width="200%" height="500%"><feGaussianBlur stdDeviation="2.4"/></filter>
"""


def render(cfg, intel):
    streaks = cfg["killstreaks"]
    longest, current = int(intel["longest_streak"]), int(intel["current_streak"])
    n = len(streaks)
    cw = (X1 - X0 - GAP * (n - 1)) / n

    ty = TOP + CARD_H + 46
    H = ty + 80

    body = [canvas(W, H), header("03", "KILLSTREAKS", "STREAK REWARDS",
                                 right=f"CURRENT {current}D · BEST {longest}D")]
    for i, ks in enumerate(streaks):
        body.append(card(i, ks, X0 + i * (cw + GAP), cw, longest, .15 + i * .09))
    edges = [X0 + i * (cw + GAP) + cw for i in range(n)]
    body.append(tracker(streaks, longest, current, ty, edges))

    nxt = next((s for s in sorted(streaks, key=lambda s: s["days"]) if longest < int(s["days"])), None)
    body.append(
        f'<g class="in" {d(2.0)}>'
        f'<text x="{X0}" y="{H - 22}" class="mono" font-size="11" fill="{C["sub"]}">'
        f'Consecutive days with at least one contribution, past year.</text>'
    )
    if nxt:
        need = int(nxt["days"]) - current
        body.append(
            f'<text x="{X1}" y="{H - 22}" text-anchor="end" class="mono cap" fill="{C["sub"]}">'
            f'NEXT <tspan fill="{C["text"]}">{esc(nxt["name"].upper())}</tspan> · {need} MORE DAY{"S" if need != 1 else ""}</text>'
        )
    else:
        body.append(
            f'<text x="{X1}" y="{H - 22}" text-anchor="end" class="mono cap acc">ALL REWARDS EARNED</text>'
        )
    body.append("</g>")

    title = (f"Killstreaks: best streak {longest} days, current {current}. "
             + ", ".join(f'{s["name"]} ({s["days"]} days, {"earned" if longest >= s["days"] else "locked"})'
                         for s in streaks))
    return {"killstreaks.svg": svg(W, H, title, "".join(body), css=CSS, defs=DEFS)}
