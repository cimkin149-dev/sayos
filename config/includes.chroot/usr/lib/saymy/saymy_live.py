"""Living Sky: wallpapers that are alive, drawn by code instead of played from video.

  * The sun and moon travel along your real clock; sky colours change continuously through the day.
  * Clouds drift, water ripples and glitters, grass and reeds sway, fireflies appear after dusk.
  * When mains power drops (Grid Down), evening falls and a lantern is lit.
  * Cost: no video decoding, no assets. Rendered at low resolution and scaled, paused on battery.

`render()` draws one frame into any cairo context, so the same code produces a live window, a still frame
for `swaybg`, a Settings thumbnail, or a test image.
"""
import math
import random

import cairo

SCENES = ["Savanna", "Highlands", "Lakeshore"]
SUNRISE, SUNSET = 6.3, 18.9

SKY_KEYS = [  # hour, top, middle, horizon
    (0.0, "#050B16", "#0C1A2A", "#183A5A"), (4.8, "#0B1230", "#2A2450", "#6A4668"),
    (5.9, "#25306E", "#B8527F", "#FFB070"), (7.2, "#2D6FB5", "#7FB6E3", "#F7D9A8"),
    (10.0, "#2578C6", "#5FAFE6", "#C9E9F8"), (13.0, "#1C6FB8", "#4FA6E0", "#BFE6F7"),
    (16.5, "#2A78C2", "#6AA9DA", "#F0D9A6"), (18.0, "#3B3B80", "#C65E70", "#FFA24A"),
    (19.0, "#1E1846", "#8A3060", "#FF7A2F"), (20.3, "#0A1330", "#1C2850", "#34406A"),
    (24.0, "#050B16", "#0C1A2A", "#183A5A"),
]
LANTERN_HOUR = 19.6


# ------------------------------------------------------------------ small helpers
def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def sky_colors(hour: float):
    hour %= 24
    for (h0, *c0), (h1, *c1) in zip(SKY_KEYS, SKY_KEYS[1:]):
        if h0 <= hour <= h1:
            t = smooth((hour - h0) / (h1 - h0))
            return tuple(mix(rgb(a), rgb(b), t) for a, b in zip(c0, c1))
    return tuple(rgb(c) for c in SKY_KEYS[0][1:])


def daylight(hour: float) -> float:
    hour %= 24
    return smooth((hour - 5.6) / 1.5) * (1 - smooth((hour - 17.9) / 1.7))


def sun_position(hour, w, h, horizon):
    u = (hour - SUNRISE) / (SUNSET - SUNRISE)
    if not 0 <= u <= 1:
        return None
    return w * (0.10 + 0.80 * u), horizon - math.sin(math.pi * u) * h * 0.46, math.sin(math.pi * u)


def moon_position(hour, w, h, horizon):
    length = 24 - (SUNSET - SUNRISE) - 0.6
    u = ((hour - (SUNSET + 0.3)) % 24) / length
    if not 0 <= u <= 1:
        return None
    return w * (0.12 + 0.76 * u), horizon - math.sin(math.pi * u) * h * 0.40, math.sin(math.pi * u)


# ------------------------------------------------------------------ deterministic world layout per scene
class World:
    def __init__(self, scene):
        r = random.Random("saymy-" + scene)
        self.stars = [(r.random(), r.random() * 0.62, r.random() * 6.28, r.choice([0.8, 1.0, 1.3, 1.7])) for _ in range(150)]
        self.clouds = []
        for layer, (n, speed, y0, y1, sc) in enumerate([(5, 5, 0.08, 0.22, 1.0), (5, 9, 0.16, 0.34, 1.3), (4, 15, 0.26, 0.42, 1.7)]):
            for _ in range(n):
                blobs = [(r.uniform(-1, 1) * 95 * sc, r.uniform(-0.3, 0.2) * 42 * sc, r.uniform(34, 66) * sc) for _ in range(7)]
                self.clouds.append({"layer": layer, "x": r.random(), "y": r.uniform(y0, y1), "speed": speed * r.uniform(0.8, 1.2), "blobs": blobs})
        self.flies = [(r.random(), 0.56 + r.random() * 0.38, r.random() * 6.28, r.random() * 6.28) for _ in range(44)]
        self.tufts = [(r.random(), r.uniform(0.9, 1.0), r.uniform(10, 34), r.random() * 6.28) for _ in range(70)]
        self.ridges = [[(r.uniform(0, 6.28), r.uniform(0.7, 1.4), r.uniform(1.6, 3.4)) for _ in range(3)] for _ in range(5)]
        self.reeds = [(r.random(), r.uniform(0.5, 1.0), r.random() * 6.28) for _ in range(34)]


