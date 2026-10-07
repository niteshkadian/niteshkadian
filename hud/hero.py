"""
Hero: a cinematic mission intro that resolves into a gameplay HUD.

Timeline (seconds)
  0.0  fade from black, letterbox bars close in, satellite map settles (1.3 -> 1)
  0.4  intro text types out, bottom left
  0.9  title card: eyebrow, name letter by letter, callsign, disciplines
  2.8  HUD comes online: compass, minimap, killfeed, target lock, weapon, XP
  4.6  hitmarker loop (decorative, hidden at rest)

Everything about the map is generated here from a fixed seed: fractal
gradient noise -> hillshaded raster (embedded PNG) + marching-squares contours
joined into smooth paths, a carved river valley, a road and a compound.
"""
from __future__ import annotations

import base64
import math
import random
import struct
import zlib

from ui import C, COND, MONO, W, attr, chamfer, d, esc, fit, roman, svg

H = 560
LB = 32                      # letterbox bar height
SEED = 2019

# objective compound (the target the camera settles on) and the player
TX, TY = 752, 300
PX, PY = 668, 360

# DIN Condensed Bold advance widths (em); the fallback stacks are squeezed to
# the same length with textLength, so layout never depends on the viewer's font
CW = {
    "A": .407, "B": .426, "C": .407, "D": .426, "E": .37, "F": .37, "G": .426, "H": .426, "I": .204,
    "J": .333, "K": .426, "L": .37, "M": .556, "N": .444, "O": .426, "P": .407, "Q": .426, "R": .426,
    "S": .406, "T": .332, "U": .426, "V": .407, "W": .593, "X": .389, "Y": .388, "Z": .333, " ": .187,
    "_": .5, "-": .389, "[": .222, "]": .222, ".": .186, "/": .222, "+": .6, ":": .186, "·": .186,
}


def cw(text: str, size: float) -> float:
    """Natural width of COND text, used to size plates and textLength."""
    return sum(CW.get(ch, .372 if ch.isdigit() else .42) for ch in text.upper()) * size


def n(v: float) -> str:
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    if s == "-0":
        s = "0"
    return s


# --------------------------------------------------------------------------
# terrain
# --------------------------------------------------------------------------

class Perlin:
    """2D gradient noise with a seeded permutation and a fixed gradient set."""
    G = [(1, 0), (-1, 0), (0, 1), (0, -1), (.7071, .7071), (-.7071, .7071), (.7071, -.7071), (-.7071, -.7071)]

    def __init__(self, seed: int):
        r = random.Random(seed)
        p = list(range(256))
        r.shuffle(p)
        self.p = p + p

    def __call__(self, x: float, y: float) -> float:
        xi, yi = math.floor(x), math.floor(y)
        xf, yf = x - xi, y - yi
        xi &= 255
        yi &= 255
        p, G = self.p, self.G

        def g(ix, iy, dx, dy):
            gx, gy = G[p[p[ix] + iy] & 7]
            return gx * dx + gy * dy

        u = xf * xf * xf * (xf * (xf * 6 - 15) + 10)
        v = yf * yf * yf * (yf * (yf * 6 - 15) + 10)
        a = g(xi, yi, xf, yf) + u * (g(xi + 1, yi, xf - 1, yf) - g(xi, yi, xf, yf))
        b = g(xi, yi + 1, xf, yf - 1) + u * (g(xi + 1, yi + 1, xf - 1, yf - 1) - g(xi, yi + 1, xf, yf - 1))
        return a + v * (b - a)


NOISE = Perlin(SEED)
WARP = Perlin(SEED + 1)
VEG = Perlin(SEED + 2)
RIDGE = Perlin(SEED + 3)


def river_x(y: float) -> float:
    """The river runs top to bottom through the gap between title and target."""
    return 628 + 34 * math.sin(y / 88 + .4) + 15 * math.sin(y / 31 + 2.1) - .06 * (y - 280)


def fbm(x: float, y: float, octaves: int = 4) -> float:
    s, amp, f, norm = 0.0, 1.0, 1 / 290, 0.0
    for o in range(octaves):
        s += amp * NOISE(x * f + 17.3 * o, y * f - 9.1 * o)
        norm += amp
        amp *= .5
        f *= 2.03
    return s / norm


def elevation(x: float, y: float) -> float:
    wx = 60 * WARP(x / 420, y / 420)
    wy = 60 * WARP(x / 420 + 40, y / 420 + 40)
    e = fbm(x + wx, y + wy)
    e += .16 * math.sin((x + y * .6) / 260)          # broad ridge structure
    # ridged noise on the high ground: sharp crests that catch the light
    r = 1 - abs(RIDGE(x / 150, y / 150)) * 1.6
    r += .5 * (1 - abs(RIDGE(x / 70 + 5, y / 70 + 5)) * 1.6)
    hi = min(1.0, max(0.0, (e + .02) / .3))
    e += .12 * hi * hi * (r - .7)
    dr = abs(x - river_x(y))
    e -= .32 * math.exp(-(dr / 70) ** 2)             # carved river valley
    return e


def grid(step: float, x0: float = 0, y0: float = 0, w: float = W, h: float = H):
    nx, ny = int(math.ceil(w / step)) + 1, int(math.ceil(h / step)) + 1
    return [[elevation(x0 + i * step, y0 + j * step) for i in range(nx)] for j in range(ny)]


# ---- marching squares -----------------------------------------------------

def contours(v, step: float, level: float):
    """Iso-lines at `level` as joined polylines (lists of (x, y))."""
    ny, nx = len(v), len(v[0])
    pts, segs = {}, []

    def edge(kind, i, j):
        key = (kind, i, j)
        if key not in pts:
            if kind == "h":   # between (i, j) and (i + 1, j)
                a, b = v[j][i], v[j][i + 1]
                t = (level - a) / (b - a)
                pts[key] = ((i + t) * step, j * step)
            else:             # between (i, j) and (i, j + 1)
                a, b = v[j][i], v[j + 1][i]
                t = (level - a) / (b - a)
                pts[key] = (i * step, (j + t) * step)
        return key

    for j in range(ny - 1):
        row, nxt = v[j], v[j + 1]
        for i in range(nx - 1):
            a, b, c, dd = row[i], row[i + 1], nxt[i + 1], nxt[i]
            k = (a > level) * 8 + (b > level) * 4 + (c > level) * 2 + (dd > level)
            if k in (0, 15):
                continue
            T, R, B, L = ("h", i, j), ("v", i + 1, j), ("h", i, j + 1), ("v", i, j)
            centre = (a + b + c + dd) / 4 > level
            pairs = {
                1: [(L, B)], 2: [(B, R)], 3: [(L, R)], 4: [(T, R)],
                5: [(L, T), (B, R)] if centre else [(T, R), (L, B)],
                6: [(T, B)], 7: [(L, T)], 8: [(L, T)], 9: [(T, B)],
                10: [(T, R), (L, B)] if centre else [(L, T), (B, R)],
                11: [(T, R)], 12: [(L, R)], 13: [(B, R)], 14: [(L, B)],
            }[k]
            for e1, e2 in pairs:
                segs.append((edge(*e1), edge(*e2)))

    adj: dict = {}
    for s, (e1, e2) in enumerate(segs):
        adj.setdefault(e1, []).append(s)
        adj.setdefault(e2, []).append(s)
    used = [False] * len(segs)

    def walk(start):
        chain, cur = [start], start
        while True:
            nxt_seg = next((s for s in adj[cur] if not used[s]), None)
            if nxt_seg is None:
                return chain
            used[nxt_seg] = True
            e1, e2 = segs[nxt_seg]
            cur = e2 if e1 == cur else e1
            chain.append(cur)

    lines = []
    for e, ss in adj.items():                       # open chains start at the border
        if len(ss) == 1 and not used[ss[0]]:
            lines.append(walk(e))
    for s in range(len(segs)):                      # then closed loops
        if not used[s]:
            lines.append(walk(segs[s][0]))
    return [[pts[e] for e in ln] for ln in lines]


