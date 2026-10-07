"""
Shared design system for every HUD panel: colour, type, frames and motion.

Rules every component follows
-----------------------------
1. Canvas width is 1000. GitHub shows it at ~840px, so nothing smaller than
   11px in viewBox units, and body copy at 13px or more.
2. The resting frame is the finished frame. Entrances use the `.in*` classes
   below, which fill *backwards*: before the delay the element is hidden, and
   after it (or in any renderer that never runs CSS animations) it is fully
   visible. Never give real content a base style of opacity 0.
3. Entrance classes animate `transform`, which REPLACES an element's
   transform attribute while running. Put them on a <g> with no transform
   attribute and position the content inside it.
4. Infinite animations only on small elements. Never on a group that carries
   a filter or holds most of the canvas (it re-rasterises every frame).
5. Fonts are system stacks (no downloads): COND resolves to DIN Condensed on
   macOS/iOS and Bahnschrift on Windows. Text widths differ by platform, so
   leave slack, and use textLength (see `fit`) for anything that must land
   exactly.
"""
from __future__ import annotations

from html import escape

C = dict(
    bg="#0A0B0A",
    panel="#0F110F",
    panel2="#151815",
    line="#232722",
    line2="#343933",
    text="#ECEEE6",
    sub="#969C90",
    dim="#5C6258",
    accent="#C6F432",   # tactical lime: selection, highlights, progress
    accent2="#7E9A1C",
    friend="#5CB8FF",   # friendly names, killfeed left side
    enemy="#FF4B3E",    # enemy names, damage, alerts
    gold="#F4B740",     # XP, medals, prestige
)

COND = ("'DIN Condensed','Bahnschrift Condensed','Bahnschrift SemiBold Condensed','Barlow Condensed',"
        "'Roboto Condensed','Arial Narrow',Bahnschrift,'Helvetica Neue',Arial,sans-serif")
SANS = "'Helvetica Neue','Segoe UI',Roboto,Arial,sans-serif"
MONO = "'SF Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"

W = 1000

BASE_CSS = f"""
text{{font-family:{SANS}}}
:where(text:not([fill])){{fill:{C['text']}}}
.cond{{font-family:{COND};font-stretch:condensed;font-weight:700}}
.mono{{font-family:{MONO}}}
.sub{{fill:{C['sub']}}}.dim{{fill:{C['dim']}}}.acc{{fill:{C['accent']}}}
.fr{{fill:{C['friend']}}}.en{{fill:{C['enemy']}}}.gold{{fill:{C['gold']}}}
.cap{{font-size:11px;font-weight:700;letter-spacing:2.4px}}
.in{{animation:in-fade .5s ease-out backwards}}
.in-up{{animation:in-up .55s cubic-bezier(.2,.8,.2,1) backwards}}
.in-down{{animation:in-down .55s cubic-bezier(.2,.8,.2,1) backwards}}
.in-left{{animation:in-left .6s cubic-bezier(.2,.8,.2,1) backwards}}
.in-right{{animation:in-right .6s cubic-bezier(.2,.8,.2,1) backwards}}
.in-scale{{animation:in-scale .5s cubic-bezier(.2,.8,.2,1) backwards;transform-box:fill-box;transform-origin:center}}
.in-wipe{{animation:in-wipe .7s cubic-bezier(.6,0,.2,1) backwards;transform-box:fill-box;transform-origin:left center}}
@keyframes in-fade{{from{{opacity:0}}}}
@keyframes in-up{{from{{opacity:0;transform:translateY(14px)}}}}
@keyframes in-down{{from{{opacity:0;transform:translateY(-14px)}}}}
@keyframes in-left{{from{{opacity:0;transform:translateX(-24px)}}}}
@keyframes in-right{{from{{opacity:0;transform:translateX(24px)}}}}
@keyframes in-scale{{from{{opacity:0;transform:scale(.6)}}}}
@keyframes in-wipe{{from{{transform:scaleX(0)}}}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.blink{{animation:blink 1.4s steps(2,jump-none) infinite}}
.spin{{animation:spin 8s linear infinite;transform-box:fill-box;transform-origin:center}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""

COMMON_DEFS = f"""
<filter id="grain" x="0" y="0" width="100%" height="100%">
  <feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="11" stitchTiles="stitch"/>
  <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .06 0"/>
</filter>
<pattern id="grid8" width="8" height="8" patternUnits="userSpaceOnUse">
  <path d="M8 0H0V8" fill="none" stroke="{C['line']}" stroke-width=".6"/>
</pattern>
<pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
  <rect width="2" height="6" fill="{C['line']}"/>
