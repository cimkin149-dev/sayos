#!/usr/bin/env python3
"""Generate every SayMy OS visual asset from code.

Run from the project root:   python3 design/generate_assets.py
Needs: rsvg-convert (librsvg2-bin) and ImageMagick `convert`.

The brand is defined in design/tokens/tokens.json; this script only draws.
Edit the tokens or the drawing functions, re-run, rebuild the ISO.
"""
import json, math, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOK = json.loads((ROOT / "design/tokens/tokens.json").read_text())
C = {k: v["hex"] for k, v in TOK["color"].items()}
INC = ROOT / "config/includes.chroot"
SHARE = INC / "usr/share/saymy"


def run(*cmd):
    subprocess.run(cmd, check=True)


def svg_to_png(svg: str, out: Path, w: int, h: int):
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.svg")
    tmp.write_text(svg)
    run("rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(out), str(tmp))
    tmp.unlink()


def to_jpg(png: Path, jpg: Path, q=88):
    run("convert", str(png), "-quality", str(q), str(jpg))
    png.unlink()


# ---------------------------------------------------------------- the mark
def mark_svg(bubble="url(#sun)", ink=None, size=512, standalone=True):
    """Speech bubble whose content is a rising sun; the rays double as sound waves."""
    ink = ink or C["lake_night"]
    cx, cy = 256, 296
    rays = ""
    for a in (20, 55, 90, 125, 160):
        r1, r2 = 90, 120
        x1 = cx + r1 * math.cos(math.radians(a)); y1 = cy - r1 * math.sin(math.radians(a))
        x2 = cx + r2 * math.cos(math.radians(a)); y2 = cy - r2 * math.sin(math.radians(a))
        rays += f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{ink}" stroke-width="15" stroke-linecap="round"/>'
    body = f'''
  <path d="M96 64H416A48 48 0 0 1 464 112V320A48 48 0 0 1 416 368H232L136 448V368H96A48 48 0 0 1 48 320V112A48 48 0 0 1 96 64Z" fill="{bubble}"/>
  <path d="M{cx-64} {cy}A64 64 0 0 1 {cx+64} {cy}Z" fill="{ink}"/>
  <rect x="{cx-92}" y="{cy+10}" width="184" height="13" rx="6.5" fill="{ink}"/>
  {rays}'''
    defs = f'''<defs><linearGradient id="sun" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{C['savanna_gold']}"/><stop offset="1" stop-color="{C['sunrise']}"/></linearGradient></defs>'''
    if not standalone:
        return body
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="{size}" height="{size}">{defs}{body}</svg>'


def logo_horizontal(dark=True):
    word = C["bark_cloth"] if dark else C["lake_night"]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 512" width="1600" height="512">
<defs><linearGradient id="sun" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C['savanna_gold']}"/><stop offset="1" stop-color="{C['sunrise']}"/></linearGradient></defs>
<g>{mark_svg(standalone=False)}</g>
<text x="548" y="330" font-family="Inter, Noto Sans, sans-serif" font-size="196" font-weight="800" letter-spacing="-4" fill="{word}">SayMy<tspan font-weight="300" fill="{C['sunrise']}" dx="28">OS</tspan></text>
</svg>'''


# ---------------------------------------------------------------- pattern
def pattern_defs(pid="bark", color="#FFFFFF", opacity=0.07, s=96):
    """Bark-cloth inspired geometry: nested diamonds with a dotted spine."""
    h = s / 2
    return f'''<pattern id="{pid}" width="{s}" height="{s}" patternUnits="userSpaceOnUse">
  <g fill="none" stroke="{color}" stroke-opacity="{opacity}" stroke-width="2">
    <path d="M{h} 6L{s-6} {h}L{h} {s-6}L6 {h}Z"/>
    <path d="M{h} 24L{s-24} {h}L{h} {s-24}L24 {h}Z"/>
    <path d="M0 0L{s} 0M0 {s}L{s} {s}"/>
  </g>
  <circle cx="{h}" cy="{h}" r="4" fill="{color}" fill-opacity="{opacity*1.6}"/>