def rdp(points, eps):
    if len(points) < 3:
        return points
    (x1, y1), (x2, y2) = points[0], points[-1]
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    best, idx = -1.0, 0
    for k in range(1, len(points) - 1):
        px, py = points[k]
        dist = abs(dy * (px - x1) - dx * (py - y1)) / L if L else math.hypot(px - x1, py - y1)
        if dist > best:
            best, idx = dist, k
    if best <= eps:
        return [points[0], points[-1]]
    return rdp(points[:idx + 1], eps)[:-1] + rdp(points[idx:], eps)


def smooth(points, closed: bool) -> str:
    """Quadratic midpoint smoothing; relative commands, one decimal."""
    if closed:
        pts = points[:-1] if points[0] == points[-1] else points
        if len(pts) < 3:
            return ""
        m = [((pts[k][0] + pts[(k + 1) % len(pts)][0]) / 2, (pts[k][1] + pts[(k + 1) % len(pts)][1]) / 2)
             for k in range(len(pts))]
        out = [f"M{n(m[-1][0])} {n(m[-1][1])}"]
        cx, cy = round(m[-1][0], 1), round(m[-1][1], 1)
        for k in range(len(pts)):
            qx, qy = round(pts[k][0], 1), round(pts[k][1], 1)
            ex, ey = round(m[k][0], 1), round(m[k][1], 1)
            out.append(f"q{n(qx - cx)} {n(qy - cy)} {n(ex - cx)} {n(ey - cy)}")
            cx, cy = ex, ey
        return "".join(out) + "z"
    if len(points) < 2:
        return ""
    cx, cy = round(points[0][0], 1), round(points[0][1], 1)
    out = [f"M{n(cx)} {n(cy)}"]
    for k in range(1, len(points) - 1):
        qx, qy = round(points[k][0], 1), round(points[k][1], 1)
        ex = round((points[k][0] + points[k + 1][0]) / 2, 1)
        ey = round((points[k][1] + points[k + 1][1]) / 2, 1)
        out.append(f"q{n(qx - cx)} {n(qy - cy)} {n(ex - cx)} {n(ey - cy)}")
        cx, cy = ex, ey
    lx, ly = round(points[-1][0], 1), round(points[-1][1], 1)
    out.append(f"l{n(lx - cx)} {n(ly - cy)}")
    return "".join(out)


def poly_len(p):
    return sum(math.hypot(p[k + 1][0] - p[k][0], p[k + 1][1] - p[k][1]) for k in range(len(p) - 1))


# ---- hillshaded raster ------------------------------------------------------

def png(w: int, h: int, rows: list[bytes]) -> bytes:
    """Minimal RGB PNG with per-row adaptive filtering (sub / up / paeth)."""
    bpp, prev, out = 3, bytes(w * 3), bytearray()
    for row in rows:
        cands = []
        sub = bytes((row[k] - (row[k - bpp] if k >= bpp else 0)) & 255 for k in range(len(row)))
        up = bytes((row[k] - prev[k]) & 255 for k in range(len(row)))
        pa = bytearray(len(row))
        for k in range(len(row)):
            a = row[k - bpp] if k >= bpp else 0
            b = prev[k]
            c = prev[k - bpp] if k >= bpp else 0
            p = a + b - c
            ppa, ppb, ppc = abs(p - a), abs(p - b), abs(p - c)
            pr = a if ppa <= ppb and ppa <= ppc else (b if ppb <= ppc else c)
            pa[k] = (row[k] - pr) & 255
        for f, data in ((1, sub), (2, up), (4, bytes(pa))):
            cands.append((sum(x if x < 128 else 256 - x for x in data), f, data))
        _, f, data = min(cands)
        out.append(f)
        out += data
        prev = row

    def chunk(t, data):
        return struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(out), 9)) + chunk(b"IEND", b""))


def raster(lo: float, hi: float, px: int = 4) -> str:
    """Hillshaded, elevation-tinted terrain as a data URI (canvas sized)."""
    rw, rh = W // px, H // px
    e = [[elevation((i - .5) * px, (j - .5) * px) for i in range(rw + 2)] for j in range(rh + 2)]
    lx, ly, lz = -1.0, -1.25, 1.1
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / ln, ly / ln, lz / ln
    flat = lz
    low, high = (17, 22, 19), (70, 66, 50)
    zf = 30.0
    rows = []
    for j in range(1, rh + 1):
        row = bytearray()
        for i in range(1, rw + 1):
            h0 = e[j][i]
            dx = (e[j][i + 1] - e[j][i - 1]) * zf
            dy = (e[j + 1][i] - e[j - 1][i]) * zf
            nl = math.sqrt(dx * dx + dy * dy + 1)
            shade = (-dx * lx - dy * ly + lz) / nl
            t = min(1.0, max(0.0, (h0 - lo) / (hi - lo)))
            t = t ** 1.1
            m = max(.4, min(1.9, 1 + 1.8 * (shade - flat)))
            x, y = (i - .5) * px, (j - .5) * px
            veg = VEG(x / 26, y / 26) + .5 * VEG(x / 11 + 7, y / 11 + 3)
            vg = max(0.0, min(1.0, (veg - .18) * 3.2)) * max(0.0, 1 - 1.4 * t) * .6
            m *= 1 + .07 * VEG(x / 5 + 31, y / 5 + 17)    # ground texture
            col = []
            lit = max(0.0, min(1.0, (shade - flat) * 3))          # sunlit slopes warm up
            dark = max(0.0, min(1.0, (flat - shade) * 3))         # shadowed slopes cool down
            for k in range(3):
                c = low[k] + (high[k] - low[k]) * t
                c = c * (1 - vg) + (11, 19, 12)[k] * vg
                c = c * m + (5, 3, -2)[k] * lit - (2, -1, -2)[k] * dark
                col.append(int(max(0, min(255, c))))
            row += bytes(col)
        rows.append(bytes(row))
    return "data:image/png;base64," + base64.b64encode(png(rw, rh, rows)).decode()


# ---- road, river, compound ----------------------------------------------------

def catmull(points, seg=10):
    out = []
    p = [points[0]] + points + [points[-1]]
    for k in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[k - 1], p[k], p[k + 1], p[k + 2]
        for s in range(seg):
            t = s / seg
            t2, t3 = t * t, t * t * t
            out.append(tuple(.5 * ((2 * p1[a]) + (-p0[a] + p2[a]) * t + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t2
                                   + (-p0[a] + 3 * p1[a] - 3 * p2[a] + p3[a]) * t3) for a in (0, 1)))
    out.append(points[-1])
    return out


ROAD = [(430, 575), (520, 486), (590, 418), (668, 360), (TX - 30, TY + 18), (TX + 40, TY - 20),
        (860, 252), (940, 232), (1015, 214)]


