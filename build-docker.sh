#!/bin/sh
# Build the ISO inside a Debian 13 container. Needs Docker. Works from Ubuntu, Windows (Docker Desktop), macOS.
set -e
cd "$(dirname "$0")"
mkdir -p out
docker run --rm --privileged \
    -v "$(pwd)":/src \
    -v "$(pwd)/out":/out \
    debian:trixie \
    bash /src/scripts/docker-entry.sh
ls -lh out/
