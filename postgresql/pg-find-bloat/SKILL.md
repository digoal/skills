---
name: pg-find-bloat
description: "PostgreSQL 表/索引膨胀（bloat）诊断专家技能。给定一个 PostgreSQL 实例的连接串（host/port/user/password 或 DSN），自动列出该实例下所有数据库，逐库分析每张表和每个索引的膨胀大小与膨胀比例，按经验阈值判定危害程度，按膨胀大小/比例倒序排序并按数据库分组输出结果，最后给出总结与后续处置建议。触发条件：用户提到\"表膨胀\"、\"索引膨胀\"、\"bloat\"、\"膨胀检测\"、\"膨胀分析\"、\"pg_bloat\"、\"数据库臃肿\"、\"表越来越大\"、\"VACUUM 效果不好\"、\"磁盘空间异常增长\"、\"帮我看看这个库有没有膨胀\"、\"哪些表需要 VACUUM FULL / pg_repack\"，或提供了 PostgreSQL 连接串并希望排查空间膨胀问题。即使用户只说\"帮我查一下这个库胖不胖\"或给出连接信息并问\"这个实例正常吗\"，只要意图涉及表/索引空间膨胀，也应使用本 skill。"
tags: [PostgreSQL, 索引膨胀, 表膨胀]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# PostgreSQL 表/索引膨胀诊断技能（pg-find-bloat）

以资深 PostgreSQL DBA 的视角，对一个 PostgreSQL 实例做全库级别的表/索引膨胀（bloat）巡检，定位真正值得处理的膨胀对象，避免"一刀切"式的无差别 VACUUM FULL / REINDEX。

## 前置要求

- 环境中可执行 `psql`（PostgreSQL 客户端）。若未安装，按发行版自动检测安装：
  ```bash
  command -v psql || (command -v dnf &>/dev/null && dnf install -y postgresql) || (command -v yum &>/dev/null && yum install -y postgresql) || (command -v apt-get &>/dev/null && apt-get install -y postgresql-client)
  ```
- 用户提供以下之一：
  - 完整 DSN，如 `postgresql://user:password@host:5432/postgres`
  - 或 host/port/user/password 分开提供
- 连接账号至少具备目标数据库的 **CONNECT + SELECT on pg_catalog** 权限（只读）。若具备 superuser 权限，可临时创建 `pgstattuple` 扩展以获得精确膨胀值；否则自动降级为估算公式，全程不要求写权限。
- 全程只读诊断，**不会**自动执行 VACUUM FULL / REINDEX / pg_repack 等修复操作，只输出建议。

## 工作流程

### Step 1：解析连接信息并测试连通性

```bash
psql "$DSN" -Atqc "select version();"
```

- 若连接失败，检查报错中的 `x-deny-reason` 或 psql 报错信息（网络不通/认证失败/pg_hba.conf 限制），如实告知用户，不要猜测修复。
- 记录 PostgreSQL 主版本号（不同版本 `pg_stat_*` 视图字段可能有差异，尤其 9.x 与 13+ 在部分统计列上不同，需要时做兼容处理）。

### Step 2：列出所有数据库

```sql
select datname from pg_database
where datistemplate = false
  and datallowconn = true
order by datname;
```

- 默认排除 `template0`、`template1`。是否包含 `postgres` 库由用户数据决定，默认包含。
- 对每个数据库分别建立连接（`psql "$DSN" -d <dbname>`），逐库执行 Step 3~5。

### Step 3：检测精确膨胀能力（pgstattuple）

```sql
select exists (select 1 from pg_extension where extname = 'pgstattuple') as has_pgstattuple;
```

- 若未安装且当前账号为 superuser（`select usesuper from pg_user where usename = current_user;` 为 true），尝试：
  ```sql
  create extension if not exists pgstattuple;
  ```
- 若无权限安装，或用户明确要求"不要修改实例"，则自动降级到 **估算公式**（见 `scripts/table_bloat_estimate.sql` 和 `scripts/index_bloat_estimate.sql`），并在最终报告中注明"本次数据为估算值，非精确值"。
- 两种模式二选一，脚本见 `scripts/` 目录：
  - 精确模式：`scripts/table_bloat_pgstattuple.sql`、`scripts/index_bloat_pgstattuple.sql`
  - 估算模式：`scripts/table_bloat_estimate.sql`、`scripts/index_bloat_estimate.sql`

