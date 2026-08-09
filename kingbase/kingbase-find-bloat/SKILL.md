---
name: kingbase-find-bloat
description: "KingbaseES（金仓）表/索引膨胀（bloat）诊断专家技能。给定一个 KingbaseES 实例的连接串（host/port/user/password 或 DSN），自动列出该实例下所有数据库，逐库分析每张表和每个索引的膨胀大小与膨胀比例，按经验阈值判定危害程度，按膨胀大小/比例倒序排序并按数据库分组输出结果，最后给出总结与后续处置建议。KingbaseES 默认采用 PG 兼容模式，因此 `pg_catalog` / `pg_stat_*` 视图与 PostgreSQL 一致，但精确膨胀测量需使用 KingbaseES 自带的 `kbstattuple` 扩展（函数 `kbstattuple()` / `kbstatindex()`，字段与 PG 的 pgstattuple 完全一致）而非 PG 的 `pgstattuple`；无该扩展时自动降级为统计信息估算。修复手段包含 KingbaseES 特有的在线压缩扩展 `sys_squeeze` 与命令行工具 `sys_repack`，以及 `REINDEX INDEX CONCURRENTLY`（已实测支持）等在线方案。触发条件：用户提到\"表膨胀\"、\"索引膨胀\"、\"bloat\"、\"膨胀检测\"、\"膨胀分析\"、\"数据库臃肿\"、\"表越来越大\"、\"VACUUM 效果不好\"、\"磁盘空间异常增长\"、\"金仓膨胀\"、\"kingbase bloat\"、\"sys_repack\"、\"sys_squeeze\"、\"帮我看看这个库有没有膨胀\"、\"哪些表需要 VACUUM FULL / sys_repack\"，或提供了 KingbaseES 连接串并希望排查空间膨胀问题。即使用户只说\"帮我查一下这个金仓库胖不胖\"或给出连接信息并问\"这个实例正常吗\"，只要意图涉及表/索引空间膨胀，也应使用本 skill。"
tags: [KingbaseES, 金仓, 表膨胀, 索引膨胀, bloat, kbstattuple, sys_repack, sys_squeeze]
platform: [claude-code, cursor]
author: digoal
version: 1.0.0
---

# KingbaseES 表/索引膨胀诊断技能（kingbase-find-bloat）

以资深 KingbaseES DBA 的视角，对一个 KingbaseES（金仓）实例做全库级别的表/索引膨胀（bloat）巡检，定位真正值得处理的膨胀对象，避免"一刀切"式的无差别 VACUUM FULL / REINDEX。

> **KingbaseES 兼容性说明（已在本 skill 开发环境 KES V9R1C10 实测验证）**：
> - KingbaseES 默认采用 PG 12 兼容模式（`server_version_num` = 120001），`pg_catalog` / `pg_stat_user_tables` / `pg_stat_user_indexes` / `pg_database` / `pg_replication_slots` / `pg_prepared_xacts` 等视图与 PG 一致，可直接复用 PG 的诊断 SQL。
> - 标准 PG 的 `pgstattuple` 扩展**不在** KingbaseES 的默认扩展列表中（实测 `pg_proc` 中无 `pgstattuple`/`pgstatindex` 函数），但 KingbaseES 自带同构扩展 **`kbstattuple`**：`CREATE EXTENSION kbstattuple;` 后提供 `kbstattuple(regclass)` 与 `kbstatindex(regclass)` 函数，**返回字段与 PG 的 pgstattuple/pgstatindex 完全一致**（`dead_tuple_percent`、`free_percent`、`avg_leaf_density` 等），是精确模式的首选工具。
> - KingbaseES 的 `round(double precision, integer)` 重载**不存在**（PG12 默认有），所有 `round(xxx, 1)` 必须显式写为 `round((xxx)::numeric, 1)`，本 skill 的 SQL 脚本已统一处理。
> - `pg_stat_user_indexes` 视图无 `last_idx_scan` 字段（KingbaseES 沿用 PG12 早期视图结构），需要索引使用情况时用 `idx_tup_read`/`idx_tup_fetch` 替代。
> - KingbaseES 系统 schema 包括 `sys_catalog`、`sysaudit`、`sysmac`、`sys_hm` 等（`sys_` 前缀），巡检时必须排除，避免把系统表当成业务表误报。
> - `REINDEX INDEX CONCURRENTLY` 实测可用（不能放在事务块内执行），是 KingbaseES 上在线重建索引的推荐方案。
> - KingbaseES 特有的在线整理手段：`sys_squeeze` 扩展（逻辑解码在线压缩，`squeeze.squeeze_table()`）与 `sys_repack` 命令行工具（无需全程排他锁，类比 pg_repack）。

## 前置要求

