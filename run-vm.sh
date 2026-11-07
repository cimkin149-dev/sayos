#!/bin/sh
# Try the ISO in QEMU.   ./run-vm.sh [file.iso] [--uefi]
ISO=""; UEFI=""
for a in "$@"; do
    case "$a" in
        --uefi) UEFI=1 ;;
        *) ISO="$a" ;;
    esac
done
[ -n "$ISO" ] || ISO="$(ls out/*.iso 2>/dev/null | head -1)"
[ -n "$ISO" ] || { echo "No ISO found. Build one first (./build-docker.sh)." >&2; exit 1; }

ACCEL=""
[ -e /dev/kvm ] && ACCEL="-enable-kvm -cpu host"
BIOS=""
if [ -n "$UEFI" ]; then
    for f in /usr/share/ovmf/OVMF.fd /usr/share/OVMF/OVMF_CODE.fd; do
        [ -f "$f" ] && BIOS="-bios $f" && break
    done
fi

# shellcheck disable=SC2086
exec qemu-system-x86_64 -m 4096 -smp 2 $ACCEL $BIOS \
    -cdrom "$ISO" -boot d \
    -device virtio-vga -display gtk \
    -device intel-hda -device hda-duplex \
    -nic user,model=virtio-net-pci
