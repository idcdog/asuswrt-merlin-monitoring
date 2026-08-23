# Known limitations

[简体中文](limitations.zh-CN.md)

- **Wireless traffic is not Internet-only traffic.** Live station counters describe frames between the AP and client and may include LAN traffic, retransmission behavior, and counter resets.
- **Traffic Analyzer history is hourly.** The importer only reads completed hours and the router retains a firmware-dependent amount of history.
- **Renaming does not rewrite history.** A new display name creates new label combinations. Aggregate historical queries by `mac`.
- **Wireless discovery still requires Broadcom `wl`.** Base radios are discovered from `wl_ifnames` and 2.4/5/6 GHz bands are detected dynamically, but MediaTek and Qualcomm tools remain unsupported.
- **A partial wireless command failure rejects the collection.** A valid empty `assoclist` publishes zero stations; command errors, missing status markers, and truncated station blocks preserve the last known-good snapshot instead of publishing a misleading partial result.
- **WAN summary is single-unit.** It reads the NVRAM-selected active WAN unit and does not model dual-WAN balancing or failover paths in detail.
- **SNMP interface names vary.** Grafana discovers `wan_if` from the SSH-exported active interface. If that name is absent from SNMP `ifName` labels, manual mapping is still required.
- **The device-name manager has no authentication or TLS.** It is designed for loopback or a trusted LAN only.
- **Collectors run as host root in the provided units.** This matches the original deployment's SSH key ownership. A dedicated service account is preferable when its SSH key, state directories, and permissions are configured explicitly.
- **No configuration migration framework exists yet.** Review example configuration and release notes before upgrading.
- **No automatic deletion or retention management is performed.** VictoriaMetrics retention and Grafana user management remain operator responsibilities.
