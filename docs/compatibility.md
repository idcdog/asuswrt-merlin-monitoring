# Compatibility matrix

[简体中文](compatibility.zh-CN.md)

## Verified installation

| Layer | Verified baseline | Status |
|---|---|---|
| Router | ASUS RT-BE88U | Supported |
| Firmware | Asuswrt-Merlin 3006.102.8_4 | Supported |
| Wireless interfaces | `wl0 wl1`, dynamically detected as 2.4 GHz and 5 GHz | Supported |
| Monitoring host | CentOS Stream 10, x86_64 | Supported |
| Python | 3.12.13; code targets Python 3.10+ | Supported |
| VictoriaMetrics | single-node 1.125.1 | Supported |
| Grafana | 12.4.3 | Supported |
| SNMP Exporter (optional) | 0.30.1 with official `if_mib` | Verified, disabled by default |
| Blackbox Exporter | 0.28.0 | Supported |

`Supported` means the complete path has been observed on a real installation. It is not a vendor support promise.

## Expected compatibility

The SSH collector is model-sensitive because it relies on Broadcom `wl`, Asuswrt NVRAM keys, Linux procfs/sysfs paths, and Traffic Analyzer internals. Optional standard SNMP `IF-MIB` should work on many ASUS models that expose SNMP, but it is not part of the default path.

| Router characteristic | Expected result |
|---|---|
| Broadcom radios listed in `wl_ifnames` | Dynamically discovered; 2.4/5/6 GHz parsing is implemented |
| Three radios or 6 GHz radio | Expected to work; real-model compatibility reports are still needed |
| MediaTek or Qualcomm wireless tools | Wireless SSH collection is unsupported |
| No Traffic Analyzer or no router `sqlite3` | Live metrics work; hourly history does not |
| Different Conntrack binary/path | System collection may fail until adapted |
| Dual-WAN/load balancing | Only the active NVRAM WAN unit is summarized |
| Active WAN lacks sysfs counters | Live collection fails explicitly instead of publishing guessed values |
| PPPoE/VLAN logical WAN lacks `speed` | Traffic counters remain available, but link speed and utilization are omitted |
| Stock Asuswrt with matching commands | May work, but is not verified |

## Before reporting compatibility

Run:

```bash
sudo ./scripts/preflight.sh
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-wifi-exporter --once'
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-traffic-importer --dry-run'
```

Open a compatibility-report issue with the model, firmware branch, monitoring OS and tool versions, and redacted results. Use `--check-snmp` only when testing optional SNMP. Never attach the SNMP community, SSH key, real MAC addresses, client names, public IP, or private network inventory.
