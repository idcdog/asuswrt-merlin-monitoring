# Compatibility matrix

[简体中文](compatibility.zh-CN.md)

## Verified installation

| Layer | Verified baseline | Status |
|---|---|---|
| Router | ASUS RT-BE88U | Supported |
| Firmware | Asuswrt-Merlin 3006.102.8_4 | Supported |
| Wireless interfaces | `wl0 wl1` mapped to 2.4 GHz and 5 GHz | Supported |
| Monitoring host | CentOS Stream 10, x86_64 | Supported |
| Python | 3.12.13; code targets Python 3.10+ | Supported |
| VictoriaMetrics | single-node 1.125.1 | Supported |
| Grafana | 12.4.3 | Supported |
| SNMP Exporter | 0.30.1 with official `if_mib` | Supported |
| Blackbox Exporter | 0.28.0 | Supported |

`Supported` means the complete path has been observed on a real installation. It is not a vendor support promise.

## Expected compatibility

Standard SNMP `IF-MIB` collection should work on many ASUS models that expose SNMP, but interface names and WAN mapping vary. The SSH collector is more model-specific because it relies on Broadcom `wl`, Asuswrt NVRAM keys, Linux procfs paths, and Traffic Analyzer internals.

| Router characteristic | Expected result |
|---|---|
| Two Broadcom radios exposed as `wl0 wl1` | Most SSH metrics should work |
| Three radios or 6 GHz radio | Station parsing may work, but radio summary mapping is incomplete |
| MediaTek or Qualcomm wireless tools | Wireless SSH collection is unsupported |
| No Traffic Analyzer or no router `sqlite3` | Live metrics work; hourly history does not |
| Different Conntrack binary/path | System collection may fail until adapted |
| Dual-WAN/load balancing | Only the active NVRAM WAN unit is summarized |
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

Open a compatibility-report issue with the model, firmware branch, monitoring OS and tool versions, and redacted results. Never attach the SNMP community, SSH key, real MAC addresses, client names, public IP, or private network inventory.
