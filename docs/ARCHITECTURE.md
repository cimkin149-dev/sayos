# Architecture (Stage 1)

```
        SayMy OS (Debian 13 "trixie" base)
 ┌──────────────────────────────────────────────┐
 │ SayMy tools   saymy-say  saymy-power         │  Python, JSON catalogs, no heavy deps
 │               saymy-data saymy-sky           │
 ├──────────────────────────────────────────────┤
 │ SayMy Shell   labwc (compositor) + waybar    │  our config, theme, panel, launcher
 │ (Stage 1)     fuzzel + mako + foot + swaylock│
 ├──────────────────────────────────────────────┤
 │ Session       sddm → labwc (Wayland)         │
 ├──────────────────────────────────────────────┤
 │ System        systemd, NetworkManager,       │  unchanged Debian: all hardware
 │               PipeWire, Linux kernel         │  drivers keep working
 └──────────────────────────────────────────────┘
```

**Why this shape:** the kernel and drivers stay Debian's, so hardware works. Everything users see and
touch is ours and lives in `config/includes.chroot`, which is copied into the image. Replacing labwc with
our own compositor later changes one layer and nothing below it.

## Say Bar
`saymy_say.py` is pure logic: `handle(text)` returns a `Result` (a command to run and/or a message).
Intents are JSON per language; adding a language means adding two JSON files. Matching tries the user's
language first, then all others, so mixed-language use works. The calculator parses with Python's `ast`
and allows only numbers and arithmetic; anything else is rejected (tested).

## Power-cut guard
`events_for(previous, current, flags)` is a pure function that turns two power snapshots into events
(`power_cut`, `power_back`, `low`, `critical`, `hibernate`). `apply()` performs actions. Runs as a
systemd user service so notifications reach the desktop.

## Data wallet
Reads `/sys/class/net/*/statistics`, ignores virtual interfaces, tolerates reboots, keeps a daily
ledger in `~/.local/share/saymy/data.json`. Cost is shown only after the user sets a price.

## Build
`auto/config` → `lb config`; package list in `config/package-lists`; files in `config/includes.chroot`;
hooks in `config/hooks/live`. `build.sh` prepares bootloader templates then runs `lb build`.

## Live session vs installed system
`lib/live/config/9990-saymy` runs only when booting the live image: it enables auto-login and
passwordless sudo for the live user. An installed system never gets either.
