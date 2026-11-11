#!/bin/bash
# Everything that can be checked without booting an ISO.
set -u
cd "$(dirname "$0")/.."
fail=0

echo "== shell syntax"
for f in build.sh build-docker.sh run-vm.sh scripts/*.sh auto/* config/hooks/live/* \
         config/includes.chroot/usr/bin/saymy-sky config/includes.chroot/usr/bin/saymy-lock \
         config/includes.chroot/usr/bin/saymy-screenshot config/includes.chroot/usr/bin/saymy-install \
         config/includes.chroot/usr/bin/saymy-session-save config/includes.chroot/lib/live/config/9990-saymy \
         config/includes.chroot/etc/skel/.config/labwc/autostart; do
    sh -n "$f" 2>/dev/null || bash -n "$f" || { echo "FAIL syntax: $f"; fail=1; }
done

if command -v shellcheck >/dev/null; then
    echo "== shellcheck"
    shellcheck -S warning build.sh build-docker.sh run-vm.sh scripts/*.sh auto/* \
        config/includes.chroot/usr/bin/saymy-sky config/includes.chroot/usr/bin/saymy-lock \
        config/includes.chroot/usr/bin/saymy-screenshot config/includes.chroot/usr/bin/saymy-install \
        config/includes.chroot/usr/bin/saymy-session-save || fail=1
fi

echo "== json"
for f in design/tokens/tokens.json config/includes.chroot/usr/share/saymy/i18n/*.json \
         config/includes.chroot/usr/share/saymy/say/intents/*.json; do
    python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$f" || { echo "FAIL json: $f"; fail=1; }
done

echo "== python"
python3 -m py_compile config/includes.chroot/usr/lib/saymy/*.py config/includes.chroot/usr/bin/saymy-language config/includes.chroot/usr/bin/saymy-settings config/includes.chroot/usr/bin/saymy-accent config/includes.chroot/usr/bin/saymy-welcome config/includes.chroot/usr/bin/saymy-space config/includes.chroot/usr/bin/saymy-doctor config/includes.chroot/usr/bin/saymy-night config/includes.chroot/usr/bin/saymy-idle config/includes.chroot/usr/bin/saymy-drop config/includes.chroot/usr/bin/saymy-look config/includes.chroot/usr/bin/saymy-sound config/includes.chroot/usr/bin/saymy-live config/includes.chroot/usr/bin/saymy-wallpaper config/includes.chroot/usr/bin/saymy-askpass config/includes.chroot/usr/lib/saymy/saymy-user-helper config/includes.chroot/usr/lib/saymy/saymy-update-helper || fail=1
python3 tests/test_saymy.py || fail=1

echo "== required files"
for f in auto/config config/package-lists/saymy.list.chroot \
         config/includes.chroot/usr/share/plymouth/themes/saymy/saymy.plymouth \
         config/includes.chroot/usr/share/calamares/branding/saymy/branding.desc \
         config/bootloaders/grub-pc/live-theme/theme.txt; do
    [ -f "$f" ] || { echo "MISSING: $f"; fail=1; }
done

[ "$fail" -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit "$fail"
