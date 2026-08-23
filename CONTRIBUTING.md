# Contributing

[简体中文说明](README.zh-CN.md)

欢迎提交兼容性修复、指标改进、Grafana 面板优化和文档补充。

提交前请：

1. 不要包含真实 SNMP community、SSH 私钥、设备 MAC、设备别名、公网 IP 或私人域名。
2. 运行 `./scripts/validate.sh`。
3. 对路由器命令保持只读；任何会修改 NVRAM、无线配置、防火墙或触发重启的命令不应加入采集脚本。
4. 新增指标时说明来源、单位、标签和采集频率，并控制标签基数。
5. 修改仪表盘时保留摘要优先的布局，并确保 PromQL 使用现有变量。

报告型号兼容性时，请提供固件分支、命令是否存在及脱敏后的输出结构，不要附带密钥或真实客户端信息。

## Development workflow

1. Fork or branch from `main`.
2. Keep changes focused and avoid unrelated formatting or refactors.
3. Add deterministic tests for parser and metric changes.
4. Run `./scripts/validate.sh`.
5. Complete the pull request checklist with a redacted tested environment.

Do not add router commands that modify NVRAM, firewall state, wireless settings, installed packages, or reboot state. A new privileged or network-facing behavior must be explicit, documented, and disabled by default.

Compatibility reports should use the issue form and include read-only preflight results. Support is community-based with no guaranteed response time; see [SUPPORT.md](SUPPORT.md).