</pattern>'''


# ---------------------------------------------------------------- wallpapers
PHASES = {
    #            sky top,    sky mid,    horizon,   sun/moon,  sun_y, hill1,     hill2,     lake,      glow
    "sunrise": ("#2B2F6B", "#C2527A", "#FFB45E", "#FFE2A8", 0.55, "#2A2447", "#171A36", "#E0884F", 0.55),
    "day":     ("#1C6FB8", "#4FA6E0", "#BFE6F7", "#FFF6D6", 0.28, "#2E6F55", "#1D4A45", "#3E9AD0", 0.35),
    "dusk":    ("#1B1740", "#8B2F5E", "#FF7A2F", "#FFC15C", 0.56, "#2B1A3A", "#150E27", "#C24E3A", 0.60),
    "night":   ("#050B16", "#0C1A2A", "#183A5A", "#EAF1FF", 0.30, "#0B1626", "#07101C", "#10304D", 0.18),
}


def hills(w, h, y0, amp, seed, fill):
    pts = []
    n = 14
    for i in range(n + 1):
        x = w * i / n
        y = y0 + amp * math.sin(i * 0.9 + seed) + amp * 0.5 * math.sin(i * 2.3 + seed * 2)
        pts.append((x, y))
    d = f"M0 {h}L0 {pts[0][1]:.0f}"
    for i in range(1, len(pts)):
        px, py = pts[i - 1]; x, y = pts[i]
        d += f"C{(px+x)/2:.0f} {py:.0f} {(px+x)/2:.0f} {y:.0f} {x:.0f} {y:.0f}"
    d += f"L{w} {h}Z"
    return f'<path d="{d}" fill="{fill}"/>'


def acacia(x, y, s, fill):
    """Flat-topped acacia silhouette."""
    return f'''<g transform="translate({x} {y}) scale({s})" fill="{fill}">
  <path d="M-6 0C-4 -60 -10 -110 -34 -150L-24 -154C-6 -126 0 -108 2 -92C10 -118 26 -136 46 -150L54 -142C30 -122 14 -98 8 -60C8 -30 10 -12 12 0Z"/>
  <ellipse cx="-6" cy="-170" rx="120" ry="26"/><ellipse cx="-70" cy="-152" rx="64" ry="18"/><ellipse cx="62" cy="-156" rx="70" ry="19"/>
</g>'''


def wallpaper_svg(phase, w=2560, h=1440):
    top, mid, hor, sun, sun_k, h1, h2, lake, glow = PHASES[phase]
    horizon = h * 0.64
    sun_y = h * sun_k
    sun_x = w * 0.68
    sun_r = h * (0.055 if phase != "night" else 0.04)
    stars = ""
    if phase == "night":
        import random
        rnd = random.Random(7)
        for _ in range(140):
            stars += f'<circle cx="{rnd.random()*w:.0f}" cy="{rnd.random()*horizon*0.8:.0f}" r="{rnd.choice([1,1,1.5,2]):.1f}" fill="#EAF1FF" fill-opacity="{rnd.uniform(.3,.9):.2f}"/>'
    streaks = ""
    for i in range(18):
        yy = horizon + 18 + i * 14
        ww = 40 + (18 - i) * 14
        streaks += f'<rect x="{sun_x-ww/2:.0f}" y="{yy:.0f}" width="{ww}" height="3" rx="1.5" fill="{sun}" fill-opacity="{max(0.08, 0.5 - i*0.025):.2f}"/>'
    band_y = h * 0.90
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs>
 <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{top}"/><stop offset=".55" stop-color="{mid}"/><stop offset="1" stop-color="{hor}"/></linearGradient>
 <radialGradient id="glow" cx="{sun_x/w:.3f}" cy="{sun_y/h:.3f}" r=".55"><stop offset="0" stop-color="{sun}" stop-opacity="{glow}"/><stop offset="1" stop-color="{sun}" stop-opacity="0"/></radialGradient>
 <linearGradient id="lake" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{lake}"/><stop offset="1" stop-color="{h2}"/></linearGradient>
 {pattern_defs("bark", "#FFFFFF", 0.09)}
 <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff" stop-opacity="1"/></linearGradient>
 <mask id="m"><rect x="0" y="{band_y-140:.0f}" width="{w}" height="{h-band_y+140:.0f}" fill="url(#fade)"/></mask>
</defs>
<rect width="{w}" height="{h}" fill="url(#sky)"/>
{stars}
<rect width="{w}" height="{h}" fill="url(#glow)"/>
<circle cx="{sun_x:.0f}" cy="{sun_y:.0f}" r="{sun_r:.0f}" fill="{sun}"/>
{hills(w, h, horizon - 40, 34, 1.0, h1)}
<rect x="0" y="{horizon:.0f}" width="{w}" height="{h-horizon:.0f}" fill="url(#lake)"/>
{streaks}
{hills(w, h, h * 0.81, 24, 3.1, h2)}
{acacia(w*0.16, h * 0.81 + 14, 1.9, h2)}
{acacia(w*0.88, horizon - 22, 1.05, h1)}
<rect x="0" y="{band_y-140:.0f}" width="{w}" height="{h-band_y+140:.0f}" fill="url(#bark)" mask="url(#m)"/>
</svg>'''


