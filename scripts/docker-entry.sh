#!/bin/bash
# Runs inside the Debian 13 container. Builds on the container's own disk (not the bind mount),
# because debootstrap needs real Linux permissions and device nodes.
set -euo pipefail
apt-get update
apt-get install -y --no-install-recommends rsync
mkdir -p /build /out
# Always hand the build log back, even when the build fails.
trap 'cp -v /build/build.log /out/ 2>/dev/null || true' EXIT
rsync -a --exclude out --exclude chroot --exclude .build --exclude cache /src/ /build/
cd /build
./build.sh
cp -v out/*.iso /out/