_WORLDS = {}


def world(scene):
    if scene not in _WORLDS:
        _WORLDS[scene] = World(scene)
    return _WORLDS[scene]


def ridge_y(world_, idx, x01, base, amp):
    return base - amp * sum(a * math.sin(x01 * f * 6.28 + p) for p, a, f in world_.ridges[idx]) / 3


# ------------------------------------------------------------------ drawing pieces
def radial(cr, x, y, r, color, alpha):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, *color, alpha)
    g.add_color_stop_rgba(1, *color, 0)
    cr.set_source(g)
    cr.arc(x, y, r, 0, 6.2832)
    cr.fill()


def draw_sky(cr, w, h, top, mid, hz):
    g = cairo.LinearGradient(0, 0, 0, h * 0.7)
    g.add_color_stop_rgb(0, *top)
    g.add_color_stop_rgb(0.55, *mid)
    g.add_color_stop_rgb(1, *hz)
    cr.set_source(g)
    cr.rectangle(0, 0, w, h)
    cr.fill()


def draw_stars(cr, w, h, wd, t, amount):
    if amount <= 0.02:
        return
    for x, y, p, s in wd.stars:
        a = amount * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 1.3 + p)))
        cr.set_source_rgba(0.92, 0.95, 1.0, a)
        cr.arc(x * w, y * h, s * h / 700, 0, 6.2832)
        cr.fill()


def draw_sun_moon(cr, w, h, hour, horizon, hz, dl):
    sp = sun_position(hour, w, h, horizon)
    if sp and dl > 0.02:
        x, y, el = sp
        warm = mix(rgb("#FFB04A"), rgb("#FFF6D6"), el)
        radial(cr, x, y, h * (0.62 - 0.2 * el), warm, 0.55 * clamp(dl + 0.3))
        cr.set_source_rgb(*mix(warm, (1, 1, 0.92), 0.45))
        cr.arc(x, y, h * 0.052, 0, 6.2832)
        cr.fill()
    mp = moon_position(hour, w, h, horizon)
    if mp and dl < 0.6:
        x, y, el = mp
        radial(cr, x, y, h * 0.30, rgb("#BCD0FF"), 0.30 * (1 - dl))
        cr.set_source_rgba(0.93, 0.95, 1.0, 0.95 * (1 - dl))
        cr.arc(x, y, h * 0.036, 0, 6.2832)
        cr.fill()
        cr.set_source_rgba(*mix(rgb("#0C1A2A"), rgb("#183A5A"), 0.5), 0.55 * (1 - dl))   # soft crescent shadow
        cr.arc(x + h * 0.014, y - h * 0.006, h * 0.032, 0, 6.2832)
        cr.fill()


def draw_clouds(cr, w, h, wd, t, hz, dl, layers=(0, 1, 2), horizon=None):
    day = mix(rgb("#26344F"), rgb("#FFFFFF"), dl)
    tint = mix(day, hz, 0.38)
    alpha_base = 0.16 + 0.34 * dl
    for c in wd.clouds:
        if c["layer"] not in layers:
            continue
        margin = 360
        x = ((c["x"] * (w + 2 * margin) + c["speed"] * t * h / 540) % (w + 2 * margin)) - margin
        y = c["y"] * h
        a = alpha_base * (0.55 + 0.2 * c["layer"])
        for dx, dy, r in c["blobs"]:
            radial(cr, x + dx * h / 540, y + dy * h / 540, r * h / 540, tint, a)


def terrain_colors(hz, dl):
    ground = mix(rgb("#070C16"), rgb("#1F4A40"), dl)
    return ground


def fill_ridge(cr, w, h, wd, idx, base, amp, color, step=24):
    cr.move_to(0, h)
    x = 0
    while x <= w + step:
        cr.line_to(x, ridge_y(wd, idx, x / w, base, amp))
        x += step
    cr.line_to(w, h)
    cr.close_path()
    cr.set_source_rgb(*color)
    cr.fill()