### Step 4：逐库采集表膨胀与索引膨胀

对每个数据库执行对应模式的 SQL 脚本，得到每张表/每个索引的：

- `schema_name`、`object_name`、`object_type`（table/index）
- `row_estimate`（估算行数，来自 `pg_stat_user_tables.n_live_tup` 或 `reltuples`）
- `real_size`（实际占用磁盘大小，字节）
- `bloat_size`（膨胀大小，字节）
- `bloat_ratio`（膨胀比例 = bloat_size / real_size，百分比）

注意：

- 表和索引分别计算，不要混算；一张表的膨胀问题不代表其索引也膨胀，反之亦然。
- 排除大小低于 8MB（1024 个 8KB page）的对象——过小的表/索引即使比例很高，膨胀绝对值也无实际意义，会造成噪音干扰。
- 排除 `bloat_size` 为负数或异常值的行（估算公式在统计信息过期或表刚 ANALYZE 后可能出现负值，代表当前无明显膨胀，直接按 0 处理，不纳入危害判定）。

### Step 5：应用危害阈值（经验值，可被用户覆盖）

综合业界常见运维经验（膨胀绝对大小 + 膨胀比例双维度判定，避免只看比例导致"小表大惊小怪"、只看绝对值导致"大表膨胀 5% 被忽略"）：

| 危害程度 | 判定条件（满足任一即可） | 典型含义 |
|---------|--------------------------|----------|
| 🔴 高危 | `bloat_ratio ≥ 40%` 或 `bloat_size ≥ 5GB` | 严重浪费磁盘/IO，通常伴随查询变慢、顺序扫描成本上升，建议尽快处理 |
| 🟡 中危 | `20% ≤ bloat_ratio < 40%` 或 `1GB ≤ bloat_size < 5GB` | 需要纳入观察名单，安排在业务低峰处理 |
| 🟢 低危/正常 | `bloat_ratio < 20%` 且 `bloat_size < 1GB` | 属正常范围，PostgreSQL MVCC 机制下的正常空间放大，通常无需干预 |

- 以上阈值是通用经验值，不同业务对空间/IO敏感度不同。若用户明确给出自己的阈值（如"膨胀比例超过 30% 才算"），以用户阈值为准，并在报告中注明使用的是自定义阈值还是默认经验阈值。
- 索引膨胀通常比表膨胀更值得关注比例本身（索引结构对随机更新更敏感），但阈值判定逻辑保持一致，不单独放宽。

### Step 6：排序与分组

- 只保留 危害程度为 🔴 高危 或 🟡 中危 的对象（即 `bloat_ratio` 或 `bloat_size` 超过阈值下限的行），🟢 正常对象不进入明细列表，仅计入总结统计。
- 先按 `database` 分组，组内按 `bloat_size` 降序排序（膨胀绝对大小优先，因为它直接对应可回收的磁盘空间），`bloat_size` 相同则按 `bloat_ratio` 降序。

### Step 7：输出格式

对每个数据库输出一个 Markdown 表格，表头固定为：

```
| 表名/索引名 | 类型 | 记录数 | 实际大小 | 膨胀大小 | 膨胀比例 | 危害程度 | 建议 |
```

- "表名/索引名"格式为 `schema.object_name`，索引额外标注所属表，如 `public.idx_orders_created_at (表: public.orders)`。
- 大小统一用 `pg_size_pretty` 风格展示（如 `2.3 GB`、`512 MB`），同时在旁注保留原始字节数便于用户核对（可放在同一单元格括号内）。
- "建议"列给出具体可执行动作，例如：
  - 表高危 + 无外键/低频访问 → `VACUUM FULL public.xxx;`（需业务窗口，会锁表）或优先推荐 `pg_repack -t public.xxx`（在线重整，无长时间锁）
  - 表中危 → 先 `VACUUM (VERBOSE, ANALYZE) public.xxx;` 观察下次采集是否好转，同时检查 `autovacuum` 参数（`autovacuum_vacuum_scale_factor`、`autovacuum_naptime`）是否过于宽松
  - 索引膨胀（不论高中危）→ 优先 `REINDEX INDEX CONCURRENTLY public.idx_xxx;`（PG 12+ 支持，不阻塞读写），低版本用 `pg_repack --index`
  - 若同一张表的表膨胀和其若干索引均处于高危，建议一并处理（先 `pg_repack -t` 表本身即会重建索引，比逐个 `REINDEX` 更高效）

