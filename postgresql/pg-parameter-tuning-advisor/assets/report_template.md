# PostgreSQL 参数调优建议报告

## 实例概览
- 版本：{{server_version}}
- 连接信息：host={{host}} port={{port}} dbname={{dbname}} user={{user}}（密码已脱敏）
- 采集时间：{{collected_at}}
- 采集范围：{{scope}}  <!-- 例如：数据库侧 + 操作系统侧（同机执行） / 数据库侧 + 操作系统侧（SSH 远程） / 仅数据库侧（无主机访问权限） -->

## 硬件与环境画像
- CPU：{{cpu_summary}}
- 内存：{{memory_summary}}
- 存储：{{storage_summary}}
- 网络：{{network_summary}}

> 若某项因权限未采集，请在此处明确写「未采集：原因」，不要留空造成误解。

## Workload 特征判断
{{workload_type}}（判断依据：{{workload_evidence}}）

## 关键瓶颈（按影响程度排序）
1. {{bottleneck_1}}（证据：{{evidence_1}}）
2. {{bottleneck_2}}（证据：{{evidence_2}}）

## 参数调整建议

| 参数名 | 调整前 | 建议调整后 | 调整原因 | 预期收益 | 生效方式 | 风险提示 |
|--------|--------|-----------|----------|----------|----------|----------|
| {{param}} | {{before}} | {{after}} | {{reason}} | {{benefit}} | {{reload_or_restart}} | {{risk}} |

## 未纳入本次调整的观察项
- {{other_observation_1}}
- {{other_observation_2}}

## 数据来源与置信度说明
- {{confidence_note}}

---
本报告仅提供参数调整建议，不包含可直接执行的变更脚本；请在测试环境验证后再应用到生产，并遵循贵司变更管理流程。
