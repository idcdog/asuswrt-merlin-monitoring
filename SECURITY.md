# Security

## Sensitive files

Never commit these files or their equivalents:

- SSH private keys
- SNMP community strings
- Grafana API tokens or passwords
- `device-names.json` containing real MAC addresses and device names
- VictoriaMetrics data or importer state

The repository `.gitignore` excludes common local copies, but review every commit before publishing.

## Device-name manager

The management UI intentionally has no authentication. It can change the local MAC-to-name mapping and can reveal device MAC, IP, vendor and online state.

Its default bind address is `127.0.0.1`. Only bind it to a LAN address when every client on that network is trusted. For broader access, place it behind an authenticated reverse proxy.

## SSH host verification

The exporter uses the system OpenSSH client and does not disable host-key checking. Populate the service user's `known_hosts` before enabling the service. Investigate host-key changes instead of automatically accepting them.

## Reporting a vulnerability

Open a [private GitHub security advisory](https://github.com/idcdog/asuswrt-merlin-monitoring/security/advisories/new) for vulnerabilities. Do not publish credentials, private network inventories or real device identifiers in a public issue.

Include the affected project version, component, impact, reproduction conditions, and a redacted proof of concept. The initial supported line is `0.1.x`; security fixes are released from the latest maintained version rather than backported to unpublished versions.
