# postgresql.conf 参数调优依据

本文档说明 `scripts/03_configure_pg.sh` 中各推荐参数的计算依据，便于人工复核或按实际业务负载调整。

## 内存相关参数

| 参数 | 计算公式 | 依据 |
|---|---|---|
| `shared_buffers` | 总内存 × 25% | PostgreSQL 官方文档建议范围为总内存的 15%-40%，25% 是通用起点；OLTP 高并发场景可适当调高，但不建议超过 40%，避免与 OS page cache 过度竞争 |
| `effective_cache_size` | 总内存 × 60% | 告知优化器可用于缓存的总量估计（含 OS cache），并不实际分配内存，通常设为总内存的 50%-75% |
| `work_mem` | 总内存 × 25% / max_connections | 每个查询排序/哈希操作可用内存；设置过大在高并发下可能导致 OOM，需结合实际并发排序查询数量调整 |
| `maintenance_work_mem` | 总内存 × 5%（上限 2048MB） | 用于 VACUUM、CREATE INDEX 等维护操作，可比 work_mem 更大，但设置过高会在多个维护进程并发时占用过多内存 |

## 复制相关参数

| 参数 | 建议值 | 依据 |
|---|---|---|
| `wal_level` | `replica` | 流复制场景的最低要求级别 |
| `max_wal_senders` | 10 | 预留给从库、pg_basebackup、备份工具等并发连接，2 节点场景通常 5-10 已足够 |
| `max_replication_slots` | 10 | 与 max_wal_senders 配合，避免槽位不足导致从库无法注册 |
| `wal_keep_size` | 1024MB | 在不使用复制槽的情况下，为从库短暂离线提供缓冲；使用复制槽时需额外监控磁盘占用，避免主库 WAL 堆积 |

## 归档相关参数

| 参数 | 建议值 | 依据 |
|---|---|---|
| `archive_mode` | `on` | 开启 WAL 归档，是 PITR（时间点恢复）与部分备份工具的前提 |
| `archive_command` | `test ! -f <dir>/%f && cp %p <dir>/%f` | 使用 `test ! -f` 避免覆盖已存在的归档文件（幂等性），若使用对象存储或专业备份工具（如 pgBackRest、barman），应替换为对应命令 |

## 使用建议

1. 以上均为**通用起点值**，正式生产环境应结合实际业务的连接数、查询模式、IOPS 能力做压测调优，不建议直接照搬。
2. 若节点混合部署了其他内存密集型服务（如应用容器），应相应下调 `shared_buffers` 与 `effective_cache_size` 的比例。
3. 生产环境强烈建议使用 pgBackRest 或 Barman 等专业备份工具替代示例中的简单 `cp` 归档命令，以获得增量备份、压缩、校验等能力。
