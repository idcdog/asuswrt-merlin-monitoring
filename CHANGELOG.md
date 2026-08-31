# Changelog

All notable project changes are documented here. The project follows Semantic Versioning after the initial public release.

## [Unreleased]

### Changed

- Treat a successful empty wireless association list as zero clients while rejecting command errors and truncated output
- Discover Broadcom radios and 2.4/5/6 GHz band mappings dynamically from the router
- Collect active-WAN byte, packet, error, drop, speed, and operational-state metrics over SSH
- Make SNMP an optional extension and remove it from the default scrape configuration and preflight checks
- Prefer SSH WAN metrics in Grafana while preserving read-only fallback queries for previously stored SNMP history
- Discover the Grafana WAN interface from `asus_router_wan_info` and verify its sysfs counters during preflight
- Preserve the original `asus-wifi-clients` Grafana dashboard UID so upgrades update existing URLs instead of creating a duplicate dashboard
- Add today-so-far WAN download/upload totals and an estimated 30-day daily WAN traffic chart
- Add sanitized full, zero-client, command-error, malformed-output, and 6 GHz regression fixtures

## [0.1.0] - 2026-08-23

### Added

- SSH exporter for router health, WAN state, radio state, and associated wireless clients
- LAN-only device-name manager backed by a MAC-to-name JSON mapping
- Traffic Analyzer hourly history importer for VictoriaMetrics
- SNMP and Blackbox Exporter example configuration
- Summary-first Grafana dashboard with redacted screenshots
- systemd services and timer examples
- English and Simplified Chinese project documentation
- Read-only preflight diagnostics, conservative custom-component uninstall, repository validation, and unit tests
- Security, compatibility, limitations, troubleshooting, and contribution guidance

[Unreleased]: https://github.com/idcdog/asuswrt-merlin-monitoring/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/idcdog/asuswrt-merlin-monitoring/releases/tag/v0.1.0
