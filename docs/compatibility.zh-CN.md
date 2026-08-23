# 兼容性矩阵

[English](compatibility.md)

## 已验证环境

| 层级 | 已验证基线 | 状态 |
|---|---|---|
| 路由器 | ASUS RT-BE88U | 已支持 |
| 固件 | Asuswrt-Merlin 3006.102.8_4 | 已支持 |
| 无线接口 | `wl0 wl1`，动态识别为 2.4 GHz 和 5 GHz | 已支持 |
| 监控服务器 | CentOS Stream 10，x86_64 | 已支持 |
| Python | 3.12.13；代码最低要求 3.10 | 已支持 |
| VictoriaMetrics | single-node 1.125.1 | 已支持 |
| Grafana | 12.4.3 | 已支持 |
| SNMP Exporter | 0.30.1，官方 `if_mib` | 已支持 |
| Blackbox Exporter | 0.28.0 | 已支持 |

“已支持”表示完整链路已在真实环境验证，不代表厂商支持承诺。

## 预期兼容性

标准 SNMP `IF-MIB` 通常可用于更多开启 SNMP 的华硕型号，但接口名和 WAN 映射会不同。SSH 采集更依赖具体平台，因为它使用 Broadcom `wl`、Asuswrt NVRAM、Linux procfs 路径和 Traffic Analyzer 内部数据库。

| 路由器特征 | 预期结果 |
|---|---|
| `wl_ifnames` 中列出的 Broadcom 射频 | 动态发现，已实现 2.4/5/6 GHz 解析 |
| 三频或 6 GHz 射频 | 预期可用，但仍需要真实型号兼容性报告 |
| MediaTek 或 Qualcomm 无线工具 | 当前不支持无线 SSH 采集 |
| 没有 Traffic Analyzer 或 `sqlite3` | 实时指标可用，小时历史不可用 |
| Conntrack 命令或路径不同 | 需适配后才能采集完整系统信息 |
| 双 WAN/负载均衡 | 只汇总 NVRAM 当前活动 WAN 单元 |
| 命令相同的华硕原厂固件 | 可能可用，但尚未验证 |

## 提交兼容性报告前

运行只读前置检查、实时单次采集和历史 dry-run，然后使用兼容性 Issue 模板提交型号、固件、监控服务器版本和脱敏结果。不要上传 SNMP community、SSH 私钥、真实 MAC、设备名称、公网 IP 或完整内网清单。
