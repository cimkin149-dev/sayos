"""Shared SayMy GTK4 look and helpers (used by Settings and the Welcome app)."""
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

import saymy_settings_backend as be  # noqa: E402

CSS = """
window { background: #0C1A2A; color: #F3E9D8; font-family: Inter, "Noto Sans", sans-serif; }
.side { background: #14283C; padding: 12px 0; }
.side list { background: transparent; }
.side row { background: transparent; color: #F3E9D8; }
.side row { padding: 11px 18px; border-radius: 12px; margin: 2px 10px; }
.side row:hover { background: #1E3A55; }
.side row:selected { background: @ACC@; color: #0C1A2A; font-weight: 700; }
.brand { font-weight: 800; font-size: 18px; padding: 8px 22px 14px 22px; }
.title { font-size: 28px; font-weight: 700; margin-bottom: 14px; }
.row { padding: 14px 16px; background: #14283C; border-radius: 14px 14px 14px 4px; margin-bottom: 10px; }
.rt { font-weight: 600; }
.dim { color: #9FB3C8; font-size: 13px; }
.good { color: #3FA66B; } .bad { color: #E0445B; }
button { background: #1E3A55; color: #F3E9D8; border-radius: 999px; padding: 6px 18px; border: none; box-shadow: none; }
button:hover { background: #27496B; }
button.accent, button.toggle:checked { background: @ACC@; color: #0C1A2A; font-weight: 700; }
switch { background: #1E3A55; border-radius: 999px; border: none; }
switch:checked { background: @ACC@; }
switch slider { background: #F3E9D8; border-radius: 999px; }
scale trough { background: #1E3A55; min-height: 8px; border-radius: 999px; }
scale highlight { background: @ACC@; border-radius: 999px; }
scale slider { background: #F3E9D8; min-width: 22px; min-height: 22px; border-radius: 999px; }
entry, passwordentry { background: #0C1A2A; color: #F3E9D8; border-radius: 12px; border: 1px solid #1E3A55; padding: 6px 12px; }
.big { font-size: 36px; font-weight: 800; }
.card-btn { padding: 14px 20px; border-radius: 16px 16px 16px 4px; }
.lv-ok { color: #3FA66B; font-weight: 800; font-size: 20px; } .lv-warn { color: #F5B93A; font-weight: 800; font-size: 20px; } .lv-bad { color: #E0445B; font-weight: 800; font-size: 20px; }
.devices { background: #14283C; border-radius: 14px; }
.devices row { padding: 4px 6px; color: #F3E9D8; background: transparent; border-radius: 10px; }
.devices row:selected { background: @ACC@; color: #0C1A2A; }
progressbar trough { background: #1E3A55; min-height: 8px; border-radius: 999px; }
progressbar progress { background: @ACC@; min-height: 8px; border-radius: 999px; }
.swatch { min-width: 40px; min-height: 40px; padding: 0; border-radius: 999px; border: 3px solid transparent; }
.swatch.sel { border-color: #F3E9D8; }
"""


def css_for(accent, mode=None):
    import saymy_looks as looks
    mode = mode or be.load_appearance().get("mode", "dark")
    extra = "".join(f".sw-{n} {{ background: {h}; }}\n" for n, h in be.ACCENTS.items())
    return looks.swap_palette(CSS.replace("@ACC@", accent), "dark", mode) + extra


def bg(fn, done):
    """Run fn off the main thread so the window never freezes; then call done(result) on it."""
    def worker():
        result = fn()
        GLib.idle_add(done, result)
    threading.Thread(target=worker, daemon=True).start()


def debounced(fn, ms=180):
    state = {"id": 0}

    def call(*args):
        if state["id"]:
            GLib.source_remove(state["id"])

        def fire():
            state["id"] = 0
            fn(*args)
            return False
        state["id"] = GLib.timeout_add(ms, fire)
    return call


def label(text, css=None, xalign=0.0, wrap=False):
    w = Gtk.Label(label=text, xalign=xalign, wrap=wrap)
    if css:
        w.add_css_class(css)
    return w


def row(title, sub=None, widget=None):
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
    box.add_css_class("row")
    txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    txt.set_hexpand(True)
    txt.append(label(title, "rt"))
    if sub:
        txt.append(label(sub, "dim", wrap=True))
    box.append(txt)
    if widget is not None:
        widget.set_valign(Gtk.Align.CENTER)
        box.append(widget)
    return box


def switch(active, on_change):
    sw = Gtk.Switch()
    sw.set_active(active)
    sw.connect("state-set", lambda s, state: (on_change(state), False)[1])
    return sw


def scale(value, on_change):
    sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
    sc.set_value(value)
    sc.set_size_request(280, -1)
    sc.set_draw_value(False)
    cb = debounced(on_change)
    sc.connect("value-changed", lambda s: cb(int(s.get_value())))
    return sc


def page(title):
    outer = Gtk.ScrolledWindow()
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for side in ("start", "end"):
        getattr(box, f"set_margin_{side}")(36)
    box.set_margin_top(28)
    box.set_margin_bottom(28)
    box.append(label(title, "title"))
    outer.set_child(box)
    return outer, box