def draw_fireflies(cr, w, h, wd, t, hour, count, gather=None):
    night = clamp(1 - daylight(hour) * 1.4)
    if night <= 0.05:
        return
    for i, (x0, y0, p1, p2) in enumerate(wd.flies[:count]):
        x = x0 * w + 34 * math.sin(t * 0.31 + p1) * h / 540
        y = y0 * h + 20 * math.sin(t * 0.43 + p2) * h / 540
        if gather:
            x = gather[0] + (x - gather[0]) * 0.55
        blink = 0.5 + 0.5 * math.sin(t * 1.7 + p2 * 3)
        radial(cr, x, y, 7 * h / 540, (1.0, 0.92, 0.45), 0.75 * night * blink)


def draw_lantern(cr, w, h, t):
    x, y = w * 0.10, h * 0.835
    flick = 0.9 + 0.07 * math.sin(t * 7.1) + 0.04 * math.sin(t * 12.9 + 1)
    radial(cr, x, y - h * 0.02, h * 0.34 * flick, rgb("#FF9A3C"), 0.55)
    radial(cr, x, y - h * 0.02, h * 0.12 * flick, rgb("#FFD27A"), 0.85)
    cr.set_source_rgb(0.10, 0.07, 0.05)                      # lantern body
    bw, bh = h * 0.028, h * 0.05
    cr.rectangle(x - bw / 2, y - bh, bw, bh)
    cr.fill()
    cr.set_source_rgba(1.0, 0.84, 0.45, 0.95)
    cr.rectangle(x - bw * 0.32, y - bh * 0.82, bw * 0.64, bh * 0.62)
    cr.fill()
    cr.set_source_rgb(0.10, 0.07, 0.05)
    cr.arc(x, y - bh - h * 0.006, bw * 0.38, math.pi, 0)     # carrying handle
    cr.set_line_width(max(1.0, h / 400))
    cr.stroke()


def draw_acacia(cr, x, y, s, color, t, phase):
    cr.save()
    cr.translate(x, y)
    cr.rotate(0.010 * math.sin(t * 0.7 + phase))
    cr.scale(s, s)
    cr.set_source_rgb(*color)
    cr.move_to(-6, 0)
    cr.curve_to(-4, -60, -10, -110, -34, -150)
    cr.line_to(-24, -154)
    cr.curve_to(-6, -126, 0, -108, 2, -92)
    cr.curve_to(10, -118, 26, -136, 46, -150)
    cr.line_to(54, -142)
    cr.curve_to(30, -122, 14, -98, 8, -60)
    cr.curve_to(8, -30, 10, -12, 12, 0)
    cr.close_path()
    cr.fill()
    for cx, cy, rx, ry in ((-6, -170, 120, 26), (-70, -152, 64, 18), (62, -156, 70, 19)):
        cr.save()
        cr.translate(cx, cy)
        cr.scale(rx, ry)
        cr.arc(0, 0, 1, 0, 6.2832)
        cr.restore()
        cr.fill()
    cr.restore()


def draw_tufts(cr, w, h, wd, t, base_y, color, count):
    cr.set_source_rgb(*color)
    cr.set_line_width(max(1.2, h / 420))
    for x01, yy, ht, p in wd.tufts[:count]:
        x, y = x01 * w, base_y + (yy - 0.9) * h * 0.4
        ht *= h / 540
        for k, lean in enumerate((-0.35, 0.0, 0.4)):
            sway = math.sin(t * 1.1 + p + k) * ht * 0.18
            cr.move_to(x + (k - 1) * 3, y)
            cr.curve_to(x + (k - 1) * 3 + lean * ht * 0.3, y - ht * 0.5, x + lean * ht * 0.5 + sway, y - ht * 0.8, x + lean * ht + sway * 1.5, y - ht)
            cr.stroke()


# ------------------------------------------------------------------ scenes
def scene_savanna(cr, w, h, wd, t, hour, hz, dl, gd, q):
    horizon = h * 0.64
    ground = terrain_colors(hz, dl)
    far = mix(hz, ground, 0.55)
    # far hills
    fill_ridge(cr, w, h, wd, 0, horizon - h * 0.02, h * 0.035, far)
    # the lake: sky colours mirrored, with sun / moon glitter
    lake_top, lake_bot = mix(hz, rgb("#2B5D86"), 0.35 * dl), mix(ground, rgb("#10304D"), 0.5)
    g = cairo.LinearGradient(0, horizon, 0, h * 0.84)
    g.add_color_stop_rgb(0, *lake_top)
    g.add_color_stop_rgb(1, *lake_bot)
    cr.set_source(g)
    cr.rectangle(0, horizon, w, h - horizon)
    cr.fill()
    draw_glitter(cr, w, h, t, hour, horizon, dl, rows=int(16 * q) + 4)
    # mid and near land
    fill_ridge(cr, w, h, wd, 1, h * 0.80, h * 0.022, mix(ground, hz, 0.12))
    near = mix(ground, rgb("#000000"), 0.35)
    fill_ridge(cr, w, h, wd, 2, h * 0.90, h * 0.016, near)
    draw_acacia(cr, w * 0.17, h * 0.89, h / 540 * 1.05, near, t, 0.0)
    draw_acacia(cr, w * 0.84, horizon - h * 0.025, h / 540 * 0.62, mix(far, near, 0.4), t, 1.7)
    draw_tufts(cr, w, h, wd, t, h * 0.93, near, int(70 * q))


