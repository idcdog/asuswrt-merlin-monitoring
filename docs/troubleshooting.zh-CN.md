# 故障排除

[English](troubleshooting.md)

首先运行只读检查：

```bash
sudo ./scripts/preflight.sh
```

## SSH exporter 显示 stale

检查 `asus-wifi-exporter.service` 状态和日志，并以相同账户测试 `BatchMode=yes` SSH。出现 `Host key verification failed` 表示 host key 未确认或发生变化；应调查变化原因，不要关闭 host-key 验证。

当前 exporter 在路由器没有任何关联无线客户端时也会显示 stale，详见 [已知限制](limitations.zh-CN.md)。

## SNMP 没有数据

确认 SNMP Exporter 健康，并访问一次 `/snmp?target=路由器地址&module=if_mib&auth=asus_router_v2`。检查 UDP 161、防火墙、认证名称和私有 `asus-auth.yml`，不要在日志或 Issue 中输出 community。

## WAN 面板为零

`eth1` 不一定是 WAN。使用下面的 PromQL 列出接口，并把 Grafana 的 `wan_if` 设置为实际承载互联网流量的接口：

```promql
ifHCInOctets{instance="192.168.1.1"}
```

## Traffic Analyzer 没有历史

运行 `asus-traffic-importer --dry-run` 并查看 systemd 日志。当前小时会被主动排除，新启用后通常要等待一个完整小时。前置检查会报告 `sqlite3`、数据库可读性和表结构问题。

除非明确要重新扫描路由器仍保留的历史，否则不要删除 `/var/lib/asus-traffic-importer/state.json`。

## Grafana 显示 `No data`

确认 VictoriaMetrics 健康、`asus_wifi_exporter_up` 能查询到、datasource UID 为 `victoriametrics`，并检查 `router_ip`、`wan_if` 和实际 scrape 配置。

## Blackbox ICMP 失败

检查服务状态和日志。示例 unit 通过 `CAP_NET_RAW` 提供 ICMP 权限；发行版软件包可能使用不同账户、路径或 capability 配置。

## 设备更名只影响新数据

这是正常现象。Prometheus 标签属于时序身份，旧样本仍保留旧 `name`。历史查询应按 `mac` 聚合，再在展示层使用最新名称。
