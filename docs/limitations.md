# Known limitations

[简体中文](limitations.zh-CN.md)

- **Wireless traffic is not Internet-only traffic.** Live station counters describe frames between the AP and client and may include LAN traffic, retransmission behavior, and counter resets.
- **Traffic Analyzer history is hourly.** The importer only reads completed hours and the router retains a firmware-dependent amount of history.
- **Renaming does not rewrite history.** A new display name creates new label combinations. Aggregate historical queries by `mac`.
- **Zero associated stations is currently treated as a failed collection.** This protects against silently publishing incomplete `wl` output, but an intentionally empty WLAN appears stale.
- **Radio summary mapping is dual-band specific.** The current remote script summarizes `wl0` as 2.4 GHz and `wl1` as 5 GHz. Tri-band and 6 GHz layouts need model-specific work.
- **WAN summary is single-unit.** It reads the NVRAM-selected active WAN unit and does not model dual-WAN balancing or failover paths in detail.
- **SNMP interface names vary.** `eth1` is only an example; select the actual WAN interface in Grafana.
- **The device-name manager has no authentication or TLS.** It is designed for loopback or a trusted LAN only.
- **Collectors run as host root in the provided units.** This matches the original deployment's SSH key ownership. A dedicated service account is preferable when its SSH key, state directories, and permissions are configured explicitly.
- **No configuration migration framework exists yet.** Review example configuration and release notes before upgrading.
- **No automatic deletion or retention management is performed.** VictoriaMetrics retention and Grafana user management remain operator responsibilities.