def draw_glitter(cr, w, h, t, hour, horizon, dl, rows):
    sp = sun_position(hour, w, h, horizon) if dl > 0.05 else moon_position(hour, w, h, horizon)
    if not sp:
        return
    cx = sp[0]
    col = rgb("#FFE9B0") if dl > 0.05 else rgb("#CFE0FF")
    strength = 0.55 if dl > 0.05 else 0.35
    for i in range(rows):
        y = horizon + (i + 1) * (h * 0.20 / rows) * (1 + i * 0.06)
        spread = 12 + i * 11
        for k in range(5):
            x = cx + math.sin(t * 0.9 + i * 1.7 + k * 2.3) * spread
            a = strength * (0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * 2.2 + i * 3.1 + k))) * (1 - i / (rows * 1.15))
            cr.set_source_rgba(*col, a)
            ww = (6 + i * 1.6) * h / 540
            cr.rectangle(x - ww / 2, y, ww, max(1.2, h / 380))
            cr.fill()


def scene_highlands(cr, w, h, wd, t, hour, hz, dl, gd, q):
    horizon = h * 0.70
    ground = terrain_colors(hz, dl)
    tones = [0.30, 0.45, 0.62, 0.80]
    bases = [horizon - h * 0.10, horizon - h * 0.05, horizon + h * 0.01, horizon + h * 0.10]
    amps = [h * 0.10, h * 0.085, h * 0.07, h * 0.05]
    for i in range(4):
        fill_ridge(cr, w, h, wd, i, bases[i], amps[i], mix(hz, ground, tones[i]), step=18)
        # drifting mist between ridges
        for m in range(3):
            mx = ((m * 0.37 + i * 0.21) * (w + 600) + t * (7 + 3 * i) * h / 540) % (w + 600) - 300
            radial(cr, mx, bases[i] + h * 0.02 * i, h * (0.30 - 0.03 * i), mix(hz, rgb("#FFFFFF"), 0.55 * dl), 0.20 * (0.6 + 0.4 * dl))
    near = mix(ground, rgb("#000000"), 0.4)
    fill_ridge(cr, w, h, wd, 4, h * 0.93, h * 0.03, near)
    draw_tufts(cr, w, h, wd, t, h * 0.97, near, int(70 * q))


def scene_lakeshore(cr, w, h, wd, t, hour, hz, dl, gd, q):
    horizon = h * 0.56
    ground = terrain_colors(hz, dl)
    far = mix(hz, ground, 0.5)
    fill_ridge(cr, w, h, wd, 3, horizon - h * 0.012, h * 0.018, far)       # distant island
    water_top, water_bot = mix(hz, rgb("#2B5D86"), 0.30 * dl), mix(ground, rgb("#10304D"), 0.55)
    g = cairo.LinearGradient(0, horizon, 0, h)
    g.add_color_stop_rgb(0, *water_top)
    g.add_color_stop_rgb(1, *water_bot)
    cr.set_source(g)
    cr.rectangle(0, horizon, w, h - horizon)
    cr.fill()
    # ripples: wavy lines, spacing grows towards the viewer
    cr.set_line_width(max(1.0, h / 540))
    for i in range(int(26 * q) + 6):
        y = horizon + (h - horizon) * ((i + 1) / (26 * q + 6)) ** 1.6
        amp = 1.5 + i * 0.35
        phase = t * (0.35 + i * 0.03) + i * 1.9
        cr.set_source_rgba(*mix(hz, rgb("#FFFFFF"), 0.4), 0.10 + 0.05 * dl)
        cr.move_to(0, y)
        x = 0
        while x <= w:
            cr.line_to(x, y + amp * math.sin(x / (46 + i * 4) + phase))
            x += 22
        cr.stroke()
    draw_glitter(cr, w, h, t, hour, horizon, dl, rows=int(20 * q) + 4)
    near = mix(ground, rgb("#000000"), 0.45)
    # papyrus reeds, framing both sides
    cr.set_source_rgb(*near)
    cr.set_line_width(max(1.5, h / 300))
    for x01, ht, p in wd.reeds:
        side = x01 * 0.20 if x01 < 0.5 else 1 - (x01 - 0.5) * 0.40
        x, base = side * w, h * 1.0
        height = h * (0.20 + 0.34 * ht) * (1.0 if side < 0.5 else 0.8)
        sway = math.sin(t * 0.8 + p) * height * 0.04
        cr.move_to(x, base)
        cr.curve_to(x + sway * 0.3, base - height * 0.5, x + sway, base - height * 0.85, x + sway * 1.6 + (6 if side > 0.5 else -6), base - height)
        cr.stroke()
        cr.arc(x + sway * 1.6 + (6 if side > 0.5 else -6), base - height, h * 0.012, 0, 6.2832)
        cr.fill()


