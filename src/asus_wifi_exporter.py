#!/usr/bin/env python3
"""Prometheus exporter for Asuswrt-Merlin wireless station metrics over SSH."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final


LOG = logging.getLogger("asus_wifi_exporter")

REMOTE_SCRIPT: Final[str] = r'''
set -u
echo '@@SYSTEM@@'
for key in productid firmver buildno extendno innerver; do
  printf '%s|' "$key"
  nvram get "$key"
done
wan_unit=$(nvram get wan_unit)
[ -n "$wan_unit" ] || wan_unit=0
wan_prefix="wan${wan_unit}"
printf 'wan_interface|'; nvram get "${wan_prefix}_ifname"
printf 'wan_protocol|'; nvram get "${wan_prefix}_proto"
printf 'wan_private_ipv4|'; nvram get "${wan_prefix}_ipaddr"
printf 'wan_public_ipv4|'; nvram get "${wan_prefix}_realip_ip"
wan_state=$(nvram get "${wan_prefix}_state_t")
wan_link=$(nvram get link_wan)
[ "$wan_state" = 2 ] && [ "$wan_link" = 1 ] && wan_up=1 || wan_up=0
printf 'wan_link_up|%s\n' "$wan_up"
awk '{print "uptime_seconds|" $1}' /proc/uptime
awk '{print "load1|" $1 "\nload5|" $2 "\nload15|" $3}' /proc/loadavg
awk '/^processor[[:space:]]*:/ {count++} END {print "cpu_cores|" count}' /proc/cpuinfo
awk '/^cpu / {printf "cpu_stat|"; for (i=2; i<=NF; i++) printf "%s%s", $i, (i<NF ? " " : "\n"); exit}' /proc/stat
awk '/^(MemTotal|MemAvailable|SwapTotal|SwapFree):/ {key=$1; sub(":", "", key); print tolower(key) "_kb|" $2}' /proc/meminfo
for conn_file in /proc/sys/net/netfilter/nf_conntrack_count /proc/sys/net/ipv4/netfilter/ip_conntrack_count; do
  if [ -r "$conn_file" ]; then
    printf 'conntrack_count|'
    cat "$conn_file"
    break
  fi
done
for conn_file in /proc/sys/net/netfilter/nf_conntrack_max /proc/sys/net/ipv4/netfilter/ip_conntrack_max; do
  if [ -r "$conn_file" ]; then
    printf 'conntrack_max|'
    cat "$conn_file"
    break
  fi
done
active_tcp=$(/usr/sbin/conntrack -L -p tcp --state ESTABLISHED 2>/dev/null | wc -l)
active_udp=$(/usr/sbin/conntrack -L -p udp 2>/dev/null | awk '/ASSURED/ {count++} END {print count + 0}')
printf 'conntrack_active|%s\n' "$((active_tcp + active_udp))"
if [ -r /sys/class/thermal/thermal_zone0/temp ]; then
  awk '{print "cpu_temp_millicelsius|" $1}' /sys/class/thermal/thermal_zone0/temp
fi
for radio in wl0 wl1; do
  temp=$(wl -i "$radio" phy_tempsense 2>/dev/null || true)
  temp=${temp%% *}
  [ -n "$temp" ] && printf '%s_temp_c|%s\n' "$radio" "$temp"
done
for radio in wl0 wl1; do
  case "$radio" in
    wl0) band='2.4G' ;;
    wl1) band='5G' ;;
  esac
  stats=$(wl -i "$radio" chanim_stats 2>/dev/null | awk 'NR > 2 && NF >= 15 {last=$0} END {print last}')
  if [ -n "$stats" ]; then
    set -- $stats
    channel=${1%%/*}
    utilization=$((100 - $14))
    [ "$utilization" -lt 0 ] && utilization=0
    [ "$utilization" -gt 100 ] && utilization=100
    printf 'radio_%s|%s|%s|%s|%s\n' "$radio" "$band" "$channel" "$utilization" "$13"
  fi
done
echo '@@NMP@@'
cat /jffs/nmp_cl_json.js 2>/dev/null || true
echo
echo '@@LEASES@@'
cat /var/lib/misc/dnsmasq.leases 2>/dev/null || true
echo '@@ARP@@'
cat /proc/net/arp 2>/dev/null || true
echo '@@STATIONS@@'
seen_ifaces=' '
for base in $(nvram get wl_ifnames); do
  vifs=$(nvram get "${base}_vifs")
  for iface in "$base" $vifs; do
    case "$seen_ifaces" in
      *" $iface "*) continue ;;
    esac
    seen_ifaces="$seen_ifaces$iface "
    wl -i "$iface" assoclist 2>/dev/null | while read -r tag mac; do
      [ "$tag" = assoclist ] || continue
      [ -n "${mac:-}" ] || continue
      echo "@@STA $iface $mac"
      wl -i "$iface" sta_info "$mac" 2>/dev/null || true
      echo '@@END@@'
    done
  done
done
'''


@dataclass(frozen=True)
class Config:
    router_host: str
    router_port: int
    router_user: str
    interval_seconds: int
    timeout_seconds: int
    listen_host: str
    listen_port: int
    management_host: str
    management_port: int
    alias_file: str
    management_html: str


@dataclass(frozen=True)
class DeviceIdentity:
    name: str
    vendor: str
    ip: str


@dataclass(frozen=True)
class Station:
    mac: str
    iface: str
    band: str
    identity: DeviceIdentity
    values: dict[str, float]


@dataclass(frozen=True)
class RadioSnapshot:
    iface: str
    band: str
    channel: float
    utilization_ratio: float
    noise_dbm: float


@dataclass(frozen=True)
class SystemSnapshot:
    model: str
    firmware: str
    inner_version: str
    uptime_seconds: float
    load1: float
    load5: float
    load15: float
    cpu_cores: float
    cpu_stat: tuple[float, ...]
    memory_total_bytes: float
    memory_available_bytes: float
    swap_total_bytes: float
    swap_free_bytes: float
    conntrack_count: float
    conntrack_max: float
    conntrack_active: float
    wan_link_up: float
    wan_interface: str
    wan_protocol: str
    wan_private_ipv4: str
    wan_public_ipv4: str
    radios: tuple[RadioSnapshot, ...]
    temperatures: tuple[tuple[str, float], ...]


def env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def load_config() -> Config:
    return Config(
        router_host=os.environ.get("ROUTER_HOST", "192.168.1.1"),
        router_port=env_int("ROUTER_PORT", 2222),
        router_user=os.environ.get("ROUTER_USER", "root"),
        interval_seconds=env_int("COLLECTION_INTERVAL", 30),
        timeout_seconds=env_int("SSH_TIMEOUT", 20),
        listen_host=os.environ.get("LISTEN_HOST", "127.0.0.1"),
        listen_port=env_int("LISTEN_PORT", 9101),
        management_host=os.environ.get("MANAGEMENT_LISTEN_HOST", "127.0.0.1"),
        management_port=env_int("MANAGEMENT_LISTEN_PORT", 9102),
        alias_file=os.environ.get("DEVICE_ALIAS_FILE", "/var/lib/asus-wifi-exporter/device-names.json"),
        management_html=os.environ.get(
            "MANAGEMENT_HTML", "/usr/local/share/asus-wifi-exporter/device-names.html"
        ),
    )


MAC_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?:[0-9A-F]{2}:){5}[0-9A-F]{2}$")


def normalize_mac(value: str) -> str:
    mac = value.strip().upper()
    if not MAC_PATTERN.fullmatch(mac):
        raise ValueError("invalid MAC address")
    return mac


def validate_alias(value: str) -> str:
    alias = value.strip()
    if not alias:
        raise ValueError("device name cannot be empty")
    if len(alias) > 64:
        raise ValueError("device name must not exceed 64 characters")
    if any(ord(character) < 32 for character in alias):
        raise ValueError("device name contains control characters")
    return alias


class AliasStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._aliases: dict[str, str] = {}
        self._mtime_ns = -1
        self._reload_locked()

    def _reload_locked(self) -> None:
        try:
            mtime_ns = self._path.stat().st_mtime_ns
        except FileNotFoundError:
            self._aliases = {}
            self._mtime_ns = -1
            return
        if mtime_ns == self._mtime_ns:
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("alias file must contain a JSON object")
            self._aliases = {
                normalize_mac(str(mac)): validate_alias(str(alias)) for mac, alias in raw.items()
            }
            self._mtime_ns = mtime_ns
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError(f"cannot load device alias file: {error}") from error

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            self._reload_locked()
            return dict(self._aliases)

    def set(self, mac_value: str, alias_value: str) -> dict[str, str]:
        mac, alias = normalize_mac(mac_value), validate_alias(alias_value)
        with self._lock:
            self._reload_locked()
            self._aliases[mac] = alias
            self._write_locked()
            return dict(self._aliases)

    def delete(self, mac_value: str) -> dict[str, str]:
        mac = normalize_mac(mac_value)
        with self._lock:
            self._reload_locked()
            self._aliases.pop(mac, None)
            self._write_locked()
            return dict(self._aliases)

    def _write_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = json.dumps(dict(sorted(self._aliases.items())), ensure_ascii=False, indent=2) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        temporary.chmod(0o640)
        os.replace(temporary, self._path)
        self._mtime_ns = self._path.stat().st_mtime_ns


def ssh_collect(config: Config) -> str:
    command = [
        "/usr/bin/ssh",
        "-p", str(config.router_port),
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={min(config.timeout_seconds, 10)}",
        "-o", "ServerAliveInterval=5",
        "-o", "ServerAliveCountMax=2",
        f"{config.router_user}@{config.router_host}",
        "sh", "-s",
    ]
    completed = subprocess.run(
        command,
        input=REMOTE_SCRIPT,
        text=True,
        capture_output=True,
        timeout=config.timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        error = completed.stderr.strip() or f"ssh exited with {completed.returncode}"
        raise RuntimeError(error)
    return completed.stdout


def section(text: str, start: str, end: str) -> str:
    match = re.search(
        rf"^{re.escape(start)}\s*$\n(.*?)^{re.escape(end)}\s*$",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def parse_nmp(raw: str) -> dict[str, dict[str, object]]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as error:
        LOG.warning("cannot parse nmp client JSON: %s", error)
        return {}
    return {str(key).upper(): value for key, value in parsed.items() if isinstance(value, dict)}


def parse_system(raw: str) -> SystemSnapshot:
    values: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition("|")
        if separator:
            values[key.strip()] = value.strip()

    def number(key: str, default: float = 0.0) -> float:
        try:
            return float(values.get(key, str(default)))
        except ValueError as error:
            raise RuntimeError(f"invalid router system value for {key}") from error

    firmver = values.get("firmver", "")
    buildno = values.get("buildno", "")
    extendno = values.get("extendno", "")
    firmware = f"{firmver.replace('.', '')}.{buildno}_{extendno}" if firmver and buildno and extendno else "unknown"
    cpu_stat = tuple(float(value) for value in values.get("cpu_stat", "").split())
    if len(cpu_stat) < 4:
        raise RuntimeError("router returned incomplete aggregate CPU counters")
    temperatures: list[tuple[str, float]] = []
    for key, sensor, scale in (
        ("cpu_temp_millicelsius", "cpu", 0.001),
        ("wl0_temp_c", "wifi_2_4ghz", 1.0),
        ("wl1_temp_c", "wifi_5ghz", 1.0),
    ):
        if key in values:
            temperatures.append((sensor, number(key) * scale))
    radios: list[RadioSnapshot] = []
    for line in raw.splitlines():
        key, separator, payload = line.partition("|")
        if not separator or not key.startswith("radio_"):
            continue
        fields = payload.split("|")
        if len(fields) != 4:
            raise RuntimeError(f"invalid router radio value for {key}")
        try:
            radios.append(RadioSnapshot(
                iface=key.removeprefix("radio_"),
                band=fields[0],
                channel=float(fields[1]),
                utilization_ratio=float(fields[2]) / 100.0,
                noise_dbm=float(fields[3]),
            ))
        except ValueError as error:
            raise RuntimeError(f"invalid router radio value for {key}") from error
    return SystemSnapshot(
        model=values.get("productid", "unknown"),
        firmware=firmware,
        inner_version=values.get("innerver", "unknown"),
        uptime_seconds=number("uptime_seconds"),
        load1=number("load1"),
        load5=number("load5"),
        load15=number("load15"),
        cpu_cores=number("cpu_cores"),
        cpu_stat=cpu_stat,
        memory_total_bytes=number("memtotal_kb") * 1024,
        memory_available_bytes=number("memavailable_kb") * 1024,
        swap_total_bytes=number("swaptotal_kb") * 1024,
        swap_free_bytes=number("swapfree_kb") * 1024,
        conntrack_count=number("conntrack_count"),
        conntrack_max=number("conntrack_max"),
        conntrack_active=number("conntrack_active"),
        wan_link_up=number("wan_link_up"),
        wan_interface=values.get("wan_interface", "unknown"),
        wan_protocol=values.get("wan_protocol", "unknown"),
        wan_private_ipv4=values.get("wan_private_ipv4", ""),
        wan_public_ipv4=values.get("wan_public_ipv4", ""),
        radios=tuple(radios),
        temperatures=tuple(temperatures),
    )


def parse_leases(raw: str) -> dict[str, tuple[str, str]]:
    leases: dict[str, tuple[str, str]] = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) >= 4 and re.fullmatch(r"[0-9A-Fa-f:]{17}", fields[1]):
            hostname = "" if fields[3] == "*" else fields[3]
            leases[fields[1].upper()] = (fields[2], hostname)
    return leases


def merge_arp(raw: str, leases: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    merged = dict(leases)
    for line in raw.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and re.fullmatch(r"[0-9A-Fa-f:]{17}", fields[3]):
            mac = fields[3].upper()
            _, hostname = merged.get(mac, ("", ""))
            merged[mac] = (fields[0], hostname)
    return merged


def first_number(body: str, pattern: str) -> float | None:
    match = re.search(pattern, body, flags=re.MULTILINE | re.IGNORECASE)
    return float(match.group(1)) if match else None


def average_numbers(body: str, pattern: str) -> float | None:
    match = re.search(pattern, body, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    values = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", match.group(1))]
    return sum(values) / len(values) if values else None


VALUE_PATTERNS: Final[dict[str, str]] = {
    "connected_seconds": r"^\s*in network\s+(\d+)\s+seconds",
    "idle_seconds": r"^\s*idle\s+(\d+)\s+seconds",
    "ap_tx_bytes_total": r"^\s*tx total bytes:\s*(\d+)",
    "ap_rx_bytes_total": r"^\s*rx data bytes:\s*(\d+)",
    "ap_tx_unicast_bytes_total": r"^\s*tx ucast bytes:\s*(\d+)",
    "ap_rx_unicast_bytes_total": r"^\s*rx ucast bytes:\s*(\d+)",
    "ap_tx_packets_total": r"^\s*tx total pkts:\s*(\d+)",
    "ap_rx_packets_total": r"^\s*rx data pkts:\s*(\d+)",
    "tx_failures_total": r"^\s*tx failures:\s*(\d+)",
    "tx_packets_sent_total": r"^\s*tx total pkts sent:\s*(\d+)",
    "tx_retries_total": r"^\s*tx pkts retries:\s*(\d+)",
    "tx_retry_exhausted_total": r"^\s*tx pkts retry exhausted:\s*(\d+)",
    "rssi_dbm": r"^\s*smoothed rssi:\s*(-?\d+(?:\.\d+)?)",
    "tx_rate_kbps": r"^\s*rate of last tx pkt:\s*(\d+(?:\.\d+)?)\s*kbps",
    "rx_rate_kbps": r"^\s*rate of last rx pkt:\s*(\d+(?:\.\d+)?)\s*kbps",
    "bandwidth_mhz": r"^\s*link bandwidth\s*=\s*(\d+(?:\.\d+)?)\s*MHZ",
    "max_rate_mbps": r"^\s*Max Rate\s*=\s*(\d+(?:\.\d+)?)\s*Mbps",
}


def parse_station_blocks(
    raw: str,
    clients: dict[str, dict[str, object]],
    leases: dict[str, tuple[str, str]],
) -> list[Station]:
    stations: list[Station] = []
    pattern = re.compile(
        r"^@@STA\s+(\S+)\s+([0-9A-Fa-f:]{17})\s*$\n(.*?)^@@END@@\s*$",
        flags=re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(raw):
        iface, mac, body = match.group(1), match.group(2).upper(), match.group(3)
        client = clients.get(mac, {})
        ip, lease_name = leases.get(mac, ("", ""))
        name = str(client.get("name") or lease_name or mac)
        vendor = str(client.get("vendor") or client.get("vendorclass") or "")
        channel = first_number(body, r"^\s*chanspec\s+(\d+)")
        wireless_code = str(client.get("wireless") or "")
        if channel is not None:
            band = "2.4G" if channel <= 14 else ("5G" if channel <= 177 else "6G")
        else:
            band = {"1": "2.4G", "2": "5G", "3": "6G"}.get(wireless_code, "unknown")
        values = {
            key: value
            for key, pattern_text in VALUE_PATTERNS.items()
            if (value := first_number(body, pattern_text)) is not None
        }
        noise = average_numbers(body, r"^\s*per antenna noise floor:\s*(.+?)\s*$")
        if noise is not None:
            values["noise_dbm"] = noise
            if "rssi_dbm" in values:
                values["snr_db"] = values["rssi_dbm"] - noise
        if channel is not None:
            values["channel"] = channel
        if "tx_rate_kbps" in values:
            values["tx_rate_bps"] = values.pop("tx_rate_kbps") * 1_000
        if "rx_rate_kbps" in values:
            values["rx_rate_bps"] = values.pop("rx_rate_kbps") * 1_000
        if "max_rate_mbps" in values:
            values["max_rate_bps"] = values.pop("max_rate_mbps") * 1_000_000
        stations.append(Station(mac, iface, band, DeviceIdentity(name, vendor, ip), values))
    return stations


def apply_aliases(stations: list[Station], aliases: dict[str, str]) -> list[Station]:
    return [
        Station(
            mac=station.mac,
            iface=station.iface,
            band=station.band,
            identity=DeviceIdentity(
                name=aliases.get(station.mac, station.identity.name),
                vendor=station.identity.vendor,
                ip=station.identity.ip,
            ),
            values=station.values,
        )
        for station in stations
    ]


def build_device_inventory(
    clients: dict[str, dict[str, object]],
    leases: dict[str, tuple[str, str]],
    stations: list[Station],
    aliases: dict[str, str],
) -> list[dict[str, object]]:
    station_by_mac = {station.mac: station for station in stations}
    macs = set(clients) | set(leases) | set(station_by_mac) | set(aliases)
    devices: list[dict[str, object]] = []
    for mac in macs:
        client = clients.get(mac, {})
        lease_ip, lease_name = leases.get(mac, ("", ""))
        station = station_by_mac.get(mac)
        original_name = str(
            client.get("name")
            or lease_name
            or (station.identity.name if station else "")
            or mac
        )
        ip = lease_ip or str(client.get("ip") or "") or (station.identity.ip if station else "")
        vendor = str(client.get("vendor") or client.get("vendorclass") or "")
        if not vendor and station:
            vendor = station.identity.vendor
        devices.append({
            "mac": mac,
            "name": aliases.get(mac, original_name),
            "alias": aliases.get(mac, ""),
            "original_name": original_name,
            "ip": ip,
            "vendor": vendor,
            "online": station is not None,
            "band": station.band if station else "",
        })
    return sorted(devices, key=lambda device: (not bool(device["online"]), str(device["name"]).lower()))


def metric_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def metric_value(value: float) -> str:
    return str(int(value)) if value.is_integer() else format(value, ".12g")


def labels(station: Station) -> str:
    values = {
        "mac": station.mac,
        "name": station.identity.name,
        "vendor": station.identity.vendor,
        "ip": station.identity.ip,
        "band": station.band,
        "iface": station.iface,
    }
    return ",".join(f'{key}="{metric_label(value)}"' for key, value in values.items())


METRICS: Final[dict[str, tuple[str, str, str]]] = {
    "connected_seconds": ("gauge", "station connection age", "seconds"),
    "idle_seconds": ("gauge", "station idle time", "seconds"),
    "ap_tx_bytes_total": ("counter", "bytes sent by AP to station; download-side wireless traffic", "bytes"),
    "ap_rx_bytes_total": ("counter", "bytes received by AP from station; upload-side wireless traffic", "bytes"),
    "ap_tx_unicast_bytes_total": ("counter", "unicast bytes sent by AP to station", "bytes"),
    "ap_rx_unicast_bytes_total": ("counter", "unicast bytes received by AP from station", "bytes"),
    "ap_tx_packets_total": ("counter", "packets sent by AP to station", "packets"),
    "ap_rx_packets_total": ("counter", "packets received by AP from station", "packets"),
    "tx_failures_total": ("counter", "AP transmit failures for station connection", "failures"),
    "tx_packets_sent_total": ("counter", "AP transmit packets sent for station connection, excluding retry attempts", "packets"),
    "tx_retries_total": ("counter", "AP transmit retries for station connection", "retries"),
    "tx_retry_exhausted_total": ("counter", "AP packets with exhausted retries", "packets"),
    "rssi_dbm": ("gauge", "smoothed station RSSI", "dBm"),
    "noise_dbm": ("gauge", "average per-antenna noise floor", "dBm"),
    "snr_db": ("gauge", "station signal-to-noise ratio calculated as RSSI minus noise floor", "dB"),
    "tx_rate_bps": ("gauge", "last AP-to-station PHY rate", "bits per second"),
    "rx_rate_bps": ("gauge", "last station-to-AP PHY rate", "bits per second"),
    "bandwidth_mhz": ("gauge", "wireless link channel width", "MHz"),
    "max_rate_bps": ("gauge", "reported maximum station PHY rate", "bits per second"),
    "channel": ("gauge", "current wireless channel", "channel"),
}


def render_station_metrics(stations: list[Station]) -> str:
    lines = [
        "# HELP asus_wifi_stations Number of distinct associated wireless stations.",
        "# TYPE asus_wifi_stations gauge",
        f"asus_wifi_stations {len({station.mac for station in stations})}",
        "# HELP asus_wifi_station_info Wireless station identity and current link.",
        "# TYPE asus_wifi_station_info gauge",
    ]
    for station in stations:
        lines.append(f"asus_wifi_station_info{{{labels(station)}}} 1")
    for key, (metric_type, help_text, unit) in METRICS.items():
        metric = f"asus_wifi_station_{key}"
        lines.extend([f"# HELP {metric} {help_text} ({unit}).", f"# TYPE {metric} {metric_type}"])
        for station in stations:
            if key in station.values:
                lines.append(f"{metric}{{{labels(station)}}} {metric_value(station.values[key])}")
    return "\n".join(lines) + "\n"


def render_device_name_metrics(devices: list[dict[str, object]]) -> str:
    lines = [
        "# HELP asus_device_name_info Resolved display name for a device MAC address.",
        "# TYPE asus_device_name_info gauge",
    ]
    for device in devices:
        label_values = {
            "mac": str(device["mac"]),
            "name": str(device["name"]),
            "original_name": str(device["original_name"]),
            "ip": str(device["ip"]),
            "source": "manual" if device["alias"] else "router",
        }
        rendered = ",".join(
            f'{key}="{metric_label(value)}"' for key, value in label_values.items()
        )
        lines.append(f"asus_device_name_info{{{rendered}}} 1")
    return "\n".join(lines) + "\n"


def cpu_usage_ratio(current: tuple[float, ...], previous: tuple[float, ...] | None) -> float | None:
    if previous is None or len(current) != len(previous):
        return None
    current_total, previous_total = sum(current), sum(previous)
    current_idle = current[3] + (current[4] if len(current) > 4 else 0.0)
    previous_idle = previous[3] + (previous[4] if len(previous) > 4 else 0.0)
    delta_total = current_total - previous_total
    delta_idle = current_idle - previous_idle
    if delta_total <= 0:
        return None
    return min(1.0, max(0.0, (delta_total - delta_idle) / delta_total))


def render_system_metrics(snapshot: SystemSnapshot, previous_cpu: tuple[float, ...] | None = None) -> str:
    used_memory = max(0.0, snapshot.memory_total_bytes - snapshot.memory_available_bytes)
    memory_ratio = used_memory / snapshot.memory_total_bytes if snapshot.memory_total_bytes > 0 else 0.0
    used_swap = max(0.0, snapshot.swap_total_bytes - snapshot.swap_free_bytes)
    info_labels = ",".join([
        f'model="{metric_label(snapshot.model)}"',
        f'firmware="{metric_label(snapshot.firmware)}"',
        f'inner_version="{metric_label(snapshot.inner_version)}"',
    ])
    wan_labels = ",".join([
        f'interface="{metric_label(snapshot.wan_interface)}"',
        f'protocol="{metric_label(snapshot.wan_protocol)}"',
        f'private_ipv4="{metric_label(snapshot.wan_private_ipv4)}"',
        f'public_ipv4="{metric_label(snapshot.wan_public_ipv4)}"',
    ])
    lines = [
        "# HELP asus_router_info Router model and firmware information.",
        "# TYPE asus_router_info gauge",
        f"asus_router_info{{{info_labels}}} 1",
        "# HELP asus_router_uptime_seconds Router uptime.",
        "# TYPE asus_router_uptime_seconds gauge",
        f"asus_router_uptime_seconds {metric_value(snapshot.uptime_seconds)}",
        "# HELP asus_router_boot_time_seconds Estimated router boot time as Unix time.",
        "# TYPE asus_router_boot_time_seconds gauge",
        f"asus_router_boot_time_seconds {metric_value(time.time() - snapshot.uptime_seconds)}",
        "# HELP asus_router_load1 One-minute load average.",
        "# TYPE asus_router_load1 gauge",
        f"asus_router_load1 {metric_value(snapshot.load1)}",
        "# HELP asus_router_load5 Five-minute load average.",
        "# TYPE asus_router_load5 gauge",
        f"asus_router_load5 {metric_value(snapshot.load5)}",
        "# HELP asus_router_load15 Fifteen-minute load average.",
        "# TYPE asus_router_load15 gauge",
        f"asus_router_load15 {metric_value(snapshot.load15)}",
        "# HELP asus_router_cpu_cores Number of router CPU cores.",
        "# TYPE asus_router_cpu_cores gauge",
        f"asus_router_cpu_cores {metric_value(snapshot.cpu_cores)}",
        "# HELP asus_router_memory_total_bytes Total physical memory.",
        "# TYPE asus_router_memory_total_bytes gauge",
        f"asus_router_memory_total_bytes {metric_value(snapshot.memory_total_bytes)}",
        "# HELP asus_router_memory_available_bytes Memory available to new workloads.",
        "# TYPE asus_router_memory_available_bytes gauge",
        f"asus_router_memory_available_bytes {metric_value(snapshot.memory_available_bytes)}",
        "# HELP asus_router_memory_used_bytes Total memory minus available memory.",
        "# TYPE asus_router_memory_used_bytes gauge",
        f"asus_router_memory_used_bytes {metric_value(used_memory)}",
        "# HELP asus_router_memory_usage_ratio Memory usage ratio based on MemAvailable.",
        "# TYPE asus_router_memory_usage_ratio gauge",
        f"asus_router_memory_usage_ratio {metric_value(memory_ratio)}",
        "# HELP asus_router_swap_total_bytes Total swap space.",
        "# TYPE asus_router_swap_total_bytes gauge",
        f"asus_router_swap_total_bytes {metric_value(snapshot.swap_total_bytes)}",
        "# HELP asus_router_swap_used_bytes Used swap space.",
        "# TYPE asus_router_swap_used_bytes gauge",
        f"asus_router_swap_used_bytes {metric_value(used_swap)}",
        "# HELP asus_router_conntrack_entries Current number of tracked connection entries.",
        "# TYPE asus_router_conntrack_entries gauge",
        f"asus_router_conntrack_entries {metric_value(snapshot.conntrack_count)}",
        "# HELP asus_router_conntrack_limit Configured maximum number of tracked connection entries.",
        "# TYPE asus_router_conntrack_limit gauge",
        f"asus_router_conntrack_limit {metric_value(snapshot.conntrack_max)}",
        "# HELP asus_router_conntrack_active Active connections using the Asuswrt-Merlin definition: TCP ESTABLISHED plus UDP ASSURED.",
        "# TYPE asus_router_conntrack_active gauge",
        f"asus_router_conntrack_active {metric_value(snapshot.conntrack_active)}",
        "# HELP asus_router_wan_link_up Whether the active WAN interface is connected.",
        "# TYPE asus_router_wan_link_up gauge",
        f"asus_router_wan_link_up {metric_value(snapshot.wan_link_up)}",
        "# HELP asus_router_wan_info Active WAN interface, protocol, private address, and detected public IPv4 address.",
        "# TYPE asus_router_wan_info gauge",
        f"asus_router_wan_info{{{wan_labels}}} 1",
        "# HELP asus_router_wifi_radio_channel Current primary channel for each wireless radio.",
        "# TYPE asus_router_wifi_radio_channel gauge",
        "# HELP asus_router_wifi_radio_channel_utilization_ratio Estimated channel utilization as one minus the chanim idle percentage.",
        "# TYPE asus_router_wifi_radio_channel_utilization_ratio gauge",
        "# HELP asus_router_wifi_radio_noise_dbm Radio noise floor reported by Broadcom chanim.",
        "# TYPE asus_router_wifi_radio_noise_dbm gauge",
        "# HELP asus_router_temperature_celsius Router temperature sensors.",
        "# TYPE asus_router_temperature_celsius gauge",
    ]
    for radio in snapshot.radios:
        radio_labels = f'iface="{metric_label(radio.iface)}",band="{metric_label(radio.band)}"'
        lines.extend([
            f"asus_router_wifi_radio_channel{{{radio_labels}}} {metric_value(radio.channel)}",
            f"asus_router_wifi_radio_channel_utilization_ratio{{{radio_labels}}} {metric_value(radio.utilization_ratio)}",
            f"asus_router_wifi_radio_noise_dbm{{{radio_labels}}} {metric_value(radio.noise_dbm)}",
        ])
    lines.extend(
        f'asus_router_temperature_celsius{{sensor="{metric_label(sensor)}"}} {metric_value(value)}'
        for sensor, value in snapshot.temperatures
    )
    usage = cpu_usage_ratio(snapshot.cpu_stat, previous_cpu)
    if usage is not None:
        lines.extend([
            "# HELP asus_router_cpu_usage_ratio Aggregate CPU usage ratio calculated from counter deltas.",
            "# TYPE asus_router_cpu_usage_ratio gauge",
            f"asus_router_cpu_usage_ratio {metric_value(usage)}",
        ])
    return "\n".join(lines) + "\n"


class CollectorState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._station_metrics = ""
        self._devices: list[dict[str, object]] = []
        self.last_success = 0.0
        self.duration = 0.0
        self.error_count = 0
        self.last_error = "not collected yet"

    def success(self, station_metrics: str, devices: list[dict[str, object]], duration: float) -> None:
        with self._lock:
            self._station_metrics = station_metrics
            self._devices = devices
            self.last_success = time.time()
            self.duration = duration
            self.last_error = ""

    def failure(self, error: Exception, duration: float) -> None:
        with self._lock:
            self.error_count += 1
            self.duration = duration
            self.last_error = str(error)

    def render(self, interval_seconds: int) -> tuple[str, bool]:
        with self._lock:
            healthy = self.last_success > 0 and time.time() - self.last_success <= interval_seconds * 3
            prefix = "\n".join([
                "# HELP asus_wifi_exporter_up Whether the most recent usable collection is fresh.",
                "# TYPE asus_wifi_exporter_up gauge",
                f"asus_wifi_exporter_up {1 if healthy else 0}",
                "# HELP asus_wifi_exporter_collection_duration_seconds Duration of the latest collection.",
                "# TYPE asus_wifi_exporter_collection_duration_seconds gauge",
                f"asus_wifi_exporter_collection_duration_seconds {self.duration:.6f}",
                "# HELP asus_wifi_exporter_last_success_unixtime_seconds Unix time of the last successful collection.",
                "# TYPE asus_wifi_exporter_last_success_unixtime_seconds gauge",
                f"asus_wifi_exporter_last_success_unixtime_seconds {int(self.last_success)}",
                "# HELP asus_wifi_exporter_collection_errors_total Total failed collections.",
                "# TYPE asus_wifi_exporter_collection_errors_total counter",
                f"asus_wifi_exporter_collection_errors_total {self.error_count}",
            ]) + "\n"
            return prefix + self._station_metrics, healthy

    def devices(self, aliases: dict[str, str]) -> list[dict[str, object]]:
        with self._lock:
            devices = [dict(device) for device in self._devices]
        known_macs = {str(device["mac"]) for device in devices}
        for device in devices:
            mac = str(device["mac"])
            device["alias"] = aliases.get(mac, "")
            device["name"] = aliases.get(mac, str(device["original_name"]))
        for mac, alias in aliases.items():
            if mac not in known_macs:
                devices.append({
                    "mac": mac,
                    "name": alias,
                    "alias": alias,
                    "original_name": mac,
                    "ip": "",
                    "vendor": "",
                    "online": False,
                    "band": "",
                })
        return sorted(devices, key=lambda device: (not bool(device["online"]), str(device["name"]).lower()))


def collect_once(
    config: Config, alias_store: AliasStore
) -> tuple[str, SystemSnapshot, list[dict[str, object]]]:
    raw = ssh_collect(config)
    system = parse_system(section(raw, "@@SYSTEM@@", "@@NMP@@"))
    nmp = parse_nmp(section(raw, "@@NMP@@", "@@LEASES@@"))
    leases = parse_leases(section(raw, "@@LEASES@@", "@@ARP@@"))
    leases = merge_arp(section(raw, "@@ARP@@", "@@STATIONS@@"), leases)
    raw_stations = parse_station_blocks(raw, nmp, leases)
    aliases = alias_store.snapshot()
    stations = apply_aliases(raw_stations, aliases)
    if not stations:
        raise RuntimeError("router returned no wireless station records")
    devices = build_device_inventory(nmp, leases, raw_stations, aliases)
    metrics = render_device_name_metrics(devices) + render_station_metrics(stations)
    return metrics, system, devices


def collection_loop(config: Config, state: CollectorState, alias_store: AliasStore) -> None:
    previous_cpu: tuple[float, ...] | None = None
    while True:
        started = time.monotonic()
        try:
            station_metrics, system, devices = collect_once(config, alias_store)
            metrics = render_system_metrics(system, previous_cpu) + station_metrics
            state.success(metrics, devices, time.monotonic() - started)
            previous_cpu = system.cpu_stat
        except Exception as error:  # keep serving the last known good snapshot
            duration = time.monotonic() - started
            state.failure(error, duration)
            LOG.error("collection failed: %s", error)
        elapsed = time.monotonic() - started
        time.sleep(max(1.0, config.interval_seconds - elapsed))


def handler_factory(state: CollectorState, interval_seconds: int) -> type[BaseHTTPRequestHandler]:
    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path not in ("/metrics", "/healthz"):
                self.send_error(404)
                return
            payload, healthy = state.render(interval_seconds)
            if self.path == "/healthz":
                payload = ("ok\n" if healthy else "stale\n")
            encoded = payload.encode("utf-8")
            self.send_response(200 if healthy else 503)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, fmt: str, *args: object) -> None:
            LOG.debug(fmt, *args)

    return MetricsHandler


def management_handler_factory(
    state: CollectorState, alias_store: AliasStore, html_path: str
) -> type[BaseHTTPRequestHandler]:
    class ManagementHandler(BaseHTTPRequestHandler):
        def send_payload(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, status: int, value: object) -> None:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_payload(status, payload, "application/json; charset=utf-8")

        def read_json(self) -> dict[str, object]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as error:
                raise ValueError("invalid content length") from error
            if length <= 0 or length > 4096:
                raise ValueError("request body must be between 1 and 4096 bytes")
            try:
                value = json.loads(self.rfile.read(length))
            except json.JSONDecodeError as error:
                raise ValueError("invalid JSON body") from error
            if not isinstance(value, dict):
                raise ValueError("JSON body must be an object")
            return value

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                try:
                    payload = Path(html_path).read_bytes()
                except OSError as error:
                    self.send_json(500, {"error": f"cannot load management page: {error}"})
                    return
                self.send_payload(200, payload, "text/html; charset=utf-8")
                return
            if self.path == "/api/devices":
                try:
                    aliases = alias_store.snapshot()
                    self.send_json(200, {"devices": state.devices(aliases), "aliases": aliases})
                except RuntimeError as error:
                    self.send_json(500, {"error": str(error)})
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/aliases":
                self.send_error(404)
                return
            try:
                request = self.read_json()
                aliases = alias_store.set(str(request.get("mac", "")), str(request.get("name", "")))
                self.send_json(200, {"ok": True, "aliases": aliases})
            except (ValueError, RuntimeError, OSError) as error:
                self.send_json(400, {"error": str(error)})

        def do_DELETE(self) -> None:  # noqa: N802
            if self.path != "/api/aliases":
                self.send_error(404)
                return
            try:
                request = self.read_json()
                aliases = alias_store.delete(str(request.get("mac", "")))
                self.send_json(200, {"ok": True, "aliases": aliases})
            except (ValueError, RuntimeError, OSError) as error:
                self.send_json(400, {"error": str(error)})

        def log_message(self, fmt: str, *args: object) -> None:
            LOG.info("management %s - %s", self.client_address[0], fmt % args)

    return ManagementHandler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="collect once and print metrics")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    alias_store = AliasStore(config.alias_file)
    if args.once:
        station_metrics, system, _ = collect_once(config, alias_store)
        print(render_system_metrics(system) + station_metrics, end="")
        return 0
    state = CollectorState()
    threading.Thread(target=collection_loop, args=(config, state, alias_store), daemon=True).start()
    metrics_server = ThreadingHTTPServer(
        (config.listen_host, config.listen_port), handler_factory(state, config.interval_seconds)
    )
    management_server = ThreadingHTTPServer(
        (config.management_host, config.management_port),
        management_handler_factory(state, alias_store, config.management_html),
    )
    threading.Thread(target=metrics_server.serve_forever, daemon=True).start()
    LOG.info("metrics listening on %s:%s", config.listen_host, config.listen_port)
    LOG.info("management listening on %s:%s", config.management_host, config.management_port)
    management_server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
