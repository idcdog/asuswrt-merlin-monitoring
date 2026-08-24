#!/usr/bin/env bash
set -uo pipefail

script_source=${BASH_SOURCE[0]-$0}
script_dir=$(cd -- "$(dirname -- "$script_source")" && pwd)
repo_dir=$(cd -- "${script_dir}/.." && pwd)
env_file=/etc/default/asus-router-monitoring
env_file_explicit=no
mode=all
check_snmp=no
passes=0
warnings=0
failures=0
detected_wan_interface=''

usage() {
  cat <<'EOF'
Usage: preflight.sh [--env-file PATH] [--host-only | --router-only] [--check-snmp]

Run read-only compatibility and connectivity checks. The script never installs
packages, writes router configuration, starts services, or imports metrics.
SNMP checks run only when --check-snmp is explicitly supplied.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      [[ $# -ge 2 ]] || { echo "error: --env-file requires a path" >&2; exit 2; }
      env_file=$2
      env_file_explicit=yes
      shift 2
      ;;
    --host-only)
      mode=host
      shift
      ;;
    --router-only)
      mode=router
      shift
      ;;
    --check-snmp)
      check_snmp=yes
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

pass() {
  passes=$((passes + 1))
  printf 'PASS  %s\n' "$*"
}

warn() {
  warnings=$((warnings + 1))
  printf 'WARN  %s\n' "$*"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL  %s\n' "$*"
}

info() {
  printf 'INFO  %s\n' "$*"
}

command_check() {
  local command_name=$1
  local required=${2:-yes}
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "host command available: ${command_name}"
  elif [[ "$required" == yes ]]; then
    fail "host command missing: ${command_name}"
  else
    warn "optional host command missing: ${command_name}"
  fi
}

http_check() {
  local name=$1
  local url=$2
  if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null 2>&1; then
    pass "${name} reachable: ${url}"
  else
    warn "${name} not reachable yet: ${url}"
  fi
}

