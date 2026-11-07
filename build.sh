#!/bin/bash
# Build the SayMy OS ISO.
#
#   ./build.sh              build natively (needs root on Debian 13 or a Debian 13 container)
#   ./build-docker.sh       build inside a Debian 13 container (works on Ubuntu, Windows+Docker, macOS+Docker)
#
# Result: out/saymy-os-*.iso
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
    echo "Run as root:  sudo ./build.sh" >&2
    exit 1
fi

. /etc/os-release
if [ "${ID:-}" != "debian" ] || [ "${VERSION_ID:-}" != "13" ]; then
    echo "This host is ${PRETTY_NAME:-unknown}. SayMy OS builds on Debian 13 (trixie)." >&2
    echo "Use ./build-docker.sh instead; it provides a Debian 13 build environment." >&2
    exit 1
fi

echo "==> Installing build tools"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    live-build debootstrap xorriso squashfs-tools mtools dosfstools cpio gnupg ca-certificates \
    isolinux syslinux syslinux-common syslinux-utils grub-pc-bin grub-efi-amd64-bin

echo "==> Preparing bootloader templates"
# live-build uses config/bootloaders wholesale once it exists, so start from the stock
# templates and keep our own files (theme, splash) on top.
if [ -d /usr/share/live/build/bootloaders ]; then
    mkdir -p config/bootloaders
    cp -rn /usr/share/live/build/bootloaders/. config/bootloaders/
    find config/bootloaders -name 'splash.svg' -delete
fi

echo "==> Making sure scripts are executable"
chmod +x auto/* config/hooks/live/* config/includes.chroot/usr/bin/saymy-* config/includes.chroot/lib/live/config/9990-saymy

echo "==> Cleaning previous build"
lb clean --purge >/dev/null 2>&1 || true

echo "==> Configuring"
lb config

echo "==> Building (this downloads about 1.5 GB and takes 20 to 60 minutes)"
lb build

mkdir -p out
for f in *.iso; do
    [ -e "$f" ] && mv "$f" out/
done
ls -lh out/
echo "==> Done. Test it with:  ./run-vm.sh"
