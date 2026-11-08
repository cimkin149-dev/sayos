# SayMy OS

**Born in Africa. Built for the world.**

SayMy OS is a Debian-based operating system with its own desktop, built for the conditions most of the
world actually computes in: power cuts, expensive data, older hardware, shared machines, and more than
one language in a single sentence.

This is **Stage 1 (version 0.1, "Dawn")**: a branded, bootable, installable image, plus the first
SayMy-specific tools. Read [docs/KNOWN-LIMITS.md](docs/KNOWN-LIMITS.md) before you build; it says plainly
what has and has not been tested.

## What is in Stage 1

| Piece | What it does |
|---|---|
| **Branded ISO** | Debian 13 live image, BIOS and UEFI, with SayMy boot menu, boot splash, login, wallpapers and sounds-free first release |
| **Say Bar** (`Super+Space`) | Type a command in English or Kiswahili: *open firefox, search cats, calculate 12*8, battery, lock, volume up, shut down*. Luganda slot is ready for a native speaker |
| **SayMy Sky** | The wallpaper follows the sky: sunrise, day, dusk, night |
| **Power-cut guard** | Detects mains loss, switches to power saver, dims the screen, warns, saves, suspends or hibernates at low battery, and keeps a diary of every cut |
| **Data wallet** | Panel counter of data used today; shows cost once you set your price (`saymy-data set-price 5000 UGX`). No currency is assumed |
| **SayMy Settings** (`Super+,`) | A real GTK app: Wi-Fi, brightness, volume, power mode, Power Diary, accent colour that recolours the whole desktop (and can follow the sky), language, data price, About |
| **Installer** | Calamares with SayMy branding and slideshow |
| **Language groundwork** | Translation catalogs, 10 locales generated, Noto fonts for wide script coverage, community-friendly JSON files |
| **Design system** | Tokens, logo, bark-cloth pattern, four wallpapers, all regenerated from code (`design/generate_assets.py`) |

## Build it

You need a machine with **about 20 GB free disk**, a stable internet connection (about 1.5 GB download),
and one of:

**A. Docker (Windows, macOS, Linux)**
```
./build-docker.sh
```
On Windows PowerShell:
```
docker run --rm --privileged -v ${PWD}:/src -v ${PWD}/out:/out debian:trixie bash /src/scripts/docker-entry.sh
```

**B. GitHub builds it for you (no machine needed)**
See [docs/BUILD-WITH-GITHUB.md](docs/BUILD-WITH-GITHUB.md). Push the project to GitHub, press *Run workflow*, download the ISO.

**C. A Debian 13 machine or VM**
```
sudo ./build.sh
```

The ISO appears in `out/`. Expect 20 to 60 minutes the first time.

## Try it

Fastest: `./run-vm.sh` (needs `qemu-system-x86_64`), or `./run-vm.sh --uefi`.
VirtualBox: Linux / Debian 64-bit, 4 GB RAM, 2 CPUs, 32 MB+ video memory, boot from the ISO.
The live session logs in by itself. Press **Super+Space** for the Say Bar. Double-click
**Install SayMy OS** from the Apps menu (`Super+A`) to install.

## Check the project without building

```
bash tests/run-all.sh
```
Runs 25 automated tests (Say Bar matching, calculator safety, power-cut logic, data ledger, sky phases)
plus shell, JSON and Python checks. No root, no ISO, no hardware needed.

## Keys

| Keys | Action |
|---|---|
| Super + Space (or Alt + Space) | Say Bar |
| Super + A | App launcher |
| Super + Enter | Terminal |
| Super + E / B | Files / Browser |
| Super + L | Lock |
| Print | Screenshot to clipboard and `~/Pictures/Screenshots` |

## Project map

```
auto/                  live-build entry points
config/package-lists/  what is installed
config/hooks/live/     branding, services, boot splash
config/includes.chroot/  files copied into the OS (desktop config, tools, themes, art)
config/bootloaders/    boot menu theme
design/                tokens, logo, pattern, wallpapers, generate_assets.py
docs/                  architecture, brand, translating, roadmap, known limits
tests/                 automated checks
```

## Licence note

Debian packages keep their own licences. Choose a licence for the SayMy-specific code and art in this
repository (MIT or GPL-3.0 are both common for a distribution) before publishing.
