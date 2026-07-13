# 采集字段清单（pg_stat_statements）

| 字段 | 含义 | 备注 |
|------|------|------|
| `queryid` | 规范化 SQL 的唯一标识 | 两次快照关联的主键 |
| `query` | 规范化后的 SQL 文本 | 展示时截取前 500 字符；参数以 `$1`、`$2` 占位 |
| `calls` | 执行次数 | 累计值，差值模式需做减法 |
| `total_exec_time` | 总执行时间（毫秒） | 不含计划时间（PG13+ 与 total_plan_time 分离） |
| `mean_exec_time` | 平均执行时间 | = `total_exec_time / calls`，需在 calls>0 时计算 |
| `rows` | 返回/影响的总行数 | 累计值 |
| `shared_blks_hit` | 共享缓冲区命中块数 | 用于计算缓存命中率 |
| `shared_blks_read` | 共享缓冲区磁盘读取块数 | 越高说明缓存命中率越低 |
| `wal_bytes` | 生成的 WAL 字节数 | PG13+ 提供；识别高频写入/DML |
| `total_plan_time` | 总计划时间（毫秒） | 仅 PG13+；13 以下版本跳过 |
| `mean_plan_time` | 平均计划时间 | = `total_plan_time / calls` |
| `userid` → `username` | 执行该 SQL 的用户 | 关联 `pg_authid`/`pg_user` 转换为可读名 |

## 缓存命中率计算

```
cache_hit_ratio = shared_blks_hit / (shared_blks_hit + shared_blks_read)
```

- 分母为 0（该 SQL 完全未触发共享缓冲区访问，如纯 DDL）时，命中率标记为"不适用"。
- 命中率 < 90% 通常视为需要关注；< 70% 视为明显偏低。

## 版本差异

- PG13 以下：`total_plan_time`、`mean_plan_time`、`wal_bytes` 可能不存在或恒为 0（`wal_bytes` 实际是 PG13 引入）。采集前应先按 `server_version_num` 分支处理，避免 SQL 报错。
- PG13 以下版本报告中应注明："本版本不支持计划时间/WAL字节拆分，相关维度已跳过或使用替代口径"。
