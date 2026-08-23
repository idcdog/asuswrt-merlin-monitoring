# Metric reference

[简体中文](metrics.md)

## Live SSH metrics

| Metric family | Purpose |
|---|---|
| `asus_router_info` | Model and firmware labels |
| `asus_router_uptime_seconds` | Router uptime |
| `asus_router_load1` / `load5` / `load15` | Load averages |
| `asus_router_cpu_usage_ratio` | Aggregate CPU utilization from counter deltas |
| `asus_router_memory_*_bytes` | Total, available, and used memory |
| `asus_router_memory_usage_ratio` | Memory utilization based on `MemAvailable` |
| `asus_router_temperature_celsius` | CPU and radio temperatures |
| `asus_router_conntrack_entries` / `active` / `limit` | Conntrack utilization and capacity |
| `asus_router_wan_info` / `wan_link_up` | Active WAN metadata and state |
| `asus_router_wifi_radio_*` | Channel, utilization, and noise |
| `asus_wifi_station_*` | Per-station RSSI, SNR, rates, retries, and counters |
| `asus_wifi_stations` | Distinct associated wireless clients |
| `asus_wifi_exporter_up` | Whether the latest usable collection is fresh |
| `asus_wifi_exporter_collection_duration_seconds` | Latest SSH collection duration |

Device display name is a mutable `name` label; `mac` is the stable identity. Renaming produces new live series and does not rewrite historical labels.

## SNMP metrics

The official `if_mib` module provides `ifHCInOctets`, `ifHCOutOctets`, interface errors, discards, operational state, and speed. WAN throughput is calculated from 64-bit byte counters:

```promql
rate(ifHCInOctets{instance="$router_ip",ifName="$wan_if"}[2m]) * 8
rate(ifHCOutOctets{instance="$router_ip",ifName="$wan_if"}[2m]) * 8
```

## Traffic Analyzer metrics

`asus_traffic_analyzer_tx_bytes` and `asus_traffic_analyzer_rx_bytes` are completed hourly buckets with explicit historical timestamps. They are not monotonic counters. Use `sum_over_time` for range totals and do not apply `rate()`.

## Blackbox metrics

`probe_success`, `probe_duration_seconds`, `probe_http_status_code`, DNS duration metrics, and ICMP phase duration metrics describe endpoint availability and latency.

## Cardinality guidance

Wireless metrics use labels such as `mac`, `name`, `ip`, `band`, and `iface`. Name or IP changes create new series. Aggregate long-term data by `mac` and map a display name at presentation time when possible.