- 连接目标 KingbaseES 实例的方式（二选一，均默认只读）：
  - **psql shell**：环境可执行 `psql`（KingbaseES 沿用 PG 客户端协议，标准 PG 的 psql 可直接连接；KingbaseES 自带的 `ksql` 语法与 psql 兼容）。若未安装，按发行版自动检测安装：
    ```bash
    command -v psql || (command -v dnf &>/dev/null && dnf install -y postgresql) || (command -v yum &>/dev/null && yum install -y postgresql) || (command -v apt-get &>/dev/null && apt-get install -y postgresql-client)
    ```
    （若环境已有 KingbaseES 自带 `ksql`，同样可直接使用，`scripts/run_query.sh` 会自动探测 psql/ksql。）
  - **Python SDK**：环境可执行 `python3` 且已安装 `psycopg2`（`pip install psycopg2-binary`）。本 skill 提供 `scripts/kingbase_find_bloat.py`，两条路径产出相同。
- **连接参数解析优先级**（脚本与 skill 一致，用户未提供时才逐级回退）：
  1. 用户显式提供（对话中给出 host/port/user/password/dbname，或命令行参数 / DSN）
  2. PG 兼容环境变量：`PGHOST` / `PGPORT` / `PGDBNAME` / `PGUSER` / `PGPASSWORD`
  3. 内置默认值：`host=127.0.0.1, port=5432, dbname=kingbase, user=kingbase, password=123456`（仅在没有以上任何环境变量时使用）
  - 注：KingbaseES 手册中环境变量可能写作 `KINGBASE_HOST` 等 KINGBASE 前缀，本 skill **统一使用 PG 前缀环境变量**，不依赖 KINGBASE 前缀。
- 连接账号至少具备目标数据库的 **CONNECT + SELECT on pg_catalog** 权限（只读）。若为 superuser（KingbaseES 无 `pg_monitor` 角色，用 `rolsuper` 判断），可临时创建 `kbstattuple` 扩展获得精确膨胀值；否则自动降级为估算公式，全程不要求写权限。
  - 注意：Python 脚本默认**不**自动创建扩展（只读优先），需加 `--create-extension` 才会在缺扩展且为 superuser 时尝试 `CREATE EXTENSION kbstattuple;`。
- 全程只读诊断，**不会**自动执行 VACUUM FULL / REINDEX / sys_repack / sys_squeeze 等修复操作，只输出建议。

## 工作流程

### Step 1：解析连接信息并测试连通性

用解析出的连接参数测试连通性，并记录版本：

```sql
select version(), current_setting('server_version_num')::int, pg_is_in_recovery();
```

- 若连接失败，检查报错（网络不通/认证失败/pg_hba.conf 限制/权限不足），如实告知用户，不要猜测修复。
- 记录 `server_version_num`（KES V9R1C10 约为 120001，即 PG 12 兼容模式），确认诊断 SQL 的字段兼容性。
- 确认当前账号是否 superuser：`select rolsuper from pg_roles where rolname = current_user;`（KingbaseES 用 `rolsuper`，无 `pg_monitor`）。

### Step 2：列出所有数据库

```sql
select datname from pg_database
where datistemplate = false
  and datallowconn = true
order by datname;
```

- 默认排除 `template0`、`template1`。是否包含 `kingbase`（维护库）由用户数据决定，默认包含。
- 对每个数据库分别建立连接（`-d <dbname>` 或 Python 中切换 dbname），逐库执行 Step 3~6。
- 注意：`sys_stat_statements` 等 KINGBASE 前缀视图是实例级但需在目标库内查询；本 skill 只用 PG 前缀的 `pg_stat_*` 视图，与库无关。

### Step 3：检测精确膨胀能力（kbstattuple）

```sql
select exists (select 1 from pg_extension where extname = 'kbstattuple') as has_kbstattuple;
```

- 若未安装且当前账号为 superuser，尝试：
  ```sql
  create extension if not exists kbstattuple;
  ```
- 若无权限安装，或用户明确要求"不要修改实例"，则自动降级到 **估算公式**（`scripts/table_bloat_estimate.sql` 和 `scripts/index_bloat_estimate.sql`），并在最终报告中注明"本次数据为估算值，非精确值"。
- 两种模式二选一，脚本见 `scripts/` 目录：
  - 精确模式：`scripts/table_bloat_kbstattuple.sql`、`scripts/index_bloat_kbstattuple.sql`
  - 估算模式：`scripts/table_bloat_estimate.sql`、`scripts/index_bloat_estimate.sql`
  - psql 路径可用 `psql -d <dbname> -f scripts/xxx.sql` 逐库执行；Python 路径自动逐库遍历（`-d` 指定单库），并可通过 `--mode exact/estimate` 强制模式、`--min-size-mb` 调整最小分析大小。
