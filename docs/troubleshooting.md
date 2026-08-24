# Troubleshooting

[简体中文](troubleshooting.zh-CN.md)

Start with the read-only diagnostic:

```bash
sudo ./scripts/preflight.sh
```

## SSH exporter is stale

```bash
sudo systemctl status asus-wifi-exporter.service --no-pager
sudo journalctl -u asus-wifi-exporter.service -n 100 --no-pager
sudo ssh -p 2222 -o BatchMode=yes root@192.168.1.1 true
```

`Host key verification failed` means the service account has not accepted the router key or the key changed. Investigate unexpected changes; do not disable host-key checking.

A router with no associated wireless stations is valid and should publish `asus_wifi_stations 0`. If the exporter is still stale, inspect the log for command errors, missing status markers, or truncated output.

## Optional SNMP returns no data

Skip this section for the default SSH-only deployment. When optional SNMP is enabled, run `preflight.sh --check-snmp` and check the exporter without printing the community:

```bash
curl -fsS http://127.0.0.1:9116/-/healthy
curl -fsS 'http://127.0.0.1:9116/snmp?target=192.168.1.1&module=if_mib&auth=asus_router_v2' | head
```

Verify UDP 161 is allowed from the monitoring host, the auth name matches both files, and the private `asus-auth.yml` contains the real community.

## WAN panels show zero or no data

The dashboard discovers the active WAN interface from `asus_router_wan_info`. Run preflight, then query the SSH counter and its interface label in Grafana Explore:

```promql
asus_router_wan_receive_bytes_total
```

If byte counters exist but speed or utilization is absent, inspect `asus_router_wan_speed_bps`. It is intentionally omitted when a logical WAN interface has no reliable speed.

## Traffic Analyzer has no history

```bash
sudo bash -c 'set -a; source /etc/default/asus-router-monitoring; \
  exec /usr/local/bin/asus-traffic-importer --dry-run'
sudo journalctl -u asus-traffic-importer.service -n 100 --no-pager
```

The current hour is intentionally excluded. A newly enabled analyzer may need more than one hour before a completed bucket exists. Missing `sqlite3`, an unreadable database, or a changed `traffic` schema is reported by preflight.

Do not delete `/var/lib/asus-traffic-importer/state.json` unless you intentionally want to rescan retained history.

## Grafana shows `No data`

Verify:

```bash
curl -fsS http://127.0.0.1:8428/-/healthy
curl -fsS 'http://127.0.0.1:8428/api/v1/query?query=asus_wifi_exporter_up'
```

The provisioned datasource UID must remain `victoriametrics`. Check `wan_if`, then confirm that VictoriaMetrics is using the expected scrape file. `router_ip` only supports the legacy SNMP history fallback.

## Blackbox ICMP fails

Inspect the unit and logs:

```bash
sudo systemctl status blackbox-exporter.service --no-pager
sudo journalctl -u blackbox-exporter.service -n 100 --no-pager
```

The provided unit grants `CAP_NET_RAW`. Distribution packages may use another user, binary path, or capability setup.

## Device names changed only for new data

This is expected. Prometheus labels are part of time-series identity, so historical samples retain the old `name`. Query history by `mac` and use the latest name mapping for presentation where possible.
