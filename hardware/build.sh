#!/usr/bin/env bash
# Build the KiCad project and production files inside the official KiCad 9 image.
# Usage: ./build.sh [sch|pcb|fab|all]
set -euo pipefail
cd "$(dirname "$0")"
MODELS=(); [ -d .3dmodels ] && MODELS=(-v "$PWD/.3dmodels:/usr/share/kicad/3dmodels:ro")
docker run --rm --platform linux/amd64 -v "$PWD/..:/repo" ${MODELS[@]+"${MODELS[@]}"} -w /repo/hardware/generator \
  -e PYTHONDONTWRITEBYTECODE=1 -e HOME=/tmp -e NOROUTE="${NOROUTE:-}" kicad/kicad:9.0 bash -c 'mkdir -p /tmp/.config/kicad/9.0 && cp /usr/share/kicad/template/*-lib-table /tmp/.config/kicad/9.0/ && python3 build.py "$0"' "${1:-all}"