if [[ -r "$env_file" ]]; then
  # This is an administrator-owned shell environment file used by systemd units.
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  pass "loaded configuration: ${env_file}"
elif [[ -r "${repo_dir}/config/asus-router-monitoring.env.example" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${repo_dir}/config/asus-router-monitoring.env.example"
  set +a
  warn "configuration not found at ${env_file}; using repository example values"
elif [[ "$env_file_explicit" == yes ]]; then
  fail "configuration file not readable: ${env_file}"
else
  warn "configuration not found at ${env_file}; using built-in defaults"
fi

ROUTER_HOST=${ROUTER_HOST:-192.168.1.1}
ROUTER_PORT=${ROUTER_PORT:-2222}
ROUTER_USER=${ROUTER_USER:-root}
SSH_TIMEOUT=${SSH_TIMEOUT:-20}
LISTEN_HOST=${LISTEN_HOST:-127.0.0.1}
LISTEN_PORT=${LISTEN_PORT:-9101}
MANAGEMENT_LISTEN_HOST=${MANAGEMENT_LISTEN_HOST:-127.0.0.1}
MANAGEMENT_LISTEN_PORT=${MANAGEMENT_LISTEN_PORT:-9102}
VICTORIAMETRICS_URL=${VICTORIAMETRICS_URL:-http://127.0.0.1:8428}
GRAFANA_URL=${GRAFANA_URL:-http://127.0.0.1:3000}
BLACKBOX_EXPORTER_URL=${BLACKBOX_EXPORTER_URL:-http://127.0.0.1:9115}
if [[ "$check_snmp" == yes ]]; then
  SNMP_EXPORTER_URL=${SNMP_EXPORTER_URL:-http://127.0.0.1:9116}
  SNMP_AUTH=${SNMP_AUTH:-asus_router_v2}
fi

if [[ ! "$ROUTER_HOST" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  fail "ROUTER_HOST contains unsupported characters"
fi
if [[ ! "$ROUTER_USER" =~ ^[A-Za-z0-9._-]+$ ]]; then
  fail "ROUTER_USER contains unsupported characters"
fi
for port_name in ROUTER_PORT LISTEN_PORT MANAGEMENT_LISTEN_PORT; do
  port_value=${!port_name}
  if [[ "$port_value" =~ ^[0-9]+$ ]] && ((port_value >= 1 && port_value <= 65535)); then
    pass "${port_name} is valid: ${port_value}"
  else
    fail "${port_name} must be an integer between 1 and 65535"
  fi
done

if [[ "$mode" != router ]]; then
  printf '\nHost checks\n'
  command_check python3
  command_check ssh
  command_check curl
  command_check systemctl
  command_check rg no

  if command -v python3 >/dev/null 2>&1; then
    if python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
      pass "Python version supported: $(python3 --version 2>&1)"
    else
      fail "Python 3.10 or newer is required"
    fi
  fi

  if [[ -x /usr/local/bin/asus-wifi-exporter ]]; then
    pass "asus-wifi-exporter installed"
  else
    warn "asus-wifi-exporter not installed yet"
  fi
  if [[ -x /usr/local/bin/asus-traffic-importer ]]; then
    pass "asus-traffic-importer installed"
  else
    warn "asus-traffic-importer not installed yet"
  fi

  http_check "VictoriaMetrics" "${VICTORIAMETRICS_URL%/}/-/healthy"
  http_check "Grafana" "${GRAFANA_URL%/}/api/health"
  if [[ "$check_snmp" == yes ]]; then
    http_check "SNMP Exporter" "${SNMP_EXPORTER_URL%/}/-/healthy"
  fi
  http_check "Blackbox Exporter" "${BLACKBOX_EXPORTER_URL%/}/-/healthy"
  http_check "SSH metrics exporter" "http://${LISTEN_HOST}:${LISTEN_PORT}/healthz"
  http_check "device-name manager" "http://${MANAGEMENT_LISTEN_HOST}:${MANAGEMENT_LISTEN_PORT}/"
fi

if [[ "$mode" != host ]]; then
  printf '\nRouter checks\n'
  if ! command -v ssh >/dev/null 2>&1; then
    fail "cannot run router checks without the host ssh command"
  elif [[ ! "$ROUTER_PORT" =~ ^[0-9]+$ ]]; then
    fail "cannot run router checks with invalid ROUTER_PORT"
  else
    ssh_command=(
      ssh
      -p "$ROUTER_PORT"
      -o BatchMode=yes
      -o "ConnectTimeout=${SSH_TIMEOUT}"
      -o ServerAliveInterval=5
      -o ServerAliveCountMax=2
      "${ROUTER_USER}@${ROUTER_HOST}"
      sh -s
    )
    remote_script=$(cat <<'EOF'
set -u
PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin
for command_name in nvram wl conntrack sqlite3; do
  if which "$command_name" >/dev/null 2>&1; then
    printf 'command_%s=present\n' "$command_name"
  else
    printf 'command_%s=missing\n' "$command_name"
  fi
done
if which nvram >/dev/null 2>&1; then
  printf 'model='; nvram get productid
  printf 'firmver='; nvram get firmver
  printf 'buildno='; nvram get buildno
  printf 'extendno='; nvram get extendno
  printf 'wl_ifnames='; nvram get wl_ifnames
  wan_unit=$(nvram get wan_unit)
  [ -n "$wan_unit" ] || wan_unit=0
  wan_interface=$(nvram get "wan${wan_unit}_ifname")
  printf 'wan_interface=%s\n' "$wan_interface"
  wan_stats_compatible=1
  if [ -z "$wan_interface" ] || ! printf '%s\n' "$wan_interface" | grep -Eq '^[A-Za-z0-9_.:-]+$'; then
    wan_stats_compatible=0
  else
    for counter in rx_bytes tx_bytes rx_packets tx_packets rx_errors tx_errors rx_dropped tx_dropped; do
      counter_path="/sys/class/net/${wan_interface}/statistics/${counter}"
      if [ ! -r "$counter_path" ]; then
        wan_stats_compatible=0
        continue
      fi
      counter_value=$(cat "$counter_path")
      if [ -z "$counter_value" ] || ! printf '%s\n' "$counter_value" | grep -Eq '^[0-9]+$'; then
        wan_stats_compatible=0
      fi
    done
  fi
  [ "$wan_stats_compatible" -eq 1 ] && echo 'wan_stats=compatible' || echo 'wan_stats=incompatible'
  if [ -r "/sys/class/net/${wan_interface}/speed" ]; then
    printf 'wan_speed_mbps='; cat "/sys/class/net/${wan_interface}/speed"
  else
    echo 'wan_speed_mbps=unavailable'
  fi
  db_path=$(nvram get bwdpi_ana_path)
else
  db_path=''
fi
[ -n "$db_path" ] || db_path=/jffs/.sys/TrafficAnalyzer/TrafficAnalyzer.db
[ -r "$db_path" ] && echo 'traffic_db=readable' || echo 'traffic_db=missing'
[ -r /jffs/nmp_cl_json.js ] && echo 'device_inventory=readable' || echo 'device_inventory=missing'
[ -r /proc/net/arp ] && echo 'arp=readable' || echo 'arp=missing'
if which sqlite3 >/dev/null 2>&1 && [ -r "$db_path" ]; then
  columns=$(sqlite3 -readonly -cmd '.timeout 3000' "$db_path" 'PRAGMA table_info(traffic);' 2>/dev/null | awk -F'|' '{print $2}')
  schema_compatible=1
  for required_column in timestamp mac tx rx; do
    printf '%s\n' "$columns" | grep -qx "$required_column" || schema_compatible=0
  done
  if [ "$schema_compatible" -eq 1 ]; then
    echo 'traffic_schema=compatible'
  else
    echo 'traffic_schema=incompatible'
  fi
else
  echo 'traffic_schema=unavailable'
fi
EOF
)
    started=$(date +%s)
    if router_output=$(printf '%s\n' "$remote_script" | "${ssh_command[@]}" 2>&1); then
      elapsed=$(( $(date +%s) - started ))
      pass "SSH public-key collection succeeded in ${elapsed}s"
      model=$(printf '%s\n' "$router_output" | sed -n 's/^model=//p' | head -1)
      firmver=$(printf '%s\n' "$router_output" | sed -n 's/^firmver=//p' | head -1)
      buildno=$(printf '%s\n' "$router_output" | sed -n 's/^buildno=//p' | head -1)
      extendno=$(printf '%s\n' "$router_output" | sed -n 's/^extendno=//p' | head -1)
      wl_ifnames=$(printf '%s\n' "$router_output" | sed -n 's/^wl_ifnames=//p' | head -1)
      detected_wan_interface=$(printf '%s\n' "$router_output" | sed -n 's/^wan_interface=//p' | head -1)
      wan_speed_mbps=$(printf '%s\n' "$router_output" | sed -n 's/^wan_speed_mbps=//p' | head -1)
      if [[ -n "$model" ]]; then
        pass "router model detected: ${model}"
      else
        fail "router model not returned by nvram"
      fi
      [[ -n "$firmver$buildno$extendno" ]] && info "router firmware components: ${firmver} / ${buildno} / ${extendno}"
      if [[ -n "$wl_ifnames" ]]; then
        info "wireless base interfaces: ${wl_ifnames}"
      else
        fail "wl_ifnames is empty"
      fi
      if [[ -n "$detected_wan_interface" ]]; then
        info "active WAN interface reported by Asuswrt: ${detected_wan_interface}"
      else
        warn "active WAN interface was not returned by Asuswrt"
      fi
      if grep -q '^wan_stats=compatible$' <<<"$router_output"; then
        pass "active WAN sysfs counters are readable and numeric"
      else
        fail "active WAN sysfs counters are incomplete or invalid"
      fi
      if [[ "$wan_speed_mbps" =~ ^[0-9]+$ ]] && ((wan_speed_mbps > 0)); then
        pass "active WAN negotiated speed available: ${wan_speed_mbps} Mbps"
      else
        warn "active WAN negotiated speed is unavailable; utilization panels will have no data"
      fi

      for required_command in nvram wl conntrack; do
        if grep -q "^command_${required_command}=present$" <<<"$router_output"; then
          pass "router command available: ${required_command}"
        else
          fail "router command missing from SSH PATH: ${required_command}"
        fi
      done
      if grep -q '^command_sqlite3=present$' <<<"$router_output"; then
        pass "router command available: sqlite3"
      else
        warn "sqlite3 missing; Traffic Analyzer history import is unavailable"
      fi
      if grep -q '^traffic_db=readable$' <<<"$router_output"; then
        pass "Traffic Analyzer database readable"
      else
        warn "Traffic Analyzer database missing or unreadable"
      fi
      if grep -q '^traffic_schema=compatible$' <<<"$router_output"; then
        pass "Traffic Analyzer schema contains timestamp/mac/tx/rx"
      else
        warn "Traffic Analyzer schema unavailable or incompatible"
      fi
      if grep -q '^device_inventory=readable$' <<<"$router_output"; then
        pass "router device inventory readable"
      else
        warn "/jffs/nmp_cl_json.js is unavailable"
      fi
    else
      fail "SSH collection failed: ${router_output}"
    fi
  fi

  if [[ "$check_snmp" == yes ]] && command -v curl >/dev/null 2>&1; then
    snmp_probe_url="${SNMP_EXPORTER_URL%/}/snmp?target=${ROUTER_HOST}&module=if_mib&auth=${SNMP_AUTH}"
    snmp_output=$(mktemp)
    if curl --fail --silent --show-error --max-time 20 "$snmp_probe_url" >"$snmp_output" 2>/dev/null; then
      if grep -q 'ifName="' "$snmp_output"; then
        pass "SNMP if_mib collection succeeded"
        interfaces=$(sed -n 's/.*ifName="\([^"]*\)".*/\1/p' "$snmp_output" | sort -u | tr '\n' ' ')
        [[ -n "$interfaces" ]] && info "SNMP interfaces: ${interfaces}"
        if [[ -n "$detected_wan_interface" ]]; then
          if grep -Fq "ifName=\"${detected_wan_interface}\"" "$snmp_output"; then
            pass "WAN interface auto-discovery matched SNMP: ${detected_wan_interface}"
            info "Grafana wan_if should resolve automatically to ${detected_wan_interface}"
          else
            warn "Asuswrt WAN interface ${detected_wan_interface} is absent from SNMP ifName labels"
          fi
        fi
      else
        warn "SNMP endpoint responded without ifName metrics"
      fi
    else
      warn "SNMP collection not ready through ${SNMP_EXPORTER_URL}"
    fi
    rm -f "$snmp_output"
  fi
fi

printf '\nSummary: %d PASS, %d WARN, %d FAIL\n' "$passes" "$warnings" "$failures"
((failures == 0))
