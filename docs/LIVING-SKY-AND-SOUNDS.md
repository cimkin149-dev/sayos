# Living Sky wallpapers and SayMy sound packs

## Why the wallpaper is code, not video
Other systems animate wallpapers by playing a looping video. That decodes video all day, uses the GPU, and drains the battery,
which is the wrong trade for places with power cuts and older hardware. Living Sky is **drawn by code in real time**:

| | Video wallpaper | Living Sky |
|---|---|---|
| Size on disk | tens of MB per scene | none (code only) |
| Follows the real clock | no, it loops | **yes**: sun, moon, sky colour, stars, fireflies |
| Reacts to the computer | no | **yes**: Grid Down lights a lantern |
| Battery | constant decoding | pauses on battery |
| Resolution | fixed | any screen |

## What it draws
Sun and moon travel along the real clock; sky colours move continuously through 24 hours (no jumps, tested); clouds drift in three
layers; grass and reeds sway; water ripples and glitters towards the sun or moon; stars twinkle; fireflies appear after dusk.
Three scenes: **Savanna** (acacias and a lake), **Highlands** (layered ridges and drifting mist), **Lakeshore** (open water and papyrus).
When mains power drops (**Grid Down**), evening falls whatever the hour, and a lantern is lit with the fireflies gathering round it.

## How it stays cheap
- Frames are drawn at a lower resolution and scaled up (960x540, then 640x360, then 480x270).
- `plan()` measures how long each frame takes and limits the work to about 35% of one core: slower machines get a smaller picture and a
  lower frame rate, and a machine that is too slow falls back to one still frame per minute.
- **Automatic** animation pauses on battery and shows one fresh frame every 30 seconds. "Always" and "Never" are one tap away.
- Without Wayland layer-shell support SayMy shows a fresh still frame every minute through `swaybg`, so the sky still follows the clock.
  The layer-shell libraries are installed by an optional build step; if the Debian mirror lacks them the build still succeeds.

## Making scenes
Scenes are Python functions in `usr/lib/saymy/saymy_live.py` (and the same logic in the browser preview). A Look can only *name* a scene,
never supply code or a file path. Letting the community add scenes safely needs a data-only scene format; that is on the roadmap.

## Sound packs
All sounds are synthesized from scratch by `design/generate_sounds.py`, so there are no samples and no licensing issues.
- **Savanna**: kalimba-style tines and plucked adungu-style strings on a pentatonic scale.
- **Quiet**: soft sine bells, lower volume. **Classic**: plain beeps. **Off**.
Events: login, logout, notification, critical, power cut, power back, battery low, file received, update done, error, tick.
Rules: sounds are silent in the **Study** space (notifications on Do Not Disturb) **except safety alerts** (power cut, critical battery,
battery low). The player never crashes if no audio tool is installed.
Verification so far is by analysis (pitch of every note measured, peak levels, click-free starts and ends), **not by ear**. Please listen
and tell us what feels wrong.
