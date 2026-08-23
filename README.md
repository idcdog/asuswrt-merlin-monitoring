# Asuswrt-Merlin Monitoring

English | [简体中文](README.zh-CN.md)

Monitor ASUS routers through SSH, SNMP, and Blackbox Exporter, store the metrics in VictoriaMetrics, and visualize router health, WAN traffic, wireless client quality, and per-device history in Grafana.

The verified baseline is an RT-BE88U running Asuswrt-Merlin 3006.102.8_4. The SSH collector relies on Asuswrt commands and data sources such as `nvram`, `wl`, `conntrack`, and Traffic Analyzer. Run the read-only preflight check before trying an unlisted model.

## Features

- Uptime, firmware, CPU, load, memory, temperatures, and Conntrack capacity
- WAN state, SNMP interface throughput, errors, discards, and utilization
- Wireless client identity, band, RSSI, SNR, PHY rates, retries, and traffic counters
- LAN-only MAC-to-device-name management page
- Hourly per-device Traffic Analyzer history imported into VictoriaMetrics
- HTTP, ICMP, and DNS availability and latency probes
- Summary-first Grafana dashboard and VictoriaMetrics scrape configuration
- systemd services and timer examples

## Architecture

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

See [Architecture and data flow](docs/architecture.en.md) for the detailed boundaries and collection paths.

## Grafana preview

The screenshots come from a working installation. Device names, IP addresses, MAC addresses, and public addresses are irreversibly redacted.

![Router network overview](docs/images/01-overview-redacted.png)

![Internet quality](docs/images/04-internet-quality.png)

![Wireless quality](docs/images/05-wireless-quality-redacted.png)

![Historical traffic](docs/images/07-history-redacted.png)

See the [complete screenshot gallery](docs/screenshots.en.md) for every dashboard section.

## Quick start

1. Enable SSH, SNMP, and Traffic Analyzer on the router.
2. Create the host configuration and enter the real router address:

   ```bash
   sudo cp config/asus-router-monitoring.env.example /etc/default/asus-router-monitoring
   sudo editor /etc/default/asus-router-monitoring
   ```

3. Configure SSH public-key authentication and accept the router host key as the service user:

   ```bash
   sudo ssh root@192.168.1.1 -p 2222 true
   ```

4. Run the read-only preflight check before installing anything:

   ```bash
   sudo ./scripts/preflight.sh
   ```

5. Install the custom collectors and systemd units:

   ```bash
   sudo ./scripts/install-host-components.sh
   sudo systemctl enable --now asus-wifi-exporter.service
   sudo systemctl enable --now asus-traffic-importer.timer
   ```

6. Follow the [installation guide](docs/installation.en.md) to configure SNMP Exporter, Blackbox Exporter, VictoriaMetrics, and Grafana.

## Documentation

- [Installation](docs/installation.en.md)
- [Compatibility matrix](docs/compatibility.md)
- [Known limitations](docs/limitations.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Metric reference](docs/metrics.en.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Security summary

- Never commit the SNMP community, SSH private keys, or a real device-name mapping.
- The unauthenticated device-name manager binds to `127.0.0.1` by default.
- SSH collection is read-only and does not run `nvram set`, apply configuration, or reboot the router.
- Private addresses and `eth1` in the examples are placeholders, not required values.

Read [SECURITY.md](SECURITY.md) and [Known limitations](docs/limitations.md) before exposing any component beyond a trusted LAN.

## License

[MIT](LICENSE)

This is an independent community project and is not affiliated with or endorsed by ASUS, Asuswrt-Merlin, Grafana Labs, VictoriaMetrics, or Prometheus.
