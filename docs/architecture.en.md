# Architecture and data flow

[简体中文](architecture.md)

The default architecture uses SSH for router state, active-WAN interface counters, and hourly traffic history. SNMP is an optional advanced path for operators who need IF-MIB data for every interface.

```text
                         ┌─────────────────────────────┐
                         │ Asuswrt / Asuswrt-Merlin    │
                         │ SSH commands       SQLite│
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

## Live SSH collection

`asus-wifi-exporter` opens one SSH session per collection interval and runs a read-only shell script. It parses:

- `/proc/uptime`, `/proc/loadavg`, `/proc/stat`, and `/proc/meminfo`
- Conntrack entry count, limit, and active TCP/UDP sessions
- Model, firmware, and WAN state returned by `nvram get`
- Active-WAN byte, packet, error, drop, state, and speed data from `/sys/class/net`
- Radio, channel, and associated-station data returned by Broadcom `wl`
- DHCP leases, ARP, and `/jffs/nmp_cl_json.js` device identity data

Prometheus metrics are served on `:9101/metrics`. `up{job="asus_wifi_clients"}` only proves that the HTTP endpoint was scraped; `asus_wifi_exporter_up` confirms that the most recent usable SSH collection remains fresh.

The same process can serve an unauthenticated device-name manager on `:9102`. Aliases are stored locally by MAC address. New live samples use an updated name after the next collection, but old VictoriaMetrics series are not rewritten.

## Optional SNMP interface counters

The default dashboard does not require SNMP. Operators who need standard IF-MIB data for every router interface can enable the optional scrape snippet and `snmp_exporter`. Authentication is stored in a separate `asus-auth.yml` that must never be committed.

## Traffic Analyzer import

A systemd timer runs `asus-traffic-importer`. It uses the router's `sqlite3` command over SSH to read completed hourly buckets, writes TX/RX samples to the VictoriaMetrics Prometheus import API, and stores the latest imported timestamp locally.

The first non-dry run imports all complete hourly rows still present in the router database. Subsequent runs resume from the local state file.

## Internet and component probes

Blackbox Exporter performs HTTPS, ICMP, and DNS probes. The example configuration also checks VictoriaMetrics, Grafana, and the device-name manager. A single public endpoint can produce target-specific false alarms, so production installations may add a second independent target.

## Permission boundaries

- Router commands are read-only and do not apply configuration or reboot the router.
- OpenSSH host-key verification remains enabled.
- The device-name API only writes the host alias file, not router configuration.
- Grafana, VictoriaMetrics, and exporters communicate over loopback by default.