def line_d(points) -> str:
    cx, cy = round(points[0][0], 1), round(points[0][1], 1)
    out = [f"M{n(cx)} {n(cy)}"]
    for x, y in points[1:]:
        x, y = round(x, 1), round(y, 1)
        out.append(f"l{n(x - cx)} {n(y - cy)}")
        cx, cy = x, y
    return "".join(out)


def rect_poly(cx, cy, w, h, ang):
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        x, y = sx * w / 2, sy * h / 2
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return "M" + "L".join(f"{n(x)} {n(y)}" for x, y in pts) + "Z"


def compound() -> str:
    """Satellite-view buildings: a walled compound on the road plus strays."""
    r = random.Random(SEED + 7)
    ang = math.atan2(-38, 70)
    roofs, shadows = [], []
    # walled compound
    wall = rect_poly(TX, TY, 84, 62, ang)
    blocks = [(-24, -12, 26, 16), (8, -14, 18, 22), (26, 8, 16, 14), (-20, 14, 22, 12), (2, 14, 12, 10)]
    ca, sa = math.cos(ang), math.sin(ang)
    for bx, by, bw, bh in blocks:
        cx, cy = TX + bx * ca - by * sa, TY + bx * sa + by * ca
        roofs.append(rect_poly(cx, cy, bw, bh, ang))
        shadows.append(rect_poly(cx + 2.2, cy + 2.2, bw, bh, ang))
    # houses strung along the road
    road = catmull(ROAD, 6)
    for k in range(4, len(road) - 4, 3):
        if r.random() < .5:
            continue
        (x0, y0), (x1, y1) = road[k], road[k + 1]
        a = math.atan2(y1 - y0, x1 - x0)
        side = r.choice((-1, 1))
        off = side * (9 + r.random() * 8)
        cx, cy = x0 - math.sin(a) * off, y0 + math.cos(a) * off
        if math.hypot(cx - TX, cy - TY) < 60 or abs(cx - river_x(cy)) < 22:
            continue
        bw, bh = 7 + r.random() * 6, 6 + r.random() * 4
        roofs.append(rect_poly(cx, cy, bw, bh, a))
        shadows.append(rect_poly(cx + 1.6, cy + 1.6, bw, bh, a))
    return (
        f'<path d="{"".join(shadows)}" fill="#000" opacity=".55"/>'
        f'<path d="{wall}" fill="#3a3c31" fill-opacity=".35" stroke="#b9b8a2" stroke-opacity=".5" stroke-width="1"/>'
        f'<path d="{"".join(roofs)}" fill="#a7a692" fill-opacity=".62"/>'
    )


def fields() -> str:
    """Patchwork farm parcels on the valley floor, aligned to the river."""
    r = random.Random(SEED + 11)
    tones = ["#59573c", "#3b4229", "#6a6449", "#2c3522", "#4b4c33"]
    by_tone: dict = {}
    for cy0, side in ((118, 1), (250, -1), (470, 1), (505, -1)):
        cx0 = river_x(cy0) + side * 58
        ang = math.atan2(1, (river_x(cy0 + 1) - river_x(cy0 - 1)) / 2)
        ca, sa = math.cos(ang), math.sin(ang)
        cols, rows, cwid, chgt = 3, 4, 24, 15
        for gi in range(cols):
            for gj in range(rows):
                if r.random() < .22:
                    continue
                u = (gi - (cols - 1) / 2) * (cwid + 3)
                v = (gj - (rows - 1) / 2) * (chgt + 3)
                x, y = cx0 + u * ca - v * sa, cy0 + u * sa + v * ca
                if abs(x - river_x(y)) < 22:
                    continue
                w = cwid * (.75 + .35 * r.random())
                by_tone.setdefault(r.choice(tones), []).append(rect_poly(x, y, w, chgt, ang))
    return "".join(f'<path d="{"".join(v)}" fill="{k}" fill-opacity=".42"/>' for k, v in by_tone.items())


# --------------------------------------------------------------------------
# HUD pieces
# --------------------------------------------------------------------------

def rifle(x, y, s=1.0, fill=None) -> str:
    """Side-profile assault rifle, ~40 x 12 at s=1, muzzle to the right."""
    p = ("M0 3.6L2.4 3.2H10.2V7.4L3 9.8H0Z"            # stock
         "M10 3H27.4V7.2H10Z"                         # receiver
         "M12.6 .2H21.4V2.4H19.6V3H14.4V2.4H12.6Z"    # optic
         "M14.4 7H18.2L16.8 12.2H13.4Z"               # grip
         "M20.4 7H24.8L26.2 12.4Q24.2 13.2 22.2 12.8Z"  # magazine
         "M27.2 3.4H36V6.6H27.2Z"                     # handguard
         "M33.8 1.8H35V3.4H33.8ZM35.8 4.3H42V5.5H35.8Z")
    return f'<path transform="translate({n(x)} {n(y)}) scale({s})" d="{p}" fill="{fill or C["text"]}"/>'


def knife(x, y, fill=None) -> str:
    p = "M0 4.2H9.5V3H12V7.6H9.5V6.4H0ZM12.4 3.6H23.5Q28.5 3.8 31 5.8L25.5 7.2H12.4Z"
    return f'<path transform="translate({n(x)} {n(y)})" d="{p}" fill="{fill or C["text"]}"/>'


def headshot(x, y) -> str:
    """Head silhouette with a reticle, the classic headshot medal glyph."""
    e = C["enemy"]
    return (
        f'<g transform="translate({n(x)} {n(y)})">'
        f'<circle cx="6" cy="5" r="4.2" fill="{C["text"]}"/>'
        f'<path d="M0.5 13Q1 8.6 6 8.6T11.5 13Z" fill="{C["text"]}"/>'
        f'<circle cx="6" cy="5" r="6" fill="none" stroke="{e}" stroke-width="1.2"/>'
        f'<path d="M6 -2.5V1.2M6 8.8V12.5M-1.5 5H2.2M9.8 5H13.5" stroke="{e}" stroke-width="1.2"/>'
        f"</g>"
    )


def c4(x, y) -> str:
    """Brick of plastic explosive: two charges, a strap, a detonator."""
    t = C["text"]
    return (
        f'<g transform="translate({n(x)} {n(y)})">'
        f'<rect x="0" y="5" width="20" height="10" rx="1" fill="{t}"/>'
        f'<path d="M6.6 5V15M13.4 5V15" stroke="{C["bg"]}" stroke-width="1.6"/>'
        f'<rect x="7.4" y="1" width="5.2" height="5" fill="{t}" stroke="{C["bg"]}" stroke-width="1"/>'
        f'<rect x="8.9" y="2.4" width="2.2" height="1.8" fill="{C["enemy"]}"/>'
        f"</g>"
    )


def stim(x, y) -> str:
    t = C["text"]
    return (
        f'<g transform="translate({n(x)} {n(y)}) rotate(-45 9 8)">'
        f'<rect x="3" y="5.5" width="11" height="5" rx="1" fill="{t}"/>'
        f'<rect x="5" y="6.8" width="5" height="2.4" fill="{C["accent"]}"/>'
        f'<path d="M14 8H18.5M0.5 5.5V10.5M0.5 8H3" stroke="{t}" stroke-width="1.4"/>'
        f"</g>"
    )


def uav(x, y, fill) -> str:
    p = "M7 0L8.4 4.6L15 6.4V7.6L8.4 7.4L8 10.6L10 11.8V12.6L7 12L4 12.6V11.8L6 10.6L5.6 7.4L-1 7.6V6.4L5.6 4.6Z"
    return f'<path transform="translate({n(x)} {n(y)})" d="{p}" fill="{fill}"/>'