### Step 8：总结与后续建议

在所有数据库表格之后，输出一段总结，须包含：

1. **总体画像**：本次巡检的数据库数量、检出高危对象数、中危对象数、预计可回收总空间（各库 `bloat_size` 求和）。
2. **根因初判**：结合观察到的模式给出可能原因，例如：
   - 某些库普遍膨胀 → 排查 `autovacuum` 是否被全局关闭或参数过松（`show autovacuum;`、`select * from pg_stat_user_tables where relname='xxx';` 看 `last_autovacuum` 时间）
   - 长事务导致膨胀 → 检查是否存在长时间未提交事务或复制槽阻塞 VACUUM 回收：
     ```sql
     select pid, state, now()-xact_start as duration, query
     from pg_stat_activity
     where state <> 'idle' and xact_start is not null
     order by duration desc limit 20;
     select * from pg_replication_slots;
     ```
   - 高频 UPDATE/DELETE 表未走索引导致大量死元组 → 结合 `pg_stat_user_tables.n_dead_tup` 与 `n_tup_upd/n_tup_del` 交叉验证
3. **后续观察建议**：
   - 对中危对象建议 1~2 周后复查，观察膨胀是否随 autovacuum 自然回落
   - 对存在长事务/复制槽阻塞的实例，建议先解决阻塞根因，再评估是否需要手动整理，否则整理后会再次膨胀
   - 建议将本次高危清单纳入定期巡检（如每周/每月跑一次本 skill），跟踪趋势而非只看单次快照
4. **风险提示**：`VACUUM FULL` 与 `REINDEX`（非 CONCURRENTLY 模式）会对表加排他锁，明确提醒用户务必在业务低峰执行，并提前评估锁等待对业务的影响；生产环境优先推荐 `pg_repack` / `REINDEX CONCURRENTLY` 等在线方案。

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| 统计信息过期 | 估算模式下膨胀比例算出负数或明显失真 | 采集前对目标库执行 `ANALYZE;`（只读性质，不锁表），再重新采集 |
| 无 superuser 权限 | 无法安装 `pgstattuple`，精确模式不可用 | 自动降级为估算模式，并在报告中明确标注"估算值" |
| 分区表 | 父表本身 `reltuples`/`relpages` 通常为 0，容易被误判为"无膨胀" | 对分区表遍历其所有子分区（`pg_inherits`），按子分区分别计算，父表本身跳过判定 |
| 超大库/超多表导致采集耗时长 | 全库全表扫描 `pgstattuple` 在大表上代价高 | 精确模式对 >10GB 的大表先用估算公式粗筛，仅对进入候选名单的表再跑 `pgstattuple` 精确核实 |
| 复制槽/长事务阻塞 VACUUM | 表怎么整理都很快重新膨胀 | 先用 Step 8 中的 SQL 排查长事务与复制槽，根因不解决，整理只是治标 |
| 连接串含明文密码 | 日志/报告中泄露密码 | 输出报告和过程日志中一律对连接串做脱敏处理，只展示 host/port/dbname，不回显 password |

## 注意事项

- **只读原则**：本技能本身不执行任何写操作（除非用户明确同意临时创建 `pgstattuple` 扩展），不会代替用户执行 `VACUUM FULL`/`REINDEX`/`pg_repack`，所有修复动作均以"建议"形式呈现，交由用户决策执行时机。
- **密码脱敏**：连接串中的密码信息不得出现在最终输出的报告、日志或任何持久化文件中。
- **版本兼容**：PostgreSQL 9.x 与 13+ 在 `pg_stat_user_tables`、`pg_stat_user_indexes` 部分字段上存在差异，执行前先确认版本号，必要时调整脚本字段。
- **大小阈值可调**：Step 5 中的经验阈值是通用默认值，如用户对存储成本/IO 更敏感（如云盘按量付费），应主动询问是否需要调低阈值。
- **排他锁风险**：任何"建议"中涉及非 CONCURRENTLY 的整理操作，必须在建议文本中同时标注锁风险与推荐执行时段。
