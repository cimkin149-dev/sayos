"""Shared SayMy GTK4 look and helpers (used by Settings and the Welcome app)."""
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402


from saymy_theme import CSS, css_for  # noqa: E402,F401  (kept here so every window imports from one place)


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