# --------------------------------------------------------------------------
# map
# --------------------------------------------------------------------------

# HUD boxes that map labels (spot heights, grid refs) must stay clear of
KEEP_OUT = [(20, 40, 180, 215), (28, 222, 590, 412), (28, 425, 470, 515), (290, 32, 710, 150),
            (700, 36, 985, 170), (668, 180, 840, 380), (740, 396, 985, 525), (940, 0, 1000, 560)]


def free(x, y, pad=6) -> bool:
    return not any(x0 - pad < x < x1 + pad and y0 - pad < y < y1 + pad for x0, y0, x1, y1 in KEEP_OUT)


def build_map():
    step = 8
    v = grid(step)
    flat = sorted(x for row in v for x in row)
    lo, hi = flat[int(.02 * len(flat))], flat[int(.99 * len(flat))]
    nlev = 12
    minor, index = [], []
    for k in range(nlev):
        level = lo + (hi - lo) * (k + .5) / nlev
        for line in contours(v, step, level):
            closed = len(line) > 3 and line[0] == line[-1]
            if poly_len(line) < (40 if closed else 26):
                continue
            pts = rdp(line, .65)
            dd = smooth(pts, closed)
            (index if k % 4 == 3 else minor).append(dd)

    def metres(e):
        return int(round(180 + (e - lo) / (hi - lo) * 320))

    # spot heights: strongest local maxima that sit in open ground
    peaks = []
    for j in range(2, len(v) - 2):
        for i in range(2, len(v[0]) - 2):
            e = v[j][i]
            if all(e > v[j + b][i + a] for a in (-2, -1, 0, 1, 2) for b in (-2, -1, 0, 1, 2) if a or b):
                peaks.append((e, i * step, j * step))
    peaks.sort(reverse=True)
    spots = []
    for e, x, y in peaks:
        if free(x, y, 18) and free(x + 30, y, 10) and all(math.hypot(x - a, y - b) > 120 for a, b, _ in spots):
            spots.append((x, y, metres(e)))
        if len(spots) == 3:
            break

    river = [(river_x(y), y) for y in range(-10, H + 12, 6)]
    road = catmull(ROAD, 8)
    bridge = None
    for (x0, y0), (x1, y1) in zip(road, road[1:]):
        if (x0 - river_x(y0)) * (x1 - river_x(y1)) < 0:
            bridge = ((x0 + x1) / 2, (y0 + y1) / 2, math.degrees(math.atan2(y1 - y0, x1 - x0)))
            break

    topo = (
        f'<g fill="none" vector-effect="non-scaling-stroke">'
        f'<path d="{"".join(minor)}" stroke="#7d8466" stroke-opacity=".34" stroke-width=".8" vector-effect="non-scaling-stroke"/>'
        f'<path d="{"".join(index)}" stroke="#aeb38c" stroke-opacity=".55" stroke-width="1.3" vector-effect="non-scaling-stroke"/>'
        f"</g>"
        f'<path d="{smooth(river, False)}" fill="none" stroke="#050806" stroke-opacity=".55" stroke-width="9" stroke-linecap="round"/>'
        f'<path d="{smooth(river, False)}" fill="none" stroke="#4e6a72" stroke-width="3.4" vector-effect="non-scaling-stroke"/>'
        f'<path d="{line_d(road)}" fill="none" stroke="#070806" stroke-opacity=".6" stroke-width="5"/>'
        f'<path d="{line_d(road)}" fill="none" stroke="#d9d4b6" stroke-opacity=".55" stroke-width="1.5" '
        f'stroke-dasharray="7 5" vector-effect="non-scaling-stroke"/>'
    )
    if bridge:
        bx, by, ba = bridge
        topo += (f'<rect x="{n(bx - 9)}" y="{n(by - 3)}" width="18" height="6" fill="#c9c6ae" fill-opacity=".7" '
                 f'transform="rotate({n(ba)} {n(bx)} {n(by)})"/>')
    return raster(lo, hi), topo, spots


def map_layer(img, topo, spots, clip_id) -> str:
    g = []
    for x in range(100, W, 100):
        g.append(f"M{x} 0V{H}")
    for y in range(100, H, 100):
        g.append(f"M0 {y}H{W}")
    sp = "".join(
        f'<path d="M{n(x)} {n(y - 4)}l4 7h-8z" fill="{C["text"]}" fill-opacity=".55"/>'
        f'<text x="{n(x + 7)}" y="{n(y + 3)}" class="mono" font-size="11" fill-opacity=".55">{m}</text>'
        for x, y, m in spots
    )
    return (
        f'<g clip-path="url(#{clip_id})"><g class="zoom">'
        f'<image href="{img}" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="none"/>'
        f"{fields()}"
        f'<g id="topo">{topo}</g>'
        f"{compound()}"
        f'<path d="{"".join(g)}" stroke="#E8EBDD" stroke-opacity=".09" stroke-width="1"/>'
        f"{sp}"
        f"</g></g>"
    )


# --------------------------------------------------------------------------
# HUD
# --------------------------------------------------------------------------

def bearing(x0, y0, x1, y1) -> float:
    return math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360


ENEMIES = [(TX + 96, TY + 58), (PX - 92, PY - 72), (PX - 112, PY + 40)]


def compass(heading: float) -> str:
    cx, ty, half, ppd = W / 2, 62, 196, 3.2
    lab = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
    ticks, texts = [], []
    start = int(heading - 100) // 5 * 5
    for deg in range(start, int(heading + 100) + 5, 5):
        x = cx + (deg - heading) * ppd
        b = deg % 360
        major = b % 15 == 0
        ticks.append(f"M{n(x)} {ty + 4}v{9 if b % 45 == 0 else (6 if major else 3)}")
        if abs(x - cx) > half - 42:
            continue                  # deep in the edge fade a label shows as a stray digit
        if b in lab:
            col = C["accent"] if b == 0 else C["text"]
            texts.append(f'<text x="{n(x)}" y="{ty}" text-anchor="middle" class="cond" font-size="17" style="fill:{col}">{lab[b]}</text>')
        elif major:
            texts.append(f'<text x="{n(x)}" y="{ty - 1}" text-anchor="middle" class="mono sub" font-size="11">{b}</text>')
    marks = []
    for ex, ey in ENEMIES:
        dlt = (bearing(PX, PY, ex, ey) - heading + 540) % 360 - 180
        if abs(dlt * ppd) > half - 30:
            continue
        x = cx + dlt * ppd
        marks.append(f'<path d="M{n(x)} {ty + 22}l4 -6h-8z" fill="{C["enemy"]}"/>')
    dlt = (bearing(PX, PY, TX, TY) - heading + 540) % 360 - 180
    ox = cx + max(-half + 8, min(half - 8, dlt * ppd))
    obj = (f'<path d="M{n(ox)} {ty + 16}l6 6-6 6-6-6z" fill="#000" fill-opacity=".5" stroke="{C["text"]}" stroke-width="1.2"/>'
           f'<text x="{n(ox)}" y="{ty + 26}" text-anchor="middle" class="cond" font-size="11">A</text>')
    return (
        f'<g class="in-down" {d(2.75)}>'
        f'<g mask="url(#cmask)"><rect x="{cx - half}" y="38" width="{2 * half}" height="38" fill="#000" fill-opacity=".34"/><g class="cpan">'
        f'<path d="{"".join(ticks)}" stroke="{C["text"]}" stroke-opacity=".8" stroke-width="1.4"/>'
        f'{"".join(texts)}'
        f"</g></g>"
        f'<g class="in" {d(3.5)}>{"".join(marks)}{obj}</g>'
        f'<path d="M{cx} {ty + 3}l-5 -7h10z" fill="{C["accent"]}" transform="translate(0 -22)"/>'
        f'<rect x="{cx - 21}" y="{ty + 32}" width="42" height="19" fill="#000" fill-opacity=".55" stroke="{C["line2"]}"/>'
        f'<text x="{cx}" y="{ty + 46}" text-anchor="middle" class="mono" font-size="13" font-weight="700">{int(round(heading)) % 360:03d}</text>'
        f"</g>"
    )


