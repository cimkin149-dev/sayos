#!/bin/bash
# Runs inside the Debian 13 container. Builds on the container's own disk (not the bind mount),
# because debootstrap needs real Linux permissions and device nodes.
set -euo pipefail
apt-get update
apt-get install -y --no-install-recommends rsync
mkdir -p /build /out
# Always hand the build log back, even when the build fails.
report() {
    code=$?
    cp -v /build/build.log /out/ 2>/dev/null || true
    if [ "$code" -ne 0 ] && [ -f /build/build.log ]; then
        tail -n 40 /build/build.log | sed 's/%/%25/g; s/\r//g' | awk 'BEGIN{ORS=""} {print $0 "%0A"}' > /tmp/annotation.txt
        echo "::error title=SayMy ISO build failed (last 40 log lines)::$(cat /tmp/annotation.txt)"
    fi
}
trap report EXIT
rsync -a --exclude out --exclude chroot --exclude .build --exclude cache /src/ /build/
cd /build
./build.sh
cp -v out/*.iso /out/
