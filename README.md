# Asuswrt-Merlin Monitoring

通过 SSH、SNMP 和 Blackbox Exporter 监控华硕路由器，并用 VictoriaMetrics 与 Grafana 展示路由器健康、WAN 流量、无线客户端质量和历史流量。

项目最初针对 RT-BE88U + Asuswrt-Merlin 3006.102.8_4 构建。SSH 采集部分依赖 `nvram`、`wl`、`conntrack` 和 Asuswrt Traffic Analyzer，其他型号需要先运行一次 `--once` 验证兼容性。

## 功能

- 路由器开机时间、固件、CPU、负载、内存、温度和 Conntrack
- WAN 状态、SNMP 接口流量、错误包、丢弃包和端口利用率
- 无线客户端 MAC、IP、名称、频段、RSSI、SNR、协商速率和重试
- 基于 MAC 的设备名称覆盖网页
- Traffic Analyzer 小时级设备历史流量导入
- HTTP、ICMP、DNS 延迟和可用性探测
- Grafana 总览模板和 VictoriaMetrics 抓取配置
- systemd 开机自启动示例

## 架构

```text
ASUS Router
  ├─ SSH ───────────────> asus-wifi-exporter :9101
  ├─ Traffic Analyzer ──> asus-traffic-importer
  └─ SNMP ──────────────> snmp_exporter :9116

Internet targets ───────> blackbox_exporter :9115
                                 │
                                 ▼
                       VictoriaMetrics :8428
                                 │
                                 ▼
                            Grafana :3000
```

更详细的数据流见 [docs/architecture.md](docs/architecture.md)。

## Grafana 效果预览

截图来自实际运行环境，已遮挡设备名称、IP、MAC 和公网地址。

![路由器网络总览](docs/images/01-overview-redacted.png)

![互联网质量](docs/images/04-internet-quality.png)

![无线质量](docs/images/05-wireless-quality-redacted.png)

![历史流量](docs/images/07-history-redacted.png)

更多分区截图见 [Grafana 截图集](docs/screenshots.md)。

## 快速开始

1. 在路由器开启 SSH、SNMP 和 Traffic Analyzer。
2. 从监控服务器配置到路由器的 SSH 公钥登录，并先手动接受主机指纹：

   ```bash
   ssh root@192.168.1.1 -p 2222 true
   ```

3. 复制环境配置并修改路由器地址、端口和监听地址：

   ```bash
   sudo cp config/asus-router-monitoring.env.example /etc/default/asus-router-monitoring
   sudo editor /etc/default/asus-router-monitoring
   ```

4. 安装自定义采集器和 systemd 单元：

   ```bash
   sudo ./scripts/install-host-components.sh
   sudo systemctl enable --now asus-wifi-exporter.service
   sudo systemctl enable --now asus-traffic-importer.timer
   ```

5. 安装 `snmp_exporter`、`blackbox_exporter`、VictoriaMetrics 和 Grafana，复制 `config/` 中对应配置。
6. 把 Grafana provisioning 文件放到 `/etc/grafana/provisioning/`，把仪表盘 JSON 放到 `/var/lib/grafana/dashboards/router/`。
7. 在 Grafana 顶部变量中设置路由器 IP、WAN 接口和设备管理 URL。

完整步骤见 [docs/installation.md](docs/installation.md)。

## 目录

```text
src/          SSH exporter 和 Traffic Analyzer importer
web/          设备名称管理网页
dashboards/   Grafana 仪表盘 JSON
config/       VictoriaMetrics、Blackbox、SNMP 和 Grafana 配置
systemd/      开机启动单元
docs/         架构、安装和指标说明
scripts/      安装与校验脚本
examples/     不含真实设备信息的示例
```

## 安全说明

- 不要把 SNMP community、SSH 私钥或真实设备别名提交到 Git。
- 设备名称管理接口没有鉴权，默认只监听 `127.0.0.1`。若开放到局域网，请确保网络可信，或在前面增加带认证的反向代理。
- exporter 通过 SSH 执行只读采集命令，不执行 `nvram set`、应用设置或重启。
- Grafana 模板中的 `192.168.1.1`、`192.168.1.10` 和 `eth1` 都是示例值。

详见 [SECURITY.md](SECURITY.md)。

## 许可证

[MIT](LICENSE)