- 若实例上既没有 `kbstattuple` 也没有安装权限，且用户希望精确值，可提示两个备选：
  - KingbaseES 的 `sys_recovery` 扩展（`CREATE EXTENSION sys_recovery;`）可读取单表死元组详情；
  - 或安装后对比 `sys_squeeze`/`sys_repack` 整理前后的 `pg_relation_size` 得到精确回收量（见 Step 8）。

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
- 必须排除 KingbaseES 系统 schema：`sys_catalog`、`sysaudit`、`sysmac`、`sys_hm` 等 `sys_` 前缀 schema（脚本已内置排除），避免系统表误报。

### Step 5：应用危害阈值（经验值，可被用户覆盖）

综合业界常见运维经验（膨胀绝对大小 + 膨胀比例双维度判定，避免只看比例导致"小表大惊小怪"、只看绝对值导致"大表膨胀 5% 被忽略"）：

| 危害程度 | 判定条件（满足任一即可） | 典型含义 |
|---------|--------------------------|----------|
| 🔴 高危 | `bloat_ratio ≥ 40%` 或 `bloat_size ≥ 5GB` | 严重浪费磁盘/IO，通常伴随查询变慢、顺序扫描成本上升，建议尽快处理 |
| 🟡 中危 | `20% ≤ bloat_ratio < 40%` 或 `1GB ≤ bloat_size < 5GB` | 需要纳入观察名单，安排在业务低峰处理 |
| 🟢 低危/正常 | `bloat_ratio < 20%` 且 `bloat_size < 1GB` | 属正常范围，MVCC 机制下的正常空间放大，通常无需干预 |

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
  - 表高危 + 无外键/低频访问 → `VACUUM FULL public.xxx;`（需业务窗口，会锁表）或优先推荐 `sys_repack -t public.xxx`（在线重整，无长时间锁）
  - 表中危 → 先 `VACUUM (VERBOSE, ANALYZE) public.xxx;` 观察下次采集是否好转，同时检查 `autovacuum` 参数（`autovacuum_vacuum_scale_factor`、`autovacuum_naptime`）是否过于宽松
  - 索引膨胀（不论高中危）→ 优先 `REINDEX INDEX CONCURRENTLY public.idx_xxx;`（实测 KingbaseES 支持，不阻塞读写，但不能在事务块内执行）；如需物理排序，也可用 `sys_repack --index`
  - 若同一张表的表膨胀和其若干索引均处于高危，建议一并处理（先 `sys_repack -t` 表本身即会重建索引，比逐个 `REINDEX` 更高效）

### Step 8：总结与后续建议

在所有数据库表格之后，输出一段总结，须包含：

1. **总体画像**：本次巡检的数据库数量、检出高危对象数、中危对象数、预计可回收总空间（各库 `bloat_size` 求和）。
2. **根因初判**：结合观察到的模式给出可能原因，例如：
   - 某些库普遍膨胀 → 排查 `autovacuum` 是否被全局关闭或参数过松（`show autovacuum;`、`select * from pg_stat_user_tables where relname='xxx';` 看 `last_autovacuum` 时间）
   - 长事务导致膨胀 → 检查是否存在长时间未提交事务或复制槽阻塞 VACUUM 回收：
     ```sql
     select pid, state, now()-xact_start as duration, left(query, 100) as query
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
4. **风险提示**：`VACUUM FULL` 与 `REINDEX`（非 CONCURRENTLY 模式）会对表加排他锁，明确提醒用户务必在业务低峰执行，并提前评估锁等待对业务的影响；生产环境优先推荐 `sys_repack` / `REINDEX INDEX CONCURRENTLY` / `sys_squeeze` 等在线方案。

## 使用附带脚本

两种执行方式等价，产出相同的诊断数据：

```bash
# 方式一：psql shell（推荐，依赖 psql/ksql）
export PGPASSWORD='123456'
./scripts/run_query.sh -h 127.0.0.1 -p 5432 -U kingbase -d kingbase \
  -f scripts/table_bloat_kbstattuple.sql
# 或单条 SQL：./scripts/run_query.sh -h 127.0.0.1 -U kingbase -d kingbase -c "select 1;"
# 脚本会自动读取 PGHOST/PGPORT/PGDBNAME/PGUSER/PGPASSWORD 环境变量，未提供时用内置默认值

