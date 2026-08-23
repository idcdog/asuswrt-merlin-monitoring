#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "${script_dir}/.." && pwd)
cd "${repo_dir}"

python3 -m py_compile src/asus_wifi_exporter.py src/asus_traffic_importer.py
python3 src/asus_wifi_exporter.py --help >/dev/null
python3 src/asus_traffic_importer.py --help >/dev/null
python3 -m unittest discover -s tests -v
bash -n scripts/install-host-components.sh scripts/validate.sh

python3 - <<'PY'
import json
from pathlib import Path

for path in Path("dashboards").glob("*.json"):
    dashboard = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(dashboard.get("panels"), list):
        raise SystemExit(f"{path}: missing panels list")

    ids: set[int] = set()
    occupied: list[tuple[int, int, int, int, int]] = []
    for panel in dashboard["panels"]:
        panel_id = panel.get("id")
        if panel_id in ids:
            raise SystemExit(f"{path}: duplicate panel id {panel_id}")
        ids.add(panel_id)
        grid = panel.get("gridPos")
        if not isinstance(grid, dict):
            continue
        x, y, w, h = (int(grid[key]) for key in ("x", "y", "w", "h"))
        if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > 24:
            raise SystemExit(f"{path}: invalid grid position for panel {panel_id}")
        for other_id, ox, oy, ow, oh in occupied:
            overlaps = x < ox + ow and ox < x + w and y < oy + oh and oy < y + h
            if overlaps:
                raise SystemExit(f"{path}: panels {panel_id} and {other_id} overlap")
        occupied.append((panel_id, x, y, w, h))

    variables = {item.get("name") for item in dashboard.get("templating", {}).get("list", [])}
    required = {"router_ip", "wan_if", "management_url", "client"}
    if missing := required - variables:
        raise SystemExit(f"{path}: missing variables {sorted(missing)}")
PY

if rg -n -i \
  '(BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9_]+|idcdog\.com|zhangpeng|张朋|周娟)' \
  --glob '!scripts/validate.sh' .; then
  echo "error: possible secret or private identifier found" >&2
  exit 1
fi

if rg -n 'community:[[:space:]]+(?!CHANGE_ME)' config --pcre2; then
  echo "error: non-placeholder SNMP community found" >&2
  exit 1
fi

echo "validation passed"
