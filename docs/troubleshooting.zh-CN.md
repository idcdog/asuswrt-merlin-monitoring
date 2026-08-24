# 故障排除

[English](troubleshooting.md)

首先运行只读检查：

```bash
sudo ./scripts/preflight.sh
```

## SSH exporter 显示 stale

检查 `asus-wifi-exporter.service` 状态和日志，并以相同账户测试 `BatchMode=yes` SSH。出现 `Host key verification failed` 表示 host key 未确认或发生变化；应调查变化原因，不要关闭 host-key 验证。

没有任何关联无线客户端是合法状态，应发布 `asus_wifi_stations 0`。若仍然 stale，请检查日志中的命令错误、缺失状态标记或截断输出。

## 可选 SNMP 没有数据

默认 SSH-only 部署可以忽略本节。启用可选 SNMP 后，使用 `preflight.sh --check-snmp`，并检查 UDP 161、防火墙、认证名称和私有 `asus-auth.yml`。不要在日志或 Issue 中输出 community。

## WAN 面板为零

仪表盘从 `asus_router_wan_info` 自动发现活动 WAN 接口。先运行前置检查，然后用下面的 PromQL 检查 SSH 计数器和接口标签：

```promql
asus_router_wan_receive_bytes_total
```

如果字节计数存在但速率或利用率为空，检查 `asus_router_wan_speed_bps`。逻辑接口不提供可靠速度时，该指标会被有意省略。

## Traffic Analyzer 没有历史

运行 `asus-traffic-importer --dry-run` 并查看 systemd 日志。当前小时会被主动排除，新启用后通常要等待一个完整小时。前置检查会报告 `sqlite3`、数据库可读性和表结构问题。

除非明确要重新扫描路由器仍保留的历史，否则不要删除 `/var/lib/asus-traffic-importer/state.json`。

## Grafana 显示 `No data`

确认 VictoriaMetrics 健康、`asus_wifi_exporter_up` 能查询到、datasource UID 为 `victoriametrics`，并检查 `wan_if` 和实际 scrape 配置。`router_ip` 仅供迁移前的 SNMP 历史回退查询使用。

## Blackbox ICMP 失败

检查服务状态和日志。示例 unit 通过 `CAP_NET_RAW` 提供 ICMP 权限；发行版软件包可能使用不同账户、路径或 capability 配置。

## 设备更名只影响新数据

这是正常现象。Prometheus 标签属于时序身份，旧样本仍保留旧 `name`。历史查询应按 `mac` 聚合，再在展示层使用最新名称。