def minimap(heading: float) -> str:
    MX, MY, R, s = 92, 120, 58, .42
    a = C["accent"]
    wedge = []
    for k in range(9):
        a0, a1 = math.radians(-90 - k * 6), math.radians(-90 - (k + 1) * 6)
        wedge.append(
            f'<path d="M{MX} {MY}L{n(MX + R * math.cos(a0))} {n(MY + R * math.sin(a0))}'
            f'A{R} {R} 0 0 0 {n(MX + R * math.cos(a1))} {n(MY + R * math.sin(a1))}Z" fill="{a}" '
            f'fill-opacity="{.26 * (1 - k / 9) ** 1.6:.3f}"/>'
        )
    pings = []
    for k, (ex, ey) in enumerate(ENEMIES):
        x, y = MX + (ex - PX) * s, MY + (ey - PY) * s
        dist = math.hypot(x - MX, y - MY)
        if dist > R - 6:
            x, y = MX + (x - MX) * (R - 6) / dist, MY + (y - MY) * (R - 6) / dist
        pings.append(
            f'<circle class="ping" style="animation-delay:{3.4 + k * .7:.1f}s" cx="{n(x)}" cy="{n(y)}" r="4" fill="none" stroke="{C["enemy"]}" stroke-width="1.4"/>'
            f'<circle cx="{n(x)}" cy="{n(y)}" r="3.2" fill="{C["enemy"]}"/>'
        )
    ox, oy = MX + (TX - PX) * s, MY + (TY - PY) * s
    od = math.hypot(ox - MX, oy - MY)
    if od > R - 9:
        ox, oy = MX + (ox - MX) * (R - 9) / od, MY + (oy - MY) * (R - 9) / od
    fov = math.radians(heading - 90)
    cone = (
        f'<path d="M{MX} {MY}L{n(MX + 44 * math.cos(fov - .55))} {n(MY + 44 * math.sin(fov - .55))}'
        f'A44 44 0 0 1 {n(MX + 44 * math.cos(fov + .55))} {n(MY + 44 * math.sin(fov + .55))}Z" fill="url(#fovg)"/>'
    )
    ring_ticks = "".join(
        f'M{n(MX + (R + 3) * math.sin(math.radians(b)))} {n(MY - (R + 3) * math.cos(math.radians(b)))}'
        f'L{n(MX + (R + (8 if b % 90 == 0 else 5)) * math.sin(math.radians(b)))} {n(MY - (R + (8 if b % 90 == 0 else 5)) * math.cos(math.radians(b)))}'
        for b in range(0, 360, 30) if b
    )
    return (
        f'<g class="in-scale" {d(2.85)}>'
        f'<circle cx="{MX}" cy="{MY}" r="{R}" fill="#050605" fill-opacity=".86"/>'
        f'<g clip-path="url(#mmclip)">'
        f'<use href="#topo" transform="translate({n(MX - PX * s)} {n(MY - PY * s)}) scale({s})" opacity=".95"/>'
        f'<g class="sweep">{"".join(wedge)}<path d="M{MX} {MY}V{MY - R}" stroke="{a}" stroke-opacity=".8" stroke-width="1.2"/></g>'
        f"</g>"
        f'<path d="M{n(ox)} {n(oy - 7)}l7 7-7 7-7-7z" fill="#000" fill-opacity=".6" stroke="{C["text"]}" stroke-width="1.2"/>'
        f'<text x="{n(ox)}" y="{n(oy + 4)}" text-anchor="middle" class="cond" font-size="11">A</text>'
        f'{"".join(pings)}'
        f"{cone}"
        f'<path d="M0 -9L6.5 7L0 3.6L-6.5 7Z" transform="translate({MX} {MY}) rotate({n(heading)})" fill="{C["friend"]}" stroke="#000" stroke-opacity=".6" stroke-width="1"/>'
        f'<circle cx="{MX}" cy="{MY}" r="{R}" fill="none" stroke="{C["text"]}" stroke-opacity=".35" stroke-width="1.2"/>'
        f'<circle cx="{MX}" cy="{MY}" r="{R + 3}" fill="none" stroke="{C["text"]}" stroke-opacity=".12"/>'
        f'<path d="{ring_ticks}" stroke="{C["text"]}" stroke-opacity=".4" stroke-width="1.2"/>'
        f'<path d="M{MX} {MY - R - 4}l-5 -8h10z" fill="{a}"/>'
        f'<text x="{MX}" y="{MY - R - 15}" text-anchor="middle" class="cond acc" font-size="13">N</text>'
        f"</g>"
        f'<g class="in" {d(3.3)}>'
        f'{uav(MX - 50, MY + R + 15, a)}'
        f'<text x="{MX - 30}" y="{MY + R + 26}" class="mono acc cap">UAV ONLINE</text>'
        f"</g>"
    )


def killfeed(cfg) -> str:
    feed = cfg.get("killfeed", [])[:5]
    rows, RX, y0 = [], 968, 46
    rh = 29 if len(feed) <= 4 else 23.5
    tag, me = f"[{cfg['clan']}]", cfg["callsign"].upper()
    fs = 15
    # one plate width for every row and fixed columns inside it, so the feed
    # reads as a single right-aligned block: tag | name | weapon slot | victim
    pad, gap, slot = 10, 10, 60             # slot fits rifle + headshot medal
    wt, wm = cw(tag, fs), min(cw(me, fs), 70)
    victims = [v.upper() for v in feed]
    wvs = [min(cw(v, fs), 112) for v in victims]
    fixed = pad + wt + 3 + wm + gap + slot + gap + pad
    wv_max = max(wvs, default=0)
    squeeze = min(1.0, (262 - fixed) / wv_max) if wv_max else 1.0   # stay clear of the compass
    w = fixed + wv_max * squeeze
    x = RX - w
    gx0 = x + pad + wt + 3 + wm + gap
    vx = gx0 + slot + gap
    for k, victim in enumerate(victims):
        wv = wvs[k] * squeeze
        y = y0 + k * rh
        if k % 4 == 1:
            glyph = rifle(gx0, y + 5) + headshot(gx0 + 47, y + 4)
        elif k % 4 == 2:
            glyph = knife(gx0 + (slot - 31) / 2, y + 6)
        else:
            glyph = rifle(gx0 + (slot - 42) / 2, y + 5)
        rows.append(
            f'<g class="in-right" {d(3.0 + k * .16)}>'
            f'<path d="{chamfer(x, y, w, 22, 6, ("tl",))}" fill="#000" fill-opacity=".58"/>'
            f'<rect x="{n(x)}" y="{y}" width="2" height="22" fill="{C["friend"]}"/>'
            + fit(n(x + pad), y + 16.5, tag, fs, n(wt), cls="cond fr", extra='fill-opacity=".62"')
            + fit(n(x + pad + wt + 3), y + 16.5, me, fs, n(wm), cls="cond fr")
            + glyph
            + fit(n(vx), y + 16.5, victim, fs, n(wv), cls="cond en")
            + "</g>"
        )
    return "".join(rows)


