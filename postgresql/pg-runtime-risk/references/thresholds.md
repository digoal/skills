# 风险分级阈值参考表

所有阈值均可根据实例实际负载（如高 TPS 实例应适当收紧）与用户明确要求调整，
但默认按下表执行。图标含义统一为：🔴 严重（Critical）/ 🟠 警告（Warning）/
🟡 关注（Notice）/ 🟢 正常（OK）。

## 1. 事务回卷（对应 01_database_xid_age.csv / 01_table_xid_age_top20.csv）

| 等级 | age(datfrozenxid) 范围 | 含义 |
|---|---|---|
| 🔴 严重 | > 20 亿 (2,000,000,000) | 即将触发强制关闭防回卷保护 |
| 🟠 警告 | > 15 亿 (1,500,000,000) | 需立即安排 vacuum freeze |
| 🟡 关注 | > 10 亿 (1,000,000,000) | 检查 autovacuum 是否正常运行 |
| 🟢 正常 | < 10 亿 | 正常范围 |

表级年龄按同一阈值参考；重点标注 TOP 20 中年龄最高、且体积最大的表（vacuum 耗时长）。

## 2. 序列回卷（对应 02_sequence_risk.csv）

| 等级 | remaining_calls（剩余调用次数） |
|---|---|
| 🔴 严重 | < 1,000 |
| 🟠 警告 | < 10,000 |
| 🟡 关注 | < 100,000 |
| 🟢 正常 | ≥ 100,000 或为循环序列（循环序列单独提示"回卷后可能产生主键冲突"） |

额外检查：`data_type` 列若为 `integer`（即 serial/smallserial 语义，最大约 21 亿/32767）
且 remaining_calls 已进入警告及以上，需建议改为 `bigint`（bigserial）。

## 3. 冻结风暴（对应 03_freeze_storm_buckets.csv）

- `age_bucket` 越接近 20（即年龄接近 20 亿上限），风险越高。
- 判定：若 age_bucket ∈ [15,20] 的桶中 `table_count` 之和 > 全部表数量的 50%，
  或其 `total_size_bytes` 之和 > 全部表总大小的 50% → 🔴 冻结风暴高风险
  （大量表将在相近时间点同时触发 autovacuum freeze，引发 IO 争抢）。
- 结合 `00_key_settings.csv` 中 `autovacuum_freeze_max_age` 是否为默认较高值
  （如 2 亿会导致 freeze 过晚集中触发），建议调低（如 10 亿）使 freeze 更均匀分摊。

## 4. 复制延迟

### 4.1 物理复制（对应 04_physical_replication.csv）

| 等级 | replay_lag（时间）或 replay_lag_bytes |
|---|---|
| 🔴 严重 | > 30 分钟 或 > 10GB |
| 🟠 警告 | > 5 分钟 或 > 1GB |
| 🟡 关注 | > 1 分钟 或 > 100MB |
| 🟢 正常 | < 1 分钟 |

### 4.2 逻辑复制槽（对应 04_logical_slots.csv）

| 异常类型 | 判定条件 | 等级 |
|---|---|---|
| 槽未激活 | `active = false` | 🔴 严重（WAL 无限堆积） |
| 推进延迟 | `restart_lag_bytes` > 1GB | 🔴 严重 |
| 未消费 | `confirmed_flush_lag_bytes` > 500MB | 🟠 警告 |
| 无消费进程 | `slot_type='logical'` 且无对应 `pg_stat_replication` 行 | 🔴 严重 |

特别提醒：逻辑复制槽的 WAL 保留不受 `wal_keep_size` 限制。

## 5. WAL 异常（对应 05_archiver_status.csv / 05_wal_dir.csv）

判定前先排除主动配置：
1. `archive_mode = off` → 跳过归档检查，注明"归档未开启"。
2. `archive_command` 为空或为 `/bin/true` 等伪命令 → 跳过，注明"归档命令为空/伪命令"。
3. `archive_timeout > 0` 且距上次归档时间在 timeout 合理范围内 → 注明"可能在等待 archive_timeout，非异常"。

排除以上情况后：

| 等级 | 条件 |
|---|---|
| 🔴 严重 | `last_failed_time` 在最近 1 小时内且 `failed_count > 0`（归档持续失败） |
| 🟠 警告 | `last_archived_time` 距今超过 `archive_timeout * 3`（长时间未成功归档） |

WAL 目录堆积：若 `total_wal_size_bytes` 超过 `max_wal_size * 2`，判定为异常堆积，
按以下优先级排查根因（逐层对照对应文件）：
1. 物理复制延迟大 → 看 04_physical_replication.csv 的 replay_lag_bytes
2. 复制槽推进延迟大 → 看 04_logical_slots.csv 的 restart_lag_bytes
3. 槽未激活 → active = false
4. 槽未消费 → confirmed_flush_lag_bytes 大
5. 归档失败 → 05_archiver_status.csv 的 failed_count 持续增加
6. 以上皆非 → 注明"存在未知原因的 WAL 堆积，需人工排查"

## 6. 集群单点故障（需人工交互补充信息，见 SKILL.md 第六部分）

| 检查项 | 单点风险判定 |
|---|---|
| 同步备库数量为 0 | 🔴 同步备库缺失，主库故障可能导致数据丢失 |
| 无任何备库（04_physical_replication.csv 为空） | 🔴 完全无备库，主库是绝对单点 |
| 无自动故障切换方案（用户回答） | 🟠 故障恢复依赖人工，RTO 不可控 |
| 连接池单节点部署（用户回答） | 🟠 连接池成为新的单点 |
| VIP/负载均衡器单节点（用户回答） | 🟠 流量入口单点 |
| 无有效备份（用户回答 + 归档状态） | 🔴 数据丢失风险 |
| `synchronous_commit` 为 `off`/`local` | 🟡 即使有同步备库也不保证同步 |

## 7. 大对象泄漏（对应 07_large_object_summary.csv）

| 等级 | total_lo_size_bytes |
|---|---|
| 🟠 警告 | > 1GB |
| 🟡 关注 | > 100MB |
| 🟢 正常 | 无或 < 100MB |

无法在 SQL 层面自动判断大对象是否仍被引用（OID 可能存于任意表的 `oid`/`lo` 类型列，
也可能仅被应用层记录）。`07_lo_reference_columns.csv` 列出所有可能存放大对象引用的
候选列，供人工核对；清理前必须由用户二次确认。
