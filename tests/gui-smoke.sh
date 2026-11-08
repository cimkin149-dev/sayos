#!/bin/bash
# Opens every Settings panel on a virtual screen and saves screenshots to /tmp/saymy-shots.
# Needs: python3-gi gir1.2-gtk-4.0 xvfb imagemagick. Not part of run-all.sh because it needs a display stack.
set -u
cd "$(dirname "$0")/.."
export SAYMY_LIB="$PWD/config/includes.chroot/usr/lib/saymy" SAYMY_SHARE="$PWD/config/includes.chroot/usr/share/saymy"
export GDK_BACKEND=x11 GSK_RENDERER=cairo HOME="$(mktemp -d)"
mkdir -p /tmp/saymy-shots; fail=0
for p in Network Display Sound Power Appearance Language "Data & Money" About; do
  log="$(mktemp)"
  xvfb-run -a -s "-screen 0 1000x640x24" bash -c "SAYMY_START_PANEL='$p' python3 config/includes.chroot/usr/bin/saymy-settings --demo >'$log' 2>&1 & pid=\$!; sleep 4; kill -0 \$pid && import -window root '/tmp/saymy-shots/${p// /_}.png'; kill \$pid" || fail=1
  grep -q Traceback "$log" && { echo "FAIL panel $p"; cat "$log"; fail=1; }
done
for n in 0 1 2 3 4; do
  log="$(mktemp)"
  xvfb-run -a -s "-screen 0 1000x640x24" bash -c "SAYMY_START_PAGE=$n python3 config/includes.chroot/usr/bin/saymy-welcome --demo >'$log' 2>&1 & pid=\$!; sleep 4; kill -0 \$pid && import -window root /tmp/saymy-shots/welcome$n.png; kill \$pid" || fail=1
  grep -q Traceback "$log" && { echo "FAIL welcome page $n"; cat "$log"; fail=1; }
done
log="$(mktemp)"
xvfb-run -a -s "-screen 0 1000x700x24" bash -c "python3 config/includes.chroot/usr/bin/saymy-doctor --demo >'$log' 2>&1 & pid=\$!; sleep 4; kill -0 \$pid && import -window root /tmp/saymy-shots/doctor.png; kill \$pid" || fail=1
grep -q Traceback "$log" && { echo "FAIL doctor"; cat "$log"; fail=1; }
for pg in Send Receive; do
  log="$(mktemp)"
  xvfb-run -a -s "-screen 0 1000x700x24" bash -c "SAYMY_START_PAGE=$pg SAYMY_DEMO_ON=1 python3 config/includes.chroot/usr/bin/saymy-drop --demo >'$log' 2>&1 & pid=\$!; sleep 4; kill -0 \$pid && import -window root /tmp/saymy-shots/drop_$pg.png; kill \$pid" || fail=1
  grep -q Traceback "$log" && { echo "FAIL drop $pg"; cat "$log"; fail=1; }
done
[ "$fail" -eq 0 ] && echo "GUI SMOKE OK: screenshots in /tmp/saymy-shots" || echo "GUI SMOKE FAILED"
exit "$fail"
