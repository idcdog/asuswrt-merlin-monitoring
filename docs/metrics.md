# 指标说明

## 实时 SSH 指标

主要指标由 `asus-wifi-exporter` 生成。完整名称可通过 `curl http://127.0.0.1:9101/metrics` 查看。

| 指标族 | 用途 |
|---|---|
| `asus_router_info` | 型号、固件版本和内部版本标签 |
| `asus_router_uptime_seconds` | 路由器开机时长 |
| `asus_router_load1` / `load5` / `load15` | 1/5/15 分钟负载 |
| `asus_router_cpu_usage_ratio` | 采集周期内 CPU 使用率，0 到 1 |
| `asus_router_memory_*_bytes` | 总内存、可用内存和已用内存 |
| `asus_router_memory_usage_ratio` | 内存使用率，0 到 1 |
| `asus_router_temperature_celsius` | CPU 与无线射频温度 |
| `asus_router_conntrack_entries` / `active` / `limit` | 当前连接、活跃连接和最大容量 |
| `asus_router_wan_info` | WAN 接口、协议和地址标签 |
| `asus_router_wan_link_up` | WAN 链路是否在线 |
| `asus_router_wifi_radio_*` | 信道、利用率和噪声 |
| `asus_wifi_station_*` | 每台无线客户端的 RSSI、SNR、速率、重试等 |
| `asus_wifi_stations` | 当前关联的无线设备数 |
| `asus_wifi_exporter_up` | 最近一次可用 SSH 采集是否仍然新鲜 |
| `asus_wifi_exporter_collection_duration_seconds` | SSH 采集及解析耗时 |

设备名称位于 `name` 标签，MAC 位于稳定的 `mac` 标签。重命名后，新实时样本立即使用新名称；旧时序不会被重写。

## SNMP 指标

这些指标来自官方 `if_mib` 模块：

| 指标 | 用途 |
|---|---|
| `ifHCInOctets` / `ifHCOutOctets` | 64 位接口累计接收/发送字节数 |
| `ifInErrors` / `ifOutErrors` | 接口错误包累计值 |
| `ifInDiscards` / `ifOutDiscards` | 接口丢弃包累计值 |
| `ifOperStatus` | 接口运行状态 |
| `ifSpeed` / `ifHighSpeed` | 接口标称速率 |

WAN 实时下载/上传带宽由累计字节数的速率计算：

```promql
rate(ifHCInOctets{instance="$router_ip",ifName="$wan_if"}[2m]) * 8
rate(ifHCOutOctets{instance="$router_ip",ifName="$wan_if"}[2m]) * 8
```

## Traffic Analyzer 指标

| 指标 | 用途 |
|---|---|
| `asus_traffic_analyzer_tx_bytes` | 每设备每完整小时上传字节数 |
| `asus_traffic_analyzer_rx_bytes` | 每设备每完整小时下载字节数 |

这两个指标是带显式历史时间戳的小时桶，而不是单调累计 counter。做时间范围合计时应使用 `sum_over_time`，不要再对它们使用 `rate()`。

## Blackbox 指标

| 指标 | 用途 |
|---|---|
| `probe_success` | 探测是否成功 |
| `probe_duration_seconds` | 端到端探测耗时 |
| `probe_http_status_code` | HTTP 状态码 |
| `probe_dns_lookup_time_seconds` | DNS 查询耗时 |
| `probe_icmp_duration_seconds` | ICMP 各阶段耗时 |

## 标签与基数

- `mac`、`name`、`ip`、`band`、`iface` 用于无线设备查询。
- 设备改名会产生新的标签组合和时序。长期统计应以 `mac` 聚合，显示层再映射别名。
- 不要把不断变化的值放进标签，也不要把全部 DHCP 历史客户端永久暴露成实时指标。
