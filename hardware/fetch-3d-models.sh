#!/usr/bin/env bash
# Download the KiCad 3D models this board uses (only needed for renders and the STEP export).
# The models come from the official KiCad library: https://gitlab.com/kicad/libraries/kicad-packages3D
# (the library has no models for the TS-1187A button and the HRO USB-C socket, so those two are missing)
set -euo pipefail
cd "$(dirname "$0")"
BASE="https://gitlab.com/kicad/libraries/kicad-packages3D/-/raw/9.0.9"
MODELS=(
  "Capacitor_SMD.3dshapes/C_0603_1608Metric.step"
  "Capacitor_SMD.3dshapes/C_0805_2012Metric.step"
  "Connector_Phoenix_MC.3dshapes/PhoenixContact_MC_1,5_4-G-3.5_1x04_P3.50mm_Horizontal.step"
  "Connector_PinHeader_2.54mm.3dshapes/PinHeader_1x06_P2.54mm_Vertical.step"
  "Diode_SMD.3dshapes/D_SMA.step"
  "Diode_SMD.3dshapes/D_SOD-123.step"
  "Fuse.3dshapes/Fuse_1206_3216Metric.step"
  "Inductor_SMD.3dshapes/L_0805_2012Metric.step"
  "Inductor_SMD.3dshapes/L_Changjiang_FNR4030S.step"
  "LED_SMD.3dshapes/LED_0603_1608Metric.step"
  "LED_SMD.3dshapes/LED_0805_2012Metric.step"
  "Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-23-6.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-23.step"
  "Package_TO_SOT_SMD.3dshapes/SOT-583-8.step"
  "RF_Module.3dshapes/ESP32-S3-WROOM-1.step"
  "Resistor_SMD.3dshapes/R_0603_1608Metric.step"
)
for m in "${MODELS[@]}"; do
  out=".3dmodels/$m"
  [ -s "$out" ] && continue
  mkdir -p "$(dirname "$out")"
  url="$BASE/$(printf '%s' "$m" | sed 's/,/%2C/g')"
  curl -fsSL -o "$out" "$url" && echo "got $m" || echo "MISSING $m"
done
