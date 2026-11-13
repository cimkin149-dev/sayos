"""SayMy theme: the shared stylesheet for every SayMy window, light or dark, with no GTK needed (so it can be tested anywhere)."""
import saymy_settings_backend as be

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