</pattern>
"""


def esc(s) -> str:
    """Escape text content."""
    return escape(str(s), quote=False)


def attr(s) -> str:
    """Escape an attribute value."""
    return escape(str(s), quote=True)


def d(delay: float) -> str:
    """Inline animation delay, e.g. <g class="in-up" {d(.4)}>."""
    return f'style="animation-delay:{delay:.2f}s"'


def svg(w: int, h: int, title: str, body: str, css: str = "", defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{attr(title)}"><title>{esc(title)}</title>'
        f"<style>{BASE_CSS}{css}</style><defs>{COMMON_DEFS}{defs}</defs>{body}</svg>\n"
    )


def chamfer(x, y, w, h, c=14, corners=("tl", "br")) -> str:
    """Path data for a rectangle with 45-degree cut corners."""
    tl, tr, br, bl = (c if k in corners else 0 for k in ("tl", "tr", "br", "bl"))
    return (
        f"M{x + tl} {y}H{x + w - tr}L{x + w} {y + tr}V{y + h - br}L{x + w - br} {y + h}"
        f"H{x + bl}L{x} {y + h - bl}V{y + tl}Z"
    )


def canvas(w: int, h: int, grain: bool = True) -> str:
    """Full-bleed section background: chamfered plate, fine grid, grain."""
    p = chamfer(0.5, 0.5, w - 1, h - 1, 18)
    out = [
        f'<path d="{p}" fill="{C["bg"]}"/>',
        f'<path d="{p}" fill="url(#grid8)" opacity=".35"/>',
    ]
    if grain:
        out.append(f'<path d="{p}" fill="#000" filter="url(#grain)"/>')
    out.append(f'<path d="{p}" fill="none" stroke="{C["line2"]}"/>')
    return "".join(out)


def frame(x, y, w, h, c=10, fill=None, stroke=None, ticks=True) -> str:
    """A chamfered panel with optional accent corner ticks."""
    out = [f'<path d="{chamfer(x, y, w, h, c)}" fill="{fill or C["panel"]}" stroke="{stroke or C["line2"]}"/>']
    if ticks:
        a = C["accent"]
        out.append(
            f'<path d="M{x + w - 14} {y + 0.5}H{x + w - 0.5}V{y + 14}M{x + 0.5} {y + h - 14}V{y + h - 0.5}H{x + 14}" '
            f'fill="none" stroke="{a}" stroke-width="1.6"/>'
        )
    return "".join(out)


def fit(x, y, text, size, length, cls="cond", anchor="start", extra="") -> str:
    """Text forced to an exact rendered width, whatever font the viewer has."""
    return (
        f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}" text-anchor="{anchor}" '
        f'textLength="{length}" lengthAdjust="spacingAndGlyphs" {extra}>{esc(text)}</text>'
    )


def header(index: str, kicker: str, title: str, right: str = "", x=36, y=58, w=W) -> str:
    """Standard section header: '02  // LOADOUT' over a big condensed title."""
    return (
        f'<g class="in-left">'
        f'<text x="{x}" y="{y - 26}" class="mono acc" font-size="12" font-weight="700">{esc(index)}</text>'
        f'<text x="{x + 26}" y="{y - 26}" class="mono sub cap">{esc("// " + kicker)}</text>'
        f'<text x="{x - 2}" y="{y + 10}" class="cond" font-size="40" letter-spacing=".5">{esc(title)}</text>'
        f"</g>"
        f'<rect x="{x}" y="{y + 22}" width="{w - 2 * x}" height="1" fill="{C["line2"]}"/>'
        f'<rect class="in-wipe" x="{x}" y="{y + 21}" width="56" height="3" fill="{C["accent"]}"/>'
        + (f'<text x="{w - x}" y="{y + 8}" text-anchor="end" class="mono sub cap">{esc(right)}</text>' if right else "")
    )


def bar(x, y, w, frac, delay=0.0, h=6, color=None, track=None) -> str:
    """Stat bar whose fill wipes in from the left."""
    frac = max(0.0, min(1.0, frac))
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{track or C["line"]}"/>'
        f'<rect class="in-wipe" {d(delay)} x="{x}" y="{y}" width="{w * frac:.1f}" height="{h}" fill="{color or C["accent"]}"/>'
    )


def chip(x, y, text, fg=None, bg=None, size=11, pad=8, chars_w=7.2) -> str:
    """Small filled label; width estimated generously from character count."""
    w = len(text) * chars_w + pad * 2
    return (
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{size + 9}" fill="{bg or C["accent"]}"/>'
        f'<text x="{x + pad}" y="{y + size + 3.5}" class="mono" font-size="{size}" font-weight="700" '
        f'fill="{fg or C["bg"]}" letter-spacing="1">{esc(text)}</text>'
    )


def roman(n: int) -> str:
    out, vals = "", [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    for v, s in vals:
        while n >= v:
            out, n = out + s, n - v
    return out or "0"
