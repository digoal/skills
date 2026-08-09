# 采集字段清单（sys_stat_statements，KES V9R1C10 / 扩展 1.11）

> 表位于 `public.sys_stat_statements`（不是 `pg_stat_statements`）。本清单基于 KES V9R1C10 + sys_stat_statements 1.11 实测的 35 列。
> **字段可用性必须用 `information_schema.columns` 动态探测**，不要按 `server_version_num`（R1C10 为 120001，但字段集是 PG14+ 的）。

| 字段 | 含义 | 备注 |
|------|------|------|
| `queryid` | 规范化 SQL 的唯一标识 | 两次快照关联的主键；可能为 NULL（工具语句等）需过滤 |
| `query` | 规范化后的 SQL 文本 | 展示时截取前 500 字符；参数以 `$1`、`$2` 占位 |
| `userid` → `username` | 执行该 SQL 的用户 | 关联 `pg_authid`/`pg_user` 转换为可读名 |
| `parses` / `plans` / `calls` | 解析/规划/执行次数 | 均为累计值，差值模式需做减法 |
| `total_parse_time` / `total_plan_time` / `total_exec_time` | 总解析/规划/执行时间（毫秒） | KES 的 sys_stat_statements 自带，无需按版本裁剪 |
| `min/max/mean/stddev_*_time` | 最小/最大/平均/标准差耗时 | 差值模式推荐用 `delta_total / delta_calls` 重算均值 |
| `rows` | 返回/影响的总行数 | 累计值 |
| `shared_blks_hit` / `shared_blks_read` | 共享缓冲区命中/磁盘读取块数 | 计算缓存命中率 |
| `shared_blks_dirtied` / `shared_blks_written` | 脏块数 / 落盘块数 | **写放大维度主用字段**（KES 无 wal_bytes） |
| `local_blks_*` / `temp_blks_read` / `temp_blks_written` | 本地缓冲区 / 临时文件读写块数 | temp 高说明 work_mem 不足产生磁盘排序/哈希 |
| `blk_read_time` / `blk_write_time` | 读写 IO 耗时（毫秒） | 仅 `track_io_timing=on` 时有值，否则恒为 0 |
| ~~`wal_bytes` / `wal_records`~~ | 生成 WAL 字节数 | **KES V9R1C10 不存在**，不要引用；写压力用 shared_blks_dirtied 近似 |

## 缓存命中率计算

```
cache_hit_ratio = shared_blks_hit / (shared_blks_hit + shared_blks_read)
```

- 分母为 0（该 SQL 完全未触发共享缓冲区访问，如纯 DDL）时，命中率标记为「不适用」。
- 命中率 < 90% 通常视为需要关注；< 70% 视为明显偏低。

## 版本差异与动态探测

- KES R1C10 的 `server_version_num=120001`（PG12 兼容），但 `sys_stat_statements` 1.11 采用 PG14+ 字段集（含 `total_plan_time`/`mean_plan_time`/`blk_read_time`/`temp_blks_*`），**不能**沿用 PG「版本 < 13 无 total_plan_time」的逻辑。
- 未来 KES 版本若新增 `wal_bytes` 等字段，`snapshot_diff.py` 会自动探测并纳入差值；报告中按实际可用字段说明维度覆盖范围。
- `sys_stat_statements` 视图默认排除当前会话自身语句；如需包含，可用函数 `sys_stat_statements_all()`（返回同样字段结构）。

## queryid 归一化差异（KES 实测行为，重要）

同一逻辑 SQL 可能因字面量书写方式不同（如 `WHERE aid = 123` 直接写常量 vs 走参数绑定）而生成**不同的 queryid**，导致执行次数/耗时被拆分到多个条目。实测例：pgbench 与 psql 手工执行的 `UPDATE pgbench_accounts SET abalance = abalance + $1 WHERE aid = $2` 出现了两个 queryid。

处理建议：
- 做差值聚合时，可先按 `query` 文本归一化（去掉 `$n` 占位差异后的标准文本）分组，再把同一文本下多个 queryid 的增量求和，避免低估 TOP SQL。
- 报告「执行频率/总耗时」口径时注明是否做了文本级合并。

## 相关函数与参数（KES 特有）

- 重置：`public.sys_stat_statements_reset()`（清空全局统计，高危，需授权）
- 重置时间：`sys_stat_statements_get_reset_time()`（替代 PG 的 pg_stat_statements_info 视图）
- 参数：`sys_stat_statements.track`（默认 `top`）、`.max`（默认 5000）、`.save`、`track_parse`、`track_plan`、`track_utility`
