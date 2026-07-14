#!/usr/bin/env python3
"""
09_generate_report.py
用途：读取部署过程中收集的事实（JSON），套用 references/report-template.md 模板，
      对密码等敏感字段自动脱敏，生成最终的 Markdown 部署报告。

用法：
  python3 09_generate_report.py <facts.json> <output.md>

facts.json 示例结构（字段可按需扩展，缺失字段会在报告中显示"待补充"）：
{
  "cluster_name": "pg_ha_demo",
  "pg_version": "16",
  "ha_software": "patroni",
  "nodes": [
    {"name": "node1", "role": "primary", "ip": "10.0.0.1", "port": 5432},
    {"name": "node2", "role": "standby", "ip": "10.0.0.2", "port": 5432}
  ],
  "vip_or_haproxy": "10.0.0.100:5432",
  "superuser_password": "S3cretPassw0rd!",
  "replicator_password": "R3plPassw0rd!",
  "installed_versions": {"postgresql": "16.4", "patroni": "3.3.0"},
  "non_default_params": {"shared_buffers": "4096MB", "wal_level": "replica"},
  "switchover_result": "耗时 8s，新主可读写，旧主正常追增",
  "failover_result": "耗时 15s 完成自动切换，原主重新加入后追增正常",
  "known_risks": ["异步复制存在极小概率数据丢失", "仅 2 节点 etcd，无第三方仲裁"],
  "next_steps": ["定期执行 base backup", "监控复制延迟并设置告警阈值"]
}
"""

import json
import sys


def mask_password(pw: str) -> str:
    if not pw:
        return "（未提供）"
    if len(pw) <= 2:
        return "*" * len(pw)
    return pw[0] + "*" * (len(pw) - 2) + pw[-1]


def render(facts: dict) -> str:
    nodes = facts.get("nodes", [])
    node_lines = "\n".join(
        f"| {n.get('name','?')} | {n.get('role','?')} | {n.get('ip','?')} | {n.get('port','?')} |"
        for n in nodes
    ) or "| （无节点信息） | | | |"

    versions = facts.get("installed_versions", {})
    version_lines = "\n".join(f"- {k}: {v}" for k, v in versions.items()) or "- （待补充）"

    params = facts.get("non_default_params", {})
    param_lines = "\n".join(f"| {k} | {v} |" for k, v in params.items()) or "| （无非默认参数） | |"

    risks = facts.get("known_risks", [])
    risk_lines = "\n".join(f"- {r}" for r in risks) or "- （暂无已知风险记录）"

    next_steps = facts.get("next_steps", [])
    next_lines = "\n".join(f"- {s}" for s in next_steps) or "- （暂无）"

    report = f"""# PostgreSQL 高可用集群部署报告

## 1. 集群架构概述

- 集群名称：{facts.get('cluster_name', '（待补充）')}
- PostgreSQL 版本：{facts.get('pg_version', '（待补充）')}
- HA 软件：{facts.get('ha_software', '（待补充）')}

| 节点名 | 角色 | IP | 端口 |
|---|---|---|---|
{node_lines}

```mermaid
graph LR
  Client[应用] --> VIP[VIP/HAProxy: {facts.get('vip_or_haproxy', '未配置')}]
  VIP --> Primary[(Primary)]
  Primary -. 流复制 .-> Standby[(Standby)]
```

## 2. 连接信息

- VIP / HAProxy 地址：{facts.get('vip_or_haproxy', '（未配置）')}
- 超级用户 postgres 密码（已脱敏）：{mask_password(facts.get('superuser_password',''))}
- 复制用户 replicator 密码（已脱敏）：{mask_password(facts.get('replicator_password',''))}
- 应用连接串示例：`postgresql://appuser:<password>@{facts.get('vip_or_haproxy','<vip>')}/appdb?sslmode=prefer`

**⚠️ 请立即修改上述初始密码，并将正式密码保存至企业密钥管理系统（如 Vault），不要以明文形式长期留存本报告。**

## 3. 安装软件版本清单

{version_lines}

## 4. 关键配置摘要（非默认参数）

| 参数 | 值 |
|---|---|
{param_lines}

## 5. 切换测试结果

- **Switchover（正常手动切换）**：{facts.get('switchover_result', '（待补充）')}
- **Failover（模拟故障切换）**：{facts.get('failover_result', '（待补充）')}

## 6. 已知局限与建议

{risk_lines}

## 7. 日常运维指引

{next_lines}

---
*本报告由 pg-deploy-cluster 技能自动生成，敏感信息已脱敏处理。*
"""
    return report


def main():
    if len(sys.argv) != 3:
        print(f"用法: {sys.argv[0]} <facts.json> <output.md>", file=sys.stderr)
        sys.exit(1)

    facts_path, out_path = sys.argv[1], sys.argv[2]
    with open(facts_path, "r", encoding="utf-8") as f:
        facts = json.load(f)

    report = render(facts)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已生成: {out_path}")


if __name__ == "__main__":
    main()