# ---------------------------------------------------------------- boot art
def grub_background(w=1920, h=1080):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C['lake_night']}"/><stop offset="1" stop-color="#050B16"/></linearGradient>
<radialGradient id="r" cx=".5" cy="1.05" r=".7"><stop offset="0" stop-color="{C['sunrise']}" stop-opacity=".55"/><stop offset="1" stop-color="{C['sunrise']}" stop-opacity="0"/></radialGradient>
{pattern_defs("bark", "#FFFFFF", 0.06)}</defs>
<rect width="{w}" height="{h}" fill="url(#g)"/><rect width="{w}" height="{h}" fill="url(#bark)"/><rect width="{w}" height="{h}" fill="url(#r)"/>
<g transform="translate({w/2-70} 120) scale(.274)">{mark_svg(standalone=False)}<defs><linearGradient id="sun" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C['savanna_gold']}"/><stop offset="1" stop-color="{C['sunrise']}"/></linearGradient></defs></g>
<text x="{w/2}" y="330" text-anchor="middle" font-family="Inter, Noto Sans, sans-serif" font-size="64" font-weight="800" fill="{C['bark_cloth']}">SayMy<tspan font-weight="300" fill="{C['sunrise']}" dx="10">OS</tspan></text>
</svg>'''


def plain_logo_on(bg, w, h, scale):
    s = 512 * scale
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
<defs><linearGradient id="sun" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{C['savanna_gold']}"/><stop offset="1" stop-color="{C['sunrise']}"/></linearGradient></defs>
<rect width="{w}" height="{h}" fill="{bg}"/>
<g transform="translate({(w-s)/2:.0f} {(h-s)/2-20:.0f}) scale({scale})">{mark_svg(standalone=False)}</g></svg>'''


def main():
    # logos (source SVGs + PNGs)
    (ROOT / "design/logo").mkdir(parents=True, exist_ok=True)
    (ROOT / "design/logo/saymy-mark.svg").write_text(mark_svg())
    (ROOT / "design/logo/saymy-logo-dark.svg").write_text(logo_horizontal(True))
    (ROOT / "design/logo/saymy-logo-light.svg").write_text(logo_horizontal(False))
    (ROOT / "design/pattern/bark-cloth-pattern.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="960"><defs>{pattern_defs("bark", C["sunrise"], 0.9)}</defs><rect width="960" height="960" fill="{C["lake_night"]}"/><rect width="960" height="960" fill="url(#bark)"/></svg>')

    # app icons for the hicolor theme
    for sz in (16, 22, 24, 32, 48, 64, 128, 256, 512):
        svg_to_png(mark_svg(), INC / f"usr/share/icons/hicolor/{sz}x{sz}/apps/saymy.png", sz, sz)
    (INC / "usr/share/icons/hicolor/scalable/apps").mkdir(parents=True, exist_ok=True)
    (INC / "usr/share/icons/hicolor/scalable/apps/saymy.svg").write_text(mark_svg())
    svg_to_png(logo_horizontal(True), SHARE / "brand/saymy-logo-dark.png", 800, 256)
    svg_to_png(mark_svg(), SHARE / "brand/saymy-mark.png", 512, 512)

    # time-of-day wallpapers: the desktop follows the equatorial sky
    for phase in PHASES:
        png = SHARE / f"wallpapers/saymy-{phase}.png"
        svg_to_png(wallpaper_svg(phase), png, 2560, 1440)
        to_jpg(png, SHARE / f"wallpapers/saymy-{phase}.jpg")
        shutil_copy = ROOT / f"design/wallpapers/saymy-{phase}.jpg"
        shutil_copy.write_bytes((SHARE / f"wallpapers/saymy-{phase}.jpg").read_bytes())

    # GRUB (UEFI) + syslinux (BIOS) menus
    gb = ROOT / "config/bootloaders/grub-pc/live-theme/background.png"
    svg_to_png(grub_background(), gb, 1920, 1080)
    svg_to_png(grub_background(1920, 1080), ROOT / "config/bootloaders/isolinux/splash.png", 640, 360)

    # Plymouth boot splash + Calamares installer branding
    pl = INC / "usr/share/plymouth/themes/saymy"
    svg_to_png(mark_svg(), pl / "logo.png", 256, 256)
    svg_to_png(f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="8"><rect width="400" height="8" rx="4" fill="{C["sunrise"]}"/></svg>', pl / "bar.png", 400, 8)
    svg_to_png(f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="8"><rect width="400" height="8" rx="4" fill="{C["deep_water"]}"/></svg>', pl / "bar-bg.png", 400, 8)
    cal = INC / "usr/share/calamares/branding/saymy"
    svg_to_png(mark_svg(), cal / "logo.png", 256, 256)
    svg_to_png(logo_horizontal(True), cal / "welcome.png", 900, 288)
    print("assets generated")


if __name__ == "__main__":
    sys.exit(main())