def target(intel) -> str:
    e, t = C["enemy"], C["text"]
    hw, hh, arm = 50, 40, 15
    br = "".join(
        f"M{TX + sx * hw} {TY + sy * (hh - arm)}V{TY + sy * hh}H{TX + sx * (hw - arm)}"
        for sx in (-1, 1) for sy in (-1, 1)
    )
    arcs = []
    for k in range(4):
        a0 = math.radians(k * 90 + 20)
        a1 = math.radians(k * 90 + 70)
        r = 47
        arcs.append(f"M{n(TX + r * math.cos(a0))} {n(TY + r * math.sin(a0))}A{r} {r} 0 0 1 {n(TX + r * math.cos(a1))} {n(TY + r * math.sin(a1))}")
    dist = max(1, intel["xp_next"] - intel["xp"])
    oy = TY - 104
    hm = "".join(f"M{n(TX + sx * 6)} {n(TY + sy * 6)}L{n(TX + sx * 14)} {n(TY + sy * 14)}" for sx in (-1, 1) for sy in (-1, 1))
    return (
        f'<g class="in" {d(3.0)}>'
        f'<g class="ring"><circle cx="{TX}" cy="{TY}" r="66" fill="none" stroke="{t}" stroke-opacity=".38" stroke-width="1.2" stroke-dasharray="2 6"/></g>'
        f'<path d="{"".join(arcs)}" fill="none" stroke="{t}" stroke-opacity=".3" stroke-width="1"/>'
        f"</g>"
        f'<g class="lock"><path class="lkc" d="{br}" fill="none" stroke="{e}" stroke-width="2.2"/></g>'
        f'<g class="in" {d(3.55)}>'
        # callout sits outside the r=66 ring: leader from the bracket corner
        f'<path d="M{TX + hw + 3} {TY - hh - 3}L{TX + hw + 13} {TY - hh - 13}H{TX + hw + 34}" fill="none" '
        f'stroke="{e}" stroke-opacity=".75" stroke-width="1.2"/>'
        f'<text x="{TX + hw + 38}" y="{TY - hh - 9}" class="mono en cap">LOCKED</text>'
        f'<text x="{TX + hw + 38}" y="{TY - hh + 7}" class="mono sub" font-size="11" font-weight="700" letter-spacing=".6">HIGH VALUE TARGET</text>'
        f'<path d="M{TX} {TY - 4}v8M{TX - 4} {TY}h8" stroke="{t}" stroke-opacity=".7" stroke-width="1.2"/>'
        f"</g>"
        f'<g class="in-down" {d(3.4)}>'
        f'<path d="M{TX} {oy - 13}l13 13-13 13-13-13z" fill="#000" fill-opacity=".55" stroke="{t}" stroke-width="1.6"/>'
        f'<text x="{TX}" y="{oy + 6.5}" text-anchor="middle" class="cond" font-size="19">A</text>'
        f'<text x="{TX}" y="{oy + 30}" text-anchor="middle" class="mono" font-size="12" font-weight="700">{dist}m</text>'
        f'<path d="M{TX} {oy + 36}V{TY - 72}" stroke="{t}" stroke-opacity=".35" stroke-dasharray="2 3"/>'
        f"</g>"
        f'<path class="hm" d="{hm}" stroke="{t}" stroke-width="2.2" stroke-linecap="square"/>'
        f'<text class="pts cond gold" x="{TX}" y="{TY + 32}" text-anchor="middle" font-size="22" stroke="#000" stroke-opacity=".7" stroke-width="3" paint-order="stroke">+100</text>'
    )


def weapon(cfg) -> str:
    RX = 968
    lo = cfg["loadout"]
    name = lo["primary"]["name"].upper()
    nw = cw(name, 20)
    mag, reserve = 30, 210
    col = RX - 102                      # reserve / rounds column
    big = cw(str(mag), 60)
    ticks = "".join(f"M{col + 1 + k * 3.4:.1f} 501v10" for k in range(mag))
    rw = cw(str(reserve), 26)
    return (
        f'<g class="in-right" {d(3.3)}>'
        f'{c4(RX - 92, 404)}<text x="{RX - 68}" y="418" class="mono" font-size="13" font-weight="700">1</text>'
        f'{stim(RX - 40, 402)}<text x="{RX}" y="418" text-anchor="end" class="mono" font-size="13" font-weight="700">1</text>'
        + fit(n(RX - nw), 450, name, 20, n(nw))
        + fit(n(col - 12 - big), 512, str(mag), 60, n(big))
        + f'<path d="M{col - 4} 470L{col - 10} 512" stroke="{C["text"]}" stroke-opacity=".3"/>'
        + fit(n(col), 492, str(reserve), 26, n(rw), cls="cond sub")
        + f'<text x="{RX}" y="491" text-anchor="end" class="mono dim cap">AUTO</text>'
        f'<path d="{ticks}" stroke="{C["text"]}" stroke-opacity=".85" stroke-width="1.8"/>'
        f"</g>"
    )


def title_card(cfg) -> str:
    name = cfg["name"].upper()
    x0, yb = 36, 334
    size = max(72.0, min(100.0, 100 * 540 / max(1.0, cw(name, 100))))
    nat = min(cw(name, size), 560)             # very long names squeeze, never spill
    letters = "".join(
        ch if ch == " " else f'<tspan {d(1.0 + k * .05)}>{esc(ch)}</tspan>' for k, ch in enumerate(name)
    )
    tag, cs = f"[{cfg['clan']}]", cfg["callsign"].upper()
    tw, cw_ = cw(tag, 30), min(cw(cs, 30), 420)
    disc = ' <tspan class="acc">·</tspan> '.join(esc(x.upper()) for x in cfg.get("disciplines", []))
    return (
        f'<g class="in-left" {d(.9)}>'
        f'<rect x="{x0 + 2}" y="232" width="4" height="13" fill="{C["accent"]}"/>'
        f'<text x="{x0 + 14}" y="244" class="mono acc" font-size="12" font-weight="700" letter-spacing="3">OPERATOR</text>'
        f'<rect x="{x0 + 108}" y="238" width="120" height="1" fill="{C["text"]}" fill-opacity=".3"/>'
        f'<rect x="{x0 + 236}" y="231" width="38" height="16" fill="none" stroke="{C["accent"]}" stroke-opacity=".7"/>'
        f'<text x="{x0 + 255}" y="243.5" text-anchor="middle" class="mono acc" font-size="11" font-weight="700" letter-spacing="1">{esc(cfg["clan"])}</text>'
        f"</g>"
        # drop shadow reveals letter by letter with the name, never ahead of it
        f'<text x="{x0 + 2}" y="{yb + 2}" class="cond nms" font-size="{n(size)}" textLength="{n(nat)}" lengthAdjust="spacingAndGlyphs" style="fill:#000" fill-opacity=".5">{letters}</text>'
        f'<text class="cond nm" x="{x0}" y="{yb}" font-size="{n(size)}" textLength="{n(nat)}" lengthAdjust="spacingAndGlyphs">{letters}</text>'
        f'<g class="in-left" {d(1.7)}>'
        + fit(x0 + 2, yb + 42, tag, 30, n(tw), cls="cond acc")
        + fit(n(x0 + 2 + tw + 8), yb + 42, cs, 30, n(cw_))
        + "</g>"
        f'<g class="in" {d(1.95)}>'
        f'<text x="{x0 + 2}" y="{yb + 70}" class="mono sub" font-size="13" font-weight="700" letter-spacing="2.5">{disc}</text>'
        f"</g>"
    )


