# 安装指南

以下示例假定监控服务器是使用 systemd 的 Linux，路由器地址为 `192.168.1.1`，SSH 端口为 `2222`。请按实际环境替换。

## 1. 前置条件

- Python 3.10 或更高版本、OpenSSH client
- VictoriaMetrics single-node
- Grafana
- Prometheus `snmp_exporter` 和 `blackbox_exporter`
- 路由器已启用 SSH、SNMP、Traffic Analyzer
- 路由器中存在 `nvram`、`wl`、`conntrack`；导入历史流量还需要 `sqlite3`

普通华硕原厂固件也可能提供 SSH、SNMP 和 Traffic Analyzer，但命令、文件路径及权限会因型号和固件分支变化。项目的已知基线是 RT-BE88U + Asuswrt-Merlin 3006.102.8_4。

## 2. 准备 SSH

把监控服务器的公钥加入路由器，并以运行采集器的用户预先接受 host key：

```bash
sudo ssh -p 2222 root@192.168.1.1 true
sudo ssh -p 2222 root@192.168.1.1 'nvram get productid; uptime'
```

服务启用了 `BatchMode=yes`，不会在后台等待密码或 host key 确认。

## 3. 安装自定义采集器

```bash
git clone https://github.com/idcdog/asuswrt-merlin-monitoring.git
cd asuswrt-merlin-monitoring
sudo ./scripts/install-host-components.sh
sudo editor /etc/default/asus-router-monitoring
```

先在前台验证实时采集器：

```bash
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-wifi-exporter --once'
```

验证历史流量但不写入 VictoriaMetrics：

```bash
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-traffic-importer --dry-run'
```

确认无误后设置开机启动：

```bash
sudo systemctl enable --now asus-wifi-exporter.service
sudo systemctl enable --now asus-traffic-importer.timer
```

## 4. 配置 SNMP Exporter

从 Prometheus `snmp_exporter` 官方发布包取得与程序版本匹配的 `snmp.yml`，确认其中包含 `if_mib` 模块，然后安装认证文件：

```bash
sudo install -d -m 0750 -o snmp_exporter -g snmp_exporter /etc/snmp_exporter
sudo install -m 0640 -o snmp_exporter -g snmp_exporter \
  config/snmp/asus-auth.yml.example /etc/snmp_exporter/asus-auth.yml
sudo editor /etc/snmp_exporter/asus-auth.yml
sudo install -m 0644 systemd/snmp-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now snmp-exporter.service
```

把 `CHANGE_ME` 替换为路由器实际 SNMP community。不要提交修改后的文件。

## 5. 配置 Blackbox Exporter

安装官方二进制和专用 `blackbox` 系统用户，然后：

```bash
sudo install -d -m 0755 /etc/blackbox_exporter
sudo install -m 0644 config/blackbox.yml /etc/blackbox_exporter/blackbox.yml
sudo install -m 0644 systemd/blackbox-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now blackbox-exporter.service
```

`CAP_NET_RAW` 用于 ICMP probe。若发行版采用不同的程序路径或服务用户，请同步修改 unit。

## 6. 让 VictoriaMetrics 抓取指标

将 `config/prometheus-scrape.yml` 复制到监控服务器并按实际环境修改目标。VictoriaMetrics single-node 启动参数需包含：

```text
-promscrape.config=/etc/victoriametrics/prometheus.yml
```

更新配置后重启 VictoriaMetrics，并检查：

```bash
curl -fsS http://127.0.0.1:8428/-/healthy
curl -fsS http://127.0.0.1:9101/metrics | head
curl -fsS http://127.0.0.1:9116/-/healthy
curl -fsS http://127.0.0.1:9115/-/healthy
```

## 7. 配置 Grafana

```bash
sudo install -d -m 0755 /var/lib/grafana/dashboards/router
sudo install -m 0644 dashboards/asus-router-network-overview.json \
  /var/lib/grafana/dashboards/router/asus-router-network-overview.json
sudo install -m 0644 config/grafana/provisioning/datasources/victoriametrics.yml \
  /etc/grafana/provisioning/datasources/victoriametrics.yml
sudo install -m 0644 config/grafana/provisioning/dashboards/router-monitoring.yml \
  /etc/grafana/provisioning/dashboards/router-monitoring.yml
sudo chown -R grafana:grafana /var/lib/grafana/dashboards/router
sudo systemctl enable --now grafana-server.service
sudo systemctl restart grafana-server.service
```

打开仪表盘后设置变量：

- `router_ip`：路由器 IP，默认 `192.168.1.1`
- `wan_if`：SNMP 中的 WAN 接口名，默认 `eth1`
- `management_url`：设备别名管理页，例如 `http://192.168.1.10:9102`
- `client`：无线设备筛选器，自动从指标标签生成

可用下面的 PromQL 确认 WAN 接口名称：

```promql
ifHCInOctets{instance="192.168.1.1"}
```

## 8. 设备名称管理

默认管理页只监听 `127.0.0.1:9102`。纯可信局域网可把 `MANAGEMENT_LISTEN_HOST` 改成监控服务器的 LAN IP，然后重启 exporter：

```bash
sudo systemctl restart asus-wifi-exporter.service
```

该网页没有登录保护。不要监听公网地址，也不要通过路由器做公网端口转发。

## 9. 升级

拉取新版本后重新运行安装脚本，再重启自定义组件。安装脚本不会覆盖现有 `/etc/default/asus-router-monitoring`：

```bash
git pull --ff-only
sudo ./scripts/install-host-components.sh
sudo systemctl restart asus-wifi-exporter.service
sudo systemctl restart asus-traffic-importer.timer
```
