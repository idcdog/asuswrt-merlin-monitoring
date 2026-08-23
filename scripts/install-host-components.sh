#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "error: run this installer as root" >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "${script_dir}/.." && pwd)

install -m 0755 "${repo_dir}/src/asus_wifi_exporter.py" /usr/local/bin/asus-wifi-exporter
install -m 0755 "${repo_dir}/src/asus_traffic_importer.py" /usr/local/bin/asus-traffic-importer
install -d -m 0755 /usr/local/share/asus-wifi-exporter
install -m 0644 "${repo_dir}/web/device-names.html" \
  /usr/local/share/asus-wifi-exporter/device-names.html

install -m 0644 "${repo_dir}/systemd/asus-wifi-exporter.service" /etc/systemd/system/
install -m 0644 "${repo_dir}/systemd/asus-traffic-importer.service" /etc/systemd/system/
install -m 0644 "${repo_dir}/systemd/asus-traffic-importer.timer" /etc/systemd/system/

if [[ ! -e /etc/default/asus-router-monitoring ]]; then
  install -m 0640 "${repo_dir}/config/asus-router-monitoring.env.example" \
    /etc/default/asus-router-monitoring
  echo "created /etc/default/asus-router-monitoring; review it before starting services"
else
  echo "kept existing /etc/default/asus-router-monitoring"
fi

systemctl daemon-reload
echo "installed host components; services were not enabled or started"