def typewriter(cfg, intel):
    first, *rest = cfg["name"].split()
    last = " ".join(rest)
    callsign = cfg["callsign"].title()
    lines = [
        f"DAY {intel['day_number']} — {cfg['intro_time']}",
        f'{intel["rank_short"]} {first} "{callsign}" {last}',
        cfg["role"],
        cfg["location_line"],
    ]
    x0, y0, lh, size = 40, 440, 20, 14
    adv = .6 * size
    cps, t, pause = .022, .4, .2
    out, css = [], []
    for li, line in enumerate(lines):
        y = y0 + li * lh
        spans = []
        for k, ch in enumerate(line):
            if ch == " ":
                spans.append(" ")
            else:
                spans.append(f'<tspan style="animation-delay:{t + k * cps:.3f}s">{esc(ch)}</tspan>')
        L = min(len(line) * adv, 690)
        cls = "mono tw" + (" acc" if li == 0 else "")
        weight = ' font-weight="700"' if li < 2 else ""
        out.append(f'<text x="{x0}" y="{y}" class="{cls}" font-size="{size}"{weight} textLength="{n(L)}" '
                   f'lengthAdjust="spacingAndGlyphs" xml:space="preserve">{"".join(spans)}</text>')
        dur = len(line) * cps
        if li < len(lines) - 1:
            # the cursor types the line, then waits at its end through the pause
            # and hands over to the next line with no dark gap in between
            hold = 100 * dur / (dur + pause)
            css.append(f"@keyframes cm{li}{{from{{opacity:1;transform:translateX(0)}}"
                       f"{hold:.1f}%,to{{opacity:1;transform:translateX({n(L)}px)}}}}")
            out.append(
                f'<rect x="{x0}" y="{y - 12}" width="8" height="15" fill="{C["accent"]}" '
                f'style="opacity:0;animation:cm{li} {dur + pause:.3f}s steps({len(line)},start) {t:.3f}s"/>'
            )
        else:
            css.append(f"@keyframes cm{li}{{from{{transform:translateX({n(-L)}px)}}to{{transform:none}}}}")
            out.append(
                f'<g style="animation:cin .01s {t:.3f}s backwards">'
                f'<rect x="{n(x0 + L + 3)}" y="{y - 12}" width="8" height="15" fill="{C["accent"]}" '
                f'style="animation:cm{li} {dur:.3f}s steps({len(line)},start) {t:.3f}s backwards,blink 1.1s steps(2,jump-none) {t + dur:.3f}s infinite"/>'
                f"</g>"
            )
        t += dur + pause
    return "".join(out), "".join(css)