SCENE_FUNCS = {"Savanna": scene_savanna, "Highlands": scene_highlands, "Lakeshore": scene_lakeshore}


# ------------------------------------------------------------------ the one entry point
def render(cr, w, h, t=0.0, hour=12.0, scene="Savanna", grid_down=False, quality=1.0):
    """Draw one frame. t = seconds (animation), hour = local time as a decimal (17.5 = 5:30 pm)."""
    scene = scene if scene in SCENE_FUNCS else "Savanna"
    wd = world(scene)
    eff = LANTERN_HOUR if grid_down and daylight(hour) > 0.25 else hour      # Grid Down: evening falls
    top, mid, hz = sky_colors(eff)
    dl = daylight(eff)
    draw_sky(cr, w, h, top, mid, hz)
    draw_stars(cr, w, h, wd, t, clamp(1 - dl * 1.7))
    horizon = h * {"Savanna": 0.64, "Highlands": 0.70, "Lakeshore": 0.56}[scene]
    draw_sun_moon(cr, w, h, eff, horizon, hz, dl)
    draw_clouds(cr, w, h, wd, t, hz, dl)
    SCENE_FUNCS[scene](cr, w, h, wd, t, eff, hz, dl, grid_down, quality)
    draw_fireflies(cr, w, h, wd, t, eff, 40 if grid_down else int(16 * quality + 4), gather=(w * 0.10, 0) if grid_down else None)
    if grid_down:
        draw_lantern(cr, w, h, t)
    g = cairo.RadialGradient(w / 2, h / 2, h * 0.45, w / 2, h / 2, h * 1.05)     # soft vignette
    g.add_color_stop_rgba(0, 0, 0, 0, 0)
    g.add_color_stop_rgba(1, 0, 0, 0, 0.30)
    cr.set_source(g)
    cr.rectangle(0, 0, w, h)
    cr.fill()


def render_png(path, w=1280, h=720, scene="Savanna", hour=12.0, t=0.0, grid_down=False, quality=1.0):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    cr = cairo.Context(surf)
    render(cr, w, h, t, hour, scene, grid_down, quality)
    surf.write_to_png(str(path))
    return path


def png_bytes(w, h, scene, hour, t=0.0, grid_down=False):
    import io
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    render(cairo.Context(surf), w, h, t, hour, scene, grid_down, 0.6)
    buf = io.BytesIO()
    surf.write_to_png(buf)
    return buf.getvalue()


def hour_now() -> float:
    import time
    lt = time.localtime()
    return lt.tm_hour + lt.tm_min / 60 + lt.tm_sec / 3600


# ------------------------------------------------------------------ adaptive quality (pure, testable)
RESOLUTIONS = [(960, 540), (640, 360), (480, 270)]
MAX_FPS, MIN_FPS = 20, 6
CPU_BUDGET = 0.35          # never ask for more than ~35% of one core


def plan(frame_ms: float, level: int):
    """Given how long the last frame took and the current resolution level (0 best), decide what to do next.
    Returns (level, fps). fps == 0 means: stop animating and fall back to one still frame per minute."""
    if frame_ms <= 0:
        return level, MAX_FPS
    fps = min(MAX_FPS, int(1000 * CPU_BUDGET / frame_ms))
    if fps >= 12:
        return level, fps
    if level < len(RESOLUTIONS) - 1:          # try a smaller picture before giving up animation
        return level + 1, MAX_FPS
    if fps < MIN_FPS:
        return level, 0
    return level, fps
