# 架构与数据流

[English](architecture.en.md)

默认架构通过 SSH 采集路由器实时状态、活动 WAN 接口计数器和小时历史流量。只有需要查看全部接口 IF-MIB 时才启用可选 SNMP。

```text
                         ┌─────────────────────────────┐
                         │ Asuswrt / Asuswrt-Merlin    │
                         │                             │
                         │ SSH commands        SQLite │
                         └──────────┬────────────┬──┘
                                    │            │
                       every 30s    │            │ every 10m
                                    ▼            ▼
                         asus-wifi-exporter   asus-traffic-importer
                              :9101/:9102          │
                                    │              │
                                    └──────┬───────┘
                                           ▼
                                   VictoriaMetrics :8428
                                           │
                                           ▼
                                      Grafana :3000

Internet HTTP / ICMP / DNS ──> blackbox_exporter :9115 ──┘
```

## 实时 SSH 采集

`asus-wifi-exporter` 常驻运行。每个采集周期通过一次 SSH 会话在路由器执行只读 shell 脚本，然后解析：

- `/proc/uptime`、`/proc/loadavg`、`/proc/stat`、`/proc/meminfo`
- Conntrack 当前数量、上限及活跃 TCP/UDP 会话
- `nvram get` 返回的型号、固件和 WAN 状态
- `/sys/class/net` 返回的活动 WAN 字节、数据包、错误、丢弃、状态和速率
- `wl` 返回的无线射频、信道和关联客户端信息
- DHCP lease、ARP 与 `/jffs/nmp_cl_json.js` 中的设备身份

采集器在 `:9101/metrics` 暴露 Prometheus 指标。`up{job="asus_wifi_clients"}` 只代表抓取端点可访问；应同时观察 `asus_wifi_exporter_up`，它才代表最近一次可用 SSH 采集仍然新鲜。

同一进程还可在 `:9102` 提供无鉴权的设备名称管理页及 JSON API。名称按 MAC 保存到本地 JSON。实时指标下一次采集就会带上新名称；历史 Traffic Analyzer 样本的 `name` 标签不会被原地改写，因此建议主要用稳定的 `mac` 标签做历史聚合。

## 可选 SNMP 接口计数器

默认仪表盘不需要 SNMP。只有需要查看路由器全部接口的标准 IF-MIB 数据时，才启用可选抓取片段和 `snmp_exporter`。SNMP community 放在独立的 `asus-auth.yml`，不能进入版本库。

## Traffic Analyzer 导入

`asus-traffic-importer` 由 systemd timer 定期触发。它通过 SSH 调用路由器内置 `sqlite3`，读取已经结束的小时桶，并将每台设备的 TX/RX 字节数写入 VictoriaMetrics 的 Prometheus import API。

导入器在本地状态文件记录最新时间戳，重复执行不会重复扫描全部历史。首次运行会导入数据库中现存的全部完整小时数据；可先用 `--dry-run` 验证。

## Internet 与组件健康探测

Blackbox Exporter 负责三类探测：

- HTTPS：验证公网 HTTP 可达性与耗时。
- ICMP：观察基础网络往返时延。
- DNS：通过路由器 DNS 解析公共域名，观察解析成功率与耗时。

单一目标可能因对端限速或维护产生误报。生产使用可复制 scrape job，增加第二个独立目标，并分别展示结果。

## 权限边界

- 路由器 SSH 命令只读，不包含 `nvram set`、重启或配置应用操作。
- SSH host key 必须预先写入运行服务用户的 `known_hosts`。
- 设备名称管理 API 会写本机别名 JSON，不会修改路由器配置。
- Grafana 与 VictoriaMetrics 默认只使用本机回环地址互联。
