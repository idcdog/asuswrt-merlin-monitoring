#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: uninstall-host-components.sh --confirm [--purge-config] [--purge-state]

Remove only the custom ASUS collector binaries, web page, and systemd units
installed by install-host-components.sh. Configuration and state are preserved
unless their explicit purge options are supplied.
EOF
}

confirm=no
purge_config=no
purge_state=no
while [[ $# -gt 0 ]]; do
  case "$1" in
    --confirm) confirm=yes ;;
    --purge-config) purge_config=yes ;;
    --purge-state) purge_state=yes ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run this uninstaller as root" >&2
  exit 1
fi
if [[ "$confirm" != yes ]]; then
  echo "error: refusing to remove components without --confirm" >&2
  usage >&2
  exit 2
fi

systemctl disable --now asus-wifi-exporter.service asus-traffic-importer.timer
systemctl stop asus-traffic-importer.service

rm -f \
  /etc/systemd/system/asus-wifi-exporter.service \
  /etc/systemd/system/asus-traffic-importer.service \
  /etc/systemd/system/asus-traffic-importer.timer \
  /usr/local/bin/asus-wifi-exporter \
  /usr/local/bin/asus-traffic-importer \
  /usr/local/share/asus-wifi-exporter/device-names.html
rmdir /usr/local/share/asus-wifi-exporter 2>/dev/null || true

if [[ "$purge_config" == yes ]]; then
  rm -f /etc/default/asus-router-monitoring
else
  echo "preserved /etc/default/asus-router-monitoring"
fi

if [[ "$purge_state" == yes ]]; then
  rm -f \
    /var/lib/asus-wifi-exporter/device-names.json \
    /var/lib/asus-traffic-importer/state.json
  rmdir /var/lib/asus-wifi-exporter /var/lib/asus-traffic-importer 2>/dev/null || true
else
  echo "preserved device aliases and Traffic Analyzer import state"
fi

systemctl daemon-reload
echo "removed custom ASUS collector components"
