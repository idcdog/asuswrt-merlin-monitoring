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

The current exporter also reports stale when the router returns no associated wireless stations. See [Known limitations](limitations.md).

## SNMP returns no data

Check the exporter and perform one probe without printing the community:

```bash
curl -fsS http://127.0.0.1:9116/-/healthy
curl -fsS 'http://127.0.0.1:9116/snmp?target=192.168.1.1&module=if_mib&auth=asus_router_v2' | head
```

Verify UDP 161 is allowed from the monitoring host, the auth name matches both files, and the private `asus-auth.yml` contains the real community.

## WAN panels show zero or no data

The dashboard normally discovers the active WAN interface from `asus_router_wan_info`. Run preflight to confirm that the same name exists in SNMP. If the variable is empty or the two names differ, query all interfaces in Grafana Explore:

```promql
ifHCInOctets{instance="192.168.1.1"}
```

Select the interface carrying Internet traffic as the temporary `wan_if` value. Confirm that the `instance` label equals the dashboard `router_ip` variable.

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

The provisioned datasource UID must remain `victoriametrics`. Check the dashboard variables `router_ip` and `wan_if`, then confirm that VictoriaMetrics is using the expected scrape file.

## Blackbox ICMP fails

Inspect the unit and logs:

```bash
sudo systemctl status blackbox-exporter.service --no-pager
sudo journalctl -u blackbox-exporter.service -n 100 --no-pager
```

The provided unit grants `CAP_NET_RAW`. Distribution packages may use another user, binary path, or capability setup.

## Device names changed only for new data

This is expected. Prometheus labels are part of time-series identity, so historical samples retain the old `name`. Query history by `mac` and use the latest name mapping for presentation where possible.
