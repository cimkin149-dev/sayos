# Safe Updates: design

**Promise:** an update must never leave someone with a computer that no longer works, and every update can be undone with one tap.
This matters most where internet is slow, power is unreliable, and nobody is available to repair a broken machine.

## Layers

| Layer | What protects the user | Status |
|---|---|---|
| 1. Guards before starting | Refuse to start on battery below 50%, with under 2 GB free, or after a half-finished install (`dpkg --audit`, `apt-get check`) | **v0.1, tested** |
| 2. Keep the old versions | Rebuild a .deb of every package about to change (`dpkg-repack`, keeps edited settings), checksummed, in `/var/lib/saymy/updates` | **v0.1, tested** |
| 3. Health check | Compare failed services before and after; only NEW failures are blamed on the update | **v0.1, tested** |
| 4. Undo | Reinstall kept versions, hold them so they are not upgraded again until the next deliberate update. Last 3 updates stay undoable | **v0.1, tested** |
| 5. Old kernel stays | Debian keeps the previous kernel; it appears under Advanced options in the boot menu | Debian default, unverified on SayMy |
| 6. Offline bundles | The same flow applied to a checksum-verified USB bundle | **v0.1, tested** |
| 7. Whole-system snapshots | Btrfs subvolumes + boot-from-snapshot, so even settings, data and non-package changes roll back | Roadmap (1.0) |
| 8. Staged rollout | New updates reach a few computers first; automatic pause if they report failures | Roadmap |

## What Undo does and does not cover
- It restores **package versions** (programs and system files that packages own), including your edited settings in them.
- It does **not** undo changes to your own documents, nor changes made by programs outside the package system.
- It cannot undo an update whose kept copy is missing or damaged. It checks first and refuses rather than half-restore.
- The kept copies are rebuilt from the installed files, not downloaded from Debian, so they are local-only and unsigned.
  They never leave the computer.

## Why not snapshots first?
Whole-system snapshots (Btrfs) are the better long-term answer, but they require the installer to partition with Btrfs subvolumes and the boot
loader to boot snapshots. Those installer changes must be tested on real machines, and the default install must stay one that is known to
work. The package-level layer works on any install today and also covers the most common failure: a bad package version.

## Files
- `usr/lib/saymy/saymy_safeupdate.py` engine, `usr/lib/saymy/saymy-update-helper` root helper, Settings → Updates window.
- Tests: `tests/test_saymy.py` class `SafeUpdates` (fake system: blocked start, kept versions, failures after update, undo, damaged copy, pruning).