# 方式二：Python SDK（依赖 psycopg2）
python3 scripts/kingbase_find_bloat.py --format markdown
# 同样支持环境变量回退与内置默认值；详见脚本 --help
# 常用选项：
#   --mode estimate    强制估算模式（不探测/不创建 kbstattuple）
#   --create-extension 缺 kbstattuple 且为 superuser 时自动 CREATE EXTENSION（默认不自动建，只读优先）
#   -d <dbname>        只巡检指定库；默认遍历实例下全部业务库
#   --min-size-mb <n>  调整最小分析对象大小（默认 8MB，psql 路径脚本内为固定 8MB）
```

- 两个脚本的**连接参数解析优先级完全一致**：命令行参数 > `PGHOST`/`PGPORT`/`PGDBNAME`/`PGUSER`/`PGPASSWORD` 环境变量 > 内置默认值（127.0.0.1:5432, kingbase/kingbase/123456）。
- 密码优先通过环境变量 `PGPASSWORD` 传递，不落盘、不出现在日志中；Python 脚本的 `-W/--password` 仅作为最后手段，明确优先使用环境变量。

## Pitfalls & Solutions

| 坑点 | 现象 | 解决方案 |
|------|------|----------|
| 误用 `pgstattuple` 扩展 | `function pgstattuple(oid) does not exist` | KingbaseES 没有 pgstattuple，改用 KingbaseES 自带的 `kbstattuple` 扩展（`CREATE EXTENSION kbstattuple;`），函数名 `kbstattuple()`/`kbstatindex()`，字段与 PG 完全一致 |
| `round(double precision, integer)` 不存在 | `function round(double precision, integer) does not exist` | KingbaseES 的 `round()` 只有 `(numeric, integer)` 重载；所有 `round(xxx, 1)` 显式写 `round((xxx)::numeric, 1)`，本 skill 的 SQL 已统一处理 |
| `pg_stat_user_indexes.last_idx_scan` 不存在 | `column s.last_idx_scan does not exist` | KingbaseES 沿用 PG12 早期视图结构，无 `last_idx_scan`；用 `idx_tup_read`/`idx_tup_fetch` 替代 |
| 系统 schema 误报 | `sys_catalog`/`sysaudit`/`sysmac`/`sys_hm` 等系统表出现在膨胀清单 | 巡检时排除 `sys_` 前缀 schema（脚本已内置 `nspname not like 'sys\_%'`），并排除 `pg_catalog`/`information_schema` |
| 无 superuser 权限 | 无法安装 `kbstattuple`，精确模式不可用 | 自动降级为估算模式，并在报告中明确标注"估算值"；KingbaseES 无 `pg_monitor` 角色，权限判断用 `rolsuper` |
| 统计信息过期 | 估算模式下膨胀比例算出负数或明显失真 | 采集前对目标库执行 `ANALYZE;`（只读性质，不锁表），再重新采集 |
| 分区表 | 父表本身 `reltuples`/`relpages` 通常为 0，容易被误判为"无膨胀" | 对分区表遍历其所有子分区（`pg_inherits`），按子分区分别计算，父表本身跳过判定 |
| 超大库/超多表导致采集耗时长 | 全库全表扫描 `kbstattuple` 在大表上代价高 | 精确模式对 >10GB 的大表先用估算公式粗筛，仅对进入候选名单的表再跑 `kbstattuple` 精确核实 |
| 复制槽/长事务阻塞 VACUUM | 表怎么整理都很快重新膨胀 | 先用 Step 8 中的 SQL 排查长事务与复制槽，根因不解决，整理只是治标 |
| `REINDEX CONCURRENTLY` 报错 | `REINDEX CONCURRENTLY cannot run inside a transaction block` | KingbaseES 的 REINDEX CONCURRENTLY 与 PG 一致，不能放在事务块内执行；建议类文本要明确说明 |
| 连接串含明文密码 | 日志/报告中泄露密码 | 输出报告和过程日志中一律对连接串做脱敏处理，只展示 host/port/dbname，不回显 password |

## 注意事项

- **只读原则**：本技能本身不执行任何写操作（除非用户明确同意临时创建 `kbstattuple` 扩展），不会代替用户执行 `VACUUM FULL`/`REINDEX`/`sys_repack`/`sys_squeeze`，所有修复动作均以"建议"形式呈现，交由用户决策执行时机。
- **密码脱敏**：连接串中的密码信息不得出现在最终输出的报告、日志或任何持久化文件中。
- **版本兼容**：KingbaseES 基于 PG 12 兼容模式（`server_version_num` ≈ 120001），本 skill 的 SQL 已针对该版本验证；如目标为其他 KES 大版本（V8R6 等），执行前先确认版本号，必要时调整脚本字段。
- **大小阈值可调**：Step 5 中的经验阈值是通用默认值，如用户对存储成本/IO 更敏感（如云盘按量付费），应主动询问是否需要调低阈值。
- **排他锁风险**：任何"建议"中涉及非 CONCURRENTLY 的整理操作，必须在建议文本中同时标注锁风险与推荐执行时段。
