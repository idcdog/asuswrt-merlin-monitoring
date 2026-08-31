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
| `asus_router_wan_receive_bytes_total` / `transmit_bytes_total` | Active-WAN cumulative byte counters |
| `asus_router_wan_receive_packets_total` / `transmit_packets_total` | Active-WAN cumulative packet counters |
| `asus_router_wan_receive_errors_total` / `transmit_errors_total` | Active-WAN cumulative error counters |
| `asus_router_wan_receive_dropped_total` / `transmit_dropped_total` | Linux active-WAN cumulative drop counters |
| `asus_router_wan_speed_bps` | Nominal active-WAN interface speed; omitted when unavailable |
| `asus_router_wan_oper_up` | Linux active-WAN interface operational state |
| `asus_router_wifi_radio_*` | Channel, utilization, and noise |
| `asus_wifi_station_*` | Per-station RSSI, SNR, rates, retries, and counters |
| `asus_wifi_stations` | Distinct associated wireless clients |
| `asus_wifi_exporter_up` | Whether the latest usable collection is fresh |
| `asus_wifi_exporter_collection_duration_seconds` | Latest SSH collection duration |

Device display name is a mutable `name` label; `mac` is the stable identity. Renaming produces new live series and does not rewrite historical labels.

WAN throughput is calculated from SSH-collected cumulative byte counters:

```promql
rate(asus_router_wan_receive_bytes_total{interface="$wan_if"}[2m]) * 8
rate(asus_router_wan_transmit_bytes_total{interface="$wan_if"}[2m]) * 8
```

WAN byte counters come from the active interface itself. They exclude ordinary `br0` LAN-to-LAN transfers, but include upstream-subnet traffic, router-originated traffic, and traffic that cannot be attributed to a client. The dashboard therefore labels daily totals as estimated WAN-interface traffic rather than billing-grade Internet usage. The daily trend uses `offset -1d` so the increase from one midnight to the next is plotted on the calendar day it measures instead of at the following midnight.

The Linux `*_dropped_total` counters are not guaranteed to have exactly the same semantics as SNMP IF-MIB discard counters. Do not expect strict point-for-point equality between them.

## Optional SNMP metrics

Enable `snmp_exporter` only when standard IF-MIB visibility for every router interface is required. The default SSH-only dashboard does not need SNMP. Its legacy IF-MIB query branches only preserve access to history already stored before migration.

## Traffic Analyzer metrics

`asus_traffic_analyzer_tx_bytes` and `asus_traffic_analyzer_rx_bytes` are completed hourly buckets with explicit historical timestamps. They are not monotonic counters. Use `sum_over_time` for range totals and do not apply `rate()`.

## Blackbox metrics

`probe_success`, `probe_duration_seconds`, `probe_http_status_code`, DNS duration metrics, and ICMP phase duration metrics describe endpoint availability and latency.

## Cardinality guidance

Wireless metrics use labels such as `mac`, `name`, `ip`, `band`, and `iface`. Name or IP changes create new series. Aggregate long-term data by `mac` and map a display name at presentation time when possible.
