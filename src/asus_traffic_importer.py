#!/usr/bin/env python3
"""Import Asus Traffic Analyzer hourly per-device data into VictoriaMetrics."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Final


REMOTE_SCRIPT: Final[str] = r'''
set -eu
last_timestamp=$1
db_path=$(nvram get bwdpi_ana_path)
[ -n "$db_path" ] || db_path=/jffs/.sys/TrafficAnalyzer/TrafficAnalyzer.db
echo '@@NMP@@'
cat /jffs/nmp_cl_json.js 2>/dev/null || true
echo
echo '@@DATA@@'
sqlite3 -readonly -cmd '.timeout 3000' -separator '|' "$db_path" \
  "SELECT (timestamp / 3600) * 3600 AS hour_bucket,
          upper(mac),
          CAST(SUM(tx) AS INTEGER),
          CAST(SUM(rx) AS INTEGER)
   FROM traffic
   WHERE ((timestamp / 3600) * 3600) > $last_timestamp
     AND timestamp < ((strftime('%s', 'now') / 3600) * 3600)
   GROUP BY hour_bucket, upper(mac)
   ORDER BY hour_bucket, upper(mac);"
'''


@dataclass(frozen=True)
class Config:
    router_host: str
    router_port: int
    router_user: str
    ssh_timeout: int
    vm_import_url: str
    state_file: Path
    device_label: str


def load_config() -> Config:
    return Config(
        router_host=os.environ.get("ROUTER_HOST", "192.168.1.1"),
        router_port=int(os.environ.get("ROUTER_PORT", "2222")),
        router_user=os.environ.get("ROUTER_USER", "root"),
        ssh_timeout=int(os.environ.get("SSH_TIMEOUT", "30")),
        vm_import_url=os.environ.get("VM_IMPORT_URL", "http://127.0.0.1:8428/api/v1/import/prometheus"),
        state_file=Path(os.environ.get("STATE_FILE", "/var/lib/asus-traffic-importer/state.json")),
        device_label=os.environ.get("DEVICE_LABEL", "ASUS-Router"),
    )


def read_state(path: Path) -> int:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(state.get("last_timestamp", 0)))
    except FileNotFoundError:
        return 0


def write_state(path: Path, last_timestamp: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="state-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"last_timestamp": last_timestamp}, handle)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def ssh_query(config: Config, last_timestamp: int) -> str:
    command = [
        "/usr/bin/ssh",
        "-p", str(config.router_port),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        f"{config.router_user}@{config.router_host}",
        "sh", "-s", "--", str(last_timestamp),
    ]
    completed = subprocess.run(
        command,
        input=REMOTE_SCRIPT,
        text=True,
        capture_output=True,
        timeout=config.ssh_timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f"ssh exited with {completed.returncode}")
    return completed.stdout


def split_sections(raw: str) -> tuple[str, str]:
    marker = "@@DATA@@\n"
    if marker not in raw:
        raise RuntimeError("router response is missing Traffic Analyzer data marker")
    nmp_raw, rows = raw.split(marker, 1)
    return nmp_raw.replace("@@NMP@@\n", "", 1).strip(), rows.strip()


def parse_names(raw: str) -> dict[str, str]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        return {}
    data = json.loads(raw[start : end + 1])
    return {
        str(mac).upper(): str(value.get("name") or mac)
        for mac, value in data.items()
        if isinstance(value, dict)
    }


def escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def build_payload(
    rows: str, names: dict[str, str], device_label: str
) -> tuple[bytes, int, int, int]:
    lines: list[str] = []
    timestamps: set[int] = set()
    macs: set[str] = set()
    latest = 0
    for line_number, row in enumerate(rows.splitlines(), 1):
        if not row.strip():
            continue
        fields = row.split("|")
        if len(fields) != 4:
            raise RuntimeError(f"unexpected Traffic Analyzer row at line {line_number}")
        timestamp, mac, tx_bytes, rx_bytes = int(fields[0]), fields[1].upper(), int(fields[2]), int(fields[3])
        if timestamp <= 0 or tx_bytes < 0 or rx_bytes < 0 or not re.fullmatch(r"[0-9A-F:]{17}", mac):
            raise RuntimeError(f"invalid Traffic Analyzer values at line {line_number}")
        label_set = (
            f'mac="{mac}",name="{escape_label(names.get(mac, mac))}",'
            f'device="{escape_label(device_label)}",job="asus_traffic_analyzer"'
        )
        timestamp_ms = timestamp * 1000
        lines.append(f"asus_traffic_analyzer_tx_bytes{{{label_set}}} {tx_bytes} {timestamp_ms}")
        lines.append(f"asus_traffic_analyzer_rx_bytes{{{label_set}}} {rx_bytes} {timestamp_ms}")
        timestamps.add(timestamp)
        macs.add(mac)
        latest = max(latest, timestamp)
    payload = ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")
    return payload, len(timestamps), len(macs), latest


def import_payload(url: str, payload: bytes) -> None:
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "text/plain; version=0.0.4"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status // 100 != 2:
            raise RuntimeError(f"VictoriaMetrics import returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="query and validate without importing or updating state")
    args = parser.parse_args()
    config = load_config()
    last_timestamp = read_state(config.state_file)
    nmp_raw, rows = split_sections(ssh_query(config, last_timestamp))
    payload, buckets, devices, latest = build_payload(
        rows, parse_names(nmp_raw), config.device_label
    )
    if not payload:
        print(f"no_new_rows last_timestamp={last_timestamp}")
        return 0
    print(f"validated buckets={buckets} devices={devices} samples={payload.count(chr(10).encode())} latest={latest}")
    if args.dry_run:
        return 0
    import_payload(config.vm_import_url, payload)
    write_state(config.state_file, latest)
    print(f"imported latest={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
