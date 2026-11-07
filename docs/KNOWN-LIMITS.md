# Known limits of Stage 1 (read before building)

Written plainly so nothing surprises you.

## What was verified
- The Say Bar logic, calculator safety, power-cut state machine, data ledger and sky phases pass 25
  automated tests in a simulated environment.
- Shell scripts pass syntax checks and shellcheck; JSON catalogs are valid; all art renders.

## What was NOT verified (no ISO has been booted yet)
- **The ISO build itself.** The live-build configuration targets Debian 13's live-build and was written
  from its documented layout, but the build tool was not available where this was written. The first
  real build may stop on an option name or a package name. That is normal for a first build. Paste the
  last 30 lines of `build.log` and it gets fixed in one round.
- **Booting on real hardware**: Wi-Fi, graphics, touchpads, suspend and hibernate vary by machine.
- **The Say Bar prompt window** uses fuzzel's `--prompt-only` option; confirm it opens and returns text.
- **Waybar icons and panel look**: written without a screenshot; expect to tweak spacing.
- **BIOS (syslinux) boot menu colours** use the stock theme with our splash image; the UEFI (GRUB) menu is fully themed.
- **The login screen** (SDDM) uses Debian's default theme with SayMy fonts; a custom login screen is Stage 2.
- **Installer**: Calamares uses Debian's tested module settings with SayMy branding on top. Install to a
  VM disk first, never to a machine with data you care about, until you have done it successfully once.

## Deliberately not in Stage 1
- Voice input (Say Bar is typed for now). Luganda commands and translations need a native speaker.
- Per-app data accounting (v0.1 counts total traffic per day).
- Mobile money, SayMy Share, Modes, Packs, the SayMy Store, local AI companion. See ROADMAP.md.
- Full-session restore after a sudden power loss. v0.1 saves files and state through the apps'
  `save-now` signal and hibernates when swap exists; true instant-resume needs more engineering.

## Translations marked as drafts
`i18n/sw.json` and `say/intents/sw.json` are a first draft for review by a native Kiswahili speaker.
`i18n/lg.json` (Luganda) is intentionally empty so English shows until a native speaker fills it in.
