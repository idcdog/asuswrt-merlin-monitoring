# Installation guide

[简体中文](installation.md)

The examples assume a systemd-based Linux monitoring host, router address `192.168.1.1`, and SSH port `2222`. Replace every example value with the values for your network.

## 1. Verified baseline and prerequisites

The initial verified installation uses:

| Component | Verified version |
|---|---|
| Router | ASUS RT-BE88U |
| Firmware | Asuswrt-Merlin 3006.102.8_4 |
| Monitoring OS | CentOS Stream 10, x86_64 |
| Python | 3.12.13; minimum supported 3.10 |
| VictoriaMetrics single-node | 1.125.1 |
| Grafana | 12.4.3 |
| SNMP Exporter (optional) | 0.30.1 |
| Blackbox Exporter | 0.28.0 |

Required host tools are Python 3.10+, OpenSSH client, curl, and systemd. The router must expose SSH. Traffic history requires Asuswrt Traffic Analyzer and a router `sqlite3` binary. SNMP is optional.

Other versions may work but have not been validated as a set. See the [compatibility matrix](compatibility.md).

## 2. Configure SSH

Install the monitoring host public key on the router, then accept the host key as the same account that will run the service. The provided units run the custom collectors as host `root` so this example populates `/root/.ssh/known_hosts`:

```bash
sudo ssh -p 2222 root@192.168.1.1 true
sudo ssh -p 2222 root@192.168.1.1 'nvram get productid; uptime'
```

Collectors use `BatchMode=yes` and never wait for a password or host-key prompt in the background.

## 3. Configure and run preflight

```bash
git clone https://github.com/idcdog/asuswrt-merlin-monitoring.git
cd asuswrt-merlin-monitoring
sudo cp config/asus-router-monitoring.env.example /etc/default/asus-router-monitoring
sudo editor /etc/default/asus-router-monitoring
sudo ./scripts/preflight.sh
```

Preflight is read-only. Resolve every `FAIL` before installation. Review `WARN` results because they may identify optional components or an unsupported router variant.

## 4. Install the custom collectors

```bash
sudo ./scripts/install-host-components.sh
```

The installer copies the two Python entrypoints, the device-name page, and their systemd units. It does not enable or start any service.

Validate live collection in the foreground:

```bash
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-wifi-exporter --once'
```

Validate Traffic Analyzer without importing or updating state:

```bash
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-traffic-importer --dry-run'
```

Enable services only after both checks succeed:

```bash
sudo systemctl enable --now asus-wifi-exporter.service
sudo systemctl enable --now asus-traffic-importer.timer
```

## 5. Optional: install SNMP Exporter

Skip this section for the default SSH-only dashboard. Enable it only when standard IF-MIB data for every router interface is required. Also merge `config/prometheus-scrape-snmp-optional.yml` into the VictoriaMetrics scrape configuration and run `sudo ./scripts/preflight.sh --check-snmp`.

Download an official SNMP Exporter release for the host architecture and verify its published checksum. Install the binary as `/usr/local/bin/snmp_exporter`, create an unprivileged `snmp_exporter` system account, and obtain the matching official `snmp.yml` containing `if_mib`.

```bash
sudo install -d -m 0750 -o snmp_exporter -g snmp_exporter /etc/snmp_exporter
sudo install -m 0640 -o snmp_exporter -g snmp_exporter \
  config/snmp/asus-auth.yml.example /etc/snmp_exporter/asus-auth.yml
sudo editor /etc/snmp_exporter/asus-auth.yml
sudo install -m 0644 systemd/snmp-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now snmp-exporter.service
```

Replace `CHANGE_ME` with the router community and never commit the edited file.

## 6. Install Blackbox Exporter

Download and verify an official release, install it as `/usr/local/bin/blackbox_exporter`, and create an unprivileged `blackbox` system account.

```bash
sudo install -d -m 0755 /etc/blackbox_exporter
sudo install -m 0644 config/blackbox.yml /etc/blackbox_exporter/blackbox.yml
sudo install -m 0644 systemd/blackbox-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now blackbox-exporter.service
```

The unit grants only `CAP_NET_RAW`, which is required for ICMP probes. Adjust binary paths and service users when your distribution packages them differently.

## 7. Configure VictoriaMetrics

Merge `config/prometheus-scrape.yml` into the host scrape configuration and replace the example addresses. VictoriaMetrics single-node must start with:

```text
-promscrape.config=/etc/victoriametrics/prometheus.yml
```

Restart VictoriaMetrics and verify local endpoints:

```bash
curl -fsS http://127.0.0.1:8428/-/healthy
curl -fsS http://127.0.0.1:9101/metrics | head
curl -fsS http://127.0.0.1:9115/-/healthy
```

## 8. Configure Grafana

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

Set these dashboard variables:

- `router_ip`: legacy SNMP history selector; new SSH-only installations can leave the example value
- `wan_if`: query variable discovered from the active interface in `asus_router_wan_info`
- `management_url`: optional device-name manager URL
- `client`: generated automatically from device-name metrics

The active WAN is discovered over SSH. Confirm the current interface with:

```promql
asus_router_wan_info{job="asus_wifi_clients"}
```

## 9. Network exposure

The metrics endpoint and device manager bind to loopback by default. Only change `MANAGEMENT_LISTEN_HOST` to a LAN address on a trusted network. The manager has no authentication and must never be exposed to the Internet.

No inbound router port forwarding is required. The monitoring host initiates SSH connections to the router.

## 10. Upgrade and uninstall

Upgrade custom collectors:

```bash
git pull --ff-only
sudo ./scripts/install-host-components.sh
sudo systemctl restart asus-wifi-exporter.service
sudo systemctl restart asus-traffic-importer.timer
```

The installer preserves an existing `/etc/default/asus-router-monitoring`. See [Troubleshooting](troubleshooting.md) before deleting state or reimporting history.

Remove only the custom collectors while preserving configuration, device aliases, and importer state:

```bash
sudo ./scripts/uninstall-host-components.sh --confirm
```

Use `--purge-config` or `--purge-state` only when those files should also be permanently removed. SNMP Exporter, Blackbox Exporter, VictoriaMetrics, and Grafana are intentionally outside this uninstaller's scope.