def clock(x, y, hhmmss: str) -> str:
    """Ticking HH:MM:SS: the static frame reads the configured intro time."""
    try:
        hh, mm, ss = (int(p) for p in hhmmss.split(":"))
    except ValueError:
        return f'<text x="{x}" y="{y}" text-anchor="end" class="mono" font-size="12" font-weight="700">{esc(hhmmss)}</text>'
    adv = 7.2
    x0 = x - 8 * adv
    fixed = f"{hh:02d}:{mm // 10}"            # columns 0-3; 4 and 6-7 roll, 5 is ':'
    out = [f'<text x="{n(x0)}" y="{y}" class="mono" font-size="12" font-weight="700" textLength="{n(4 * adv - 1.2)}" lengthAdjust="spacingAndGlyphs">{fixed}</text>',
           f'<text x="{n(x0 + 5 * adv)}" y="{y}" class="mono" font-size="12" font-weight="700">:</text>']
    cols = [  # (column index, start digit, digit count, step seconds, phase seconds)
        (4, mm % 10, 10, 60, 60 - ss),
        (6, ss // 10, 6, 10, 10 - ss % 10),
        (7, ss % 10, 10, 1, 1),
    ]
    for col, start, count, stp, first in cols:
        cx = x0 + col * adv
        digits = "".join(
            f'<text x="{n(cx)}" y="{y + k * 16}" class="mono" font-size="12" font-weight="700">{(start + k) % (10 if count == 10 else 6)}</text>'
            for k in range(count)
        )
        period = count * stp
        delay = -(stp - first)
        out.append(
            f'<g clip-path="url(#clk)"><g style="animation:clk{count} {period}s steps({count},end) {delay}s infinite">{digits}</g></g>'
        )
    return "".join(out)


def letterbox(cfg, intel) -> str:
    xp_lo, xp_hi, xp = intel["xp_level_floor"], intel["xp_next"], intel["xp"]
    frac = 1.0 if xp_hi <= xp_lo else (xp - xp_lo) / (xp_hi - xp_lo)
    yb = H - LB
    bar_x, bar_w = 96, 220
    t = C["text"]
    return (
        f'<rect class="lbt" x="0" y="0" width="{W}" height="{LB}" fill="#000"/>'
        f'<rect class="lbb" x="0" y="{yb}" width="{W}" height="{LB}" fill="#000"/>'
        f'<g class="in" {d(1.0)}>'
        f'<circle class="blink" cx="30" cy="16" r="3.5" fill="{C["enemy"]}"/>'
        f'<text x="40" y="20.5" class="mono en cap">LIVE</text>'
        f'<text x="86" y="20.5" class="mono dim cap">SAT-2 OVERWATCH  ·  ZOOM 1.0X</text>'
        f'<text x="{W - 104}" y="20.5" text-anchor="end" class="mono dim cap">GRID 43R FK 4721 1833</text>'
        f"{clock(W - 26, 20.5, cfg.get('intro_time', '00:00:00'))}"
        f"</g>"
        f'<g class="in" {d(3.6)}>'
        f'<text x="30" y="{yb + 21}" class="mono sub cap">LVL</text>'
        f'<text x="60" y="{yb + 22}" class="cond gold" font-size="19">{intel["level"]}</text>'
        f'<rect x="{bar_x}" y="{yb + 14}" width="{bar_w}" height="3" fill="{t}" fill-opacity=".14"/>'
        f'<rect class="in-wipe" {d(3.7)} x="{bar_x}" y="{yb + 14}" width="{bar_w * max(0, min(1, frac)):.1f}" height="3" fill="{C["gold"]}"/>'
        f'<text x="{bar_x + bar_w + 12}" y="{yb + 20.5}" class="mono sub" font-size="11">{xp:,} / {xp_hi:,} XP</text>'
        f'<text x="{W - 30}" y="{yb + 20.5}" text-anchor="end" class="mono sub cap">'
        f'{esc(intel["rank"].upper())}  ·  <tspan class="gold">PRESTIGE {roman(intel["prestige"])}</tspan></text>'
        f"</g>"
    )


def grid_refs() -> str:
    out = []
    for k, y in enumerate(range(100, H - LB, 100)):
        if free(10, y):
            out.append(f'<text x="8" y="{y + 4}" class="mono" font-size="11" fill-opacity=".4">{18 - k:02d}</text>')
    for k, x in enumerate(range(100, W, 100)):
        if free(x, H - LB - 10):
            out.append(f'<text x="{x + 4}" y="{H - LB - 7}" class="mono" font-size="11" fill-opacity=".4">{47 + k}</text>')
    return "".join(out)


def render(cfg, intel):
    heading = round(bearing(PX, PY, TX, TY)) - 9
    img, topo, spots = build_map()
    tw, tw_css = typewriter(cfg, intel)
    outline = chamfer(.5, .5, W - 1, H - 1, 18)
    # ui.py's default `text:not([fill])` outranks a bare `.acc` (0,1,1 vs 0,1,0),
    # so restate the palette classes at equal specificity, later in the sheet
    tone = {"sub": "sub", "dim": "dim", "acc": "accent", "fr": "friend", "en": "enemy", "gold": "gold"}
    css = (
        "".join(f"text.{k}{{fill:{C[v]}}}" for k, v in tone.items())
        + f".zoom{{animation:zoom 2.2s cubic-bezier(.16,.84,.24,1) backwards;transform-origin:{TX}px {TY}px}}"
        "@keyframes zoom{from{transform:scale(1.3)}}"
        ".blk{opacity:0;animation:blk 1.4s ease-out}"
        "@keyframes blk{0%,18%{opacity:1}100%{opacity:0}}"
        ".lbt,.lbb{animation:lb 1.3s cubic-bezier(.7,0,.2,1) .1s backwards;transform-box:fill-box;transform-origin:50% 0}"
        ".lbb{transform-origin:50% 100%}"
        "@keyframes lb{from{transform:scaleY(5)}}"
        ".scan{opacity:0;animation:scan 1.5s cubic-bezier(.45,0,.55,1) .3s}"
        f"@keyframes scan{{0%{{opacity:0;transform:translateY(0)}}12%{{opacity:1}}85%{{opacity:1}}100%{{opacity:0;transform:translateY({H - 2 * LB - 10}px)}}}}"
        ".tw tspan{animation:ty 1ms steps(1) backwards}"   # char shows the moment the cursor steps past it
        "@keyframes ty{from,to{fill-opacity:0}}"
        "@keyframes cin{from,to{opacity:0}}"
        ".nm tspan{animation:nm .6s ease-out backwards}"
        ".nms tspan{animation:nms .6s ease-out backwards}@keyframes nms{from{fill-opacity:0}}"
        f"@keyframes nm{{0%{{fill-opacity:0;fill:{C['accent']}}}30%{{fill-opacity:1;fill:{C['accent']}}}100%{{fill:{C['text']}}}}}"
        f".sweep{{animation:sweep 3.2s linear infinite;transform-origin:92px 120px}}"
        "@keyframes sweep{to{transform:rotate(360deg)}}"
        ".ping{opacity:0;animation:ping 2.1s ease-out infinite;transform-box:fill-box;transform-origin:center}"
        "@keyframes ping{0%{opacity:.9;transform:scale(.6)}100%{opacity:0;transform:scale(3)}}"
        f".ring{{animation:spin 40s linear infinite;transform-origin:{TX}px {TY}px}}"
        f".lock{{animation:lock .55s cubic-bezier(.2,.9,.3,1.15) 3.1s backwards;transform-origin:{TX}px {TY}px}}"
        "@keyframes lock{0%{opacity:0;transform:scale(2.4)}35%{opacity:1}100%{transform:scale(1)}}"
        f".lkc{{animation:lkc .6s steps(1) 3.1s backwards}}@keyframes lkc{{from,to{{stroke:{C['text']}}}}}"
        f".hm{{opacity:0;animation:hm 4s ease-out 4.6s infinite;transform-origin:{TX}px {TY}px}}"
        "@keyframes hm{0%{opacity:1;transform:scale(1.5)}6%{opacity:1;transform:scale(1)}16%{opacity:0}100%{opacity:0}}"
        ".pts{opacity:0;animation:pts 4s ease-out 4.65s infinite}"
        "@keyframes pts{0%{opacity:0;transform:translateY(6px)}6%{opacity:1}30%{opacity:1;transform:translateY(-12px)}42%{opacity:0;transform:translateY(-16px)}100%{opacity:0}}"
        ".cpan{animation:cpan 1.8s cubic-bezier(.2,.8,.2,1) 2.75s backwards}"
        "@keyframes cpan{from{transform:translateX(-120px)}}"
        "@keyframes clk10{to{transform:translateY(-160px)}}@keyframes clk6{to{transform:translateY(-96px)}}"
        + tw_css
    )
    defs = (
        f'<clipPath id="cv"><path d="{outline}"/></clipPath>'
        f'<clipPath id="mmclip"><circle cx="92" cy="120" r="58"/></clipPath>'
        f'<clipPath id="clk"><rect x="{W - 100}" y="8" width="90" height="16"/></clipPath>'
        '<radialGradient id="vig" cx="50%" cy="48%" r="72%">'
        '<stop offset=".5" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".78"/></radialGradient>'
        '<radialGradient id="scrim" cx="260" cy="350" r="380" gradientUnits="userSpaceOnUse" gradientTransform="translate(260 350) scale(1 .62) translate(-260 -350)">'
        '<stop offset="0" stop-color="#050605" stop-opacity=".78"/><stop offset=".55" stop-color="#050605" stop-opacity=".55"/>'
        '<stop offset="1" stop-color="#050605" stop-opacity="0"/></radialGradient>'
        '<radialGradient id="scrim2" cx="860" cy="455" r="200" gradientUnits="userSpaceOnUse" gradientTransform="translate(860 455) scale(1 .6) translate(-860 -455)">'
        '<stop offset="0" stop-color="#050605" stop-opacity=".7"/><stop offset="1" stop-color="#050605" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="fovg" cx="92" cy="120" r="44" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{C["friend"]}" stop-opacity=".4"/><stop offset="1" stop-color="{C["friend"]}" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="scang" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{C["accent"]}" stop-opacity="0"/><stop offset="1" stop-color="{C["accent"]}" stop-opacity=".14"/></linearGradient>'
        '<linearGradient id="cfade" x1="0" x2="1">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".22" stop-color="#fff"/>'
        '<stop offset=".78" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="cmask"><rect x="{W / 2 - 196}" y="36" width="392" height="56" fill="url(#cfade)"/></mask>'
    )
    body = (
        f'<path d="{outline}" fill="{C["bg"]}"/>'
        + map_layer(img, topo, spots, "cv")
        + '<g clip-path="url(#cv)">'
        f'<rect width="{W}" height="{H}" fill="url(#vig)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#scrim)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#scrim2)"/>'
        f'<rect width="{W}" height="{H}" fill="#000" filter="url(#grain)"/>'
        f'<g class="scan"><rect x="0" y="{LB - 40}" width="{W}" height="40" fill="url(#scang)"/>'
        f'<rect x="0" y="{LB - 1}" width="{W}" height="1" fill="{C["accent"]}" fill-opacity=".7"/></g>'
        + grid_refs()
        + compass(heading)
        + minimap(heading)
        + killfeed(cfg)
        + target(intel)
        + weapon(cfg)
        + title_card(cfg)
        + letterbox(cfg, intel)
        + f'<rect class="blk" width="{W}" height="{H}" fill="#000"/>'
        + tw                     # types crisp over the fade from black
        + "</g>"
        f'<path d="{outline}" fill="none" stroke="{C["line2"]}"/>'
    )
    title = f'{cfg["name"]} "{cfg["callsign"]}": {cfg["role"]}. Level {intel["level"]} {intel["rank"]}.'
    return {"hero.svg": svg(W, H, title, body, css=css, defs=defs)}
