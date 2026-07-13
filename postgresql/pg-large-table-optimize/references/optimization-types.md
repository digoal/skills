# 负载类型判定与优化模板（阶段 3）

判定顺序：先检查是否同时满足两类以上条件 → 归为 E；否则按 A→B→C→D 顺序匹配第一个满足的类型。所有类型的前提都是「真实大小（修正膨胀后）> 10GB」，类型 D 额外要求 > 50GB。

## 类型 A：高频 UPDATE/DELETE 活跃大表

**判定**：更新比率 > 40% 或 DML 密度 > 0.5。

**核心问题**：死元组产生快，autovacuum 追不上，freeze 开销随表增大而上升，可能触发 wraparound 保护性 autovacuum。

**优化建议模板**：

1. **分区改造**：按业务逻辑键（非频繁更新的列，如 `tenant_id`、状态维度、时间维度）水平分区，使 vacuum/freeze 可按分区独立进行。分区键推荐逻辑：
   - 若表有 `created_at`/`updated_at` 且更新集中在近期数据 → 按时间范围分区，历史分区自然趋于只读，vacuum 压力下降。
   - 若表有明显的租户/业务线字段且各分区更新独立 → 按该字段做 LIST 分区。
   - 若统计信息无法支撑判断 → 标注「需与业务方确认分区键」，不要臆断字段语义。
2. **autovacuum 参数评估**：对比该表当前 DML 速率与默认 `autovacuum_vacuum_scale_factor`(0.2)/`autovacuum_vacuum_threshold`(50) 是否匹配，若死元组增长远快于默认阈值触发频率，建议对该表单独设置更激进参数：
   ```sql
   ALTER TABLE schema.table SET (
     autovacuum_vacuum_scale_factor = 0.05,
     autovacuum_vacuum_cost_limit = 2000
   );
   -- 仅作为建议 SQL 呈现，不代表已执行
   ```
3. **HOT 更新效率**：若 HOT 更新效率低（<50%），说明更新的列上有索引导致无法走 HOT 更新，建议：
   - 检查是否有可以删除的冗余索引；
   - 或调整 `fillfactor`（如设为 70~80）为行内更新预留空间，提升 HOT 命中率：
     ```sql
     ALTER TABLE schema.table SET (fillfactor = 75);
     -- 需要一次 VACUUM FULL 或表重写才能对存量数据生效，建议在维护窗口执行
     ```
4. 若分区改造代价过高（如大量外键依赖、应用层改造成本高），替代方案：定期 `pg_repack`（在线重组，无需长时间锁表）或 `pg_squeeze`（Percona 方案，同理），而非 `VACUUM FULL`（会长时间持锁）。

## 类型 B：高频 INSERT ONLY / 写入为主大表

**判定**：写入比率 > 80%，更新+删除极少。

**核心问题**：数据只增不减，历史数据查询频率低但仍占用空间和缓存，全表扫描/索引维护代价随时间递增。

**优化建议模板**：

1. **按时间维度分区**：推荐使用 `created_at` 或等效业务时间字段做 RANGE 分区，按日/月/年（依据数据增长速率选择粒度——日增千万级选日分区，日增十万级选月分区）：
   ```sql
   -- 示例模板，字段名与粒度需按实际业务确认
   CREATE TABLE schema.table_y2026m07 PARTITION OF schema.table
     FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
   ```
2. **历史归档策略**：对超过 N 个月（默认建议 N=6，需与业务方确认保留策略）的分区：
   ```sql
   ALTER TABLE schema.table DETACH PARTITION schema.table_y2025m01;
   -- detach 后可 ALTER TABLE ... SET TABLESPACE 迁移到冷存储表空间，
   -- 或导出后 DROP，具体取决于合规/审计对历史数据的保留要求
   ```
3. 若已是分区表但单分区仍 > 10GB，建议细分粒度（如月分区改周分区）。
4. **写入热点**：最后一个分区往往是插入并发瓶颈，评估：
   - 是否可用 `INSERT ... ON CONFLICT DO NOTHING/UPDATE` 减少应用层先查后插的往返；
   - 索引数量是否过多拖慢插入吞吐，评估是否有非必要索引可延迟到批处理时段再建。

## 类型 C：OLTP 点查大表

**判定**：索引使用率 > 70%，每次索引扫描平均行数 < 100。

**核心问题**：数据量大导致 B-Tree 层级深，点查需要更多次随机 IO。

**优化建议模板**：

1. **索引瘦身**（针对标记「索引偏深」的索引，估算层高 > 3）：
   - 部分索引：若查询总带某个过滤条件（如 `WHERE status = 'active'`），只对该子集建索引，缩小索引体积：
     ```sql
     CREATE INDEX CONCURRENTLY idx_table_active
       ON schema.table (key_col) WHERE status = 'active';
     ```
   - 覆盖索引（INCLUDE）：将查询常用的输出列放入 INCLUDE，避免回表：
     ```sql
     CREATE INDEX CONCURRENTLY idx_table_covering
       ON schema.table (key_col) INCLUDE (col_a, col_b);
     ```
   - Hash 索引：若查询全部是等值匹配（无范围查询），PG 10+ 的 Hash 索引比 B-Tree 更紧凑：
     ```sql
     CREATE INDEX CONCURRENTLY idx_table_hash ON schema.table USING hash (key_col);
     ```
2. **BRIN 索引**：若表的物理存储顺序与索引键强相关（如按插入时间自然排序的日志表），BRIN 体积远小于 B-Tree：
   ```sql
   CREATE INDEX CONCURRENTLY idx_table_brin ON schema.table USING brin (created_at);
   ```
3. **应用层卸载**：评估 pgbouncer 事务级连接池是否已启用（减少连接开销）+ 应用层 Redis 缓存热点点查结果，降低对数据库的直接点查压力。所有 `CREATE INDEX` 建议使用 `CONCURRENTLY` 避免锁表，但仍需业务低峰期执行并监控进度。

## 类型 D：分析型负载大表

**判定**：顺序扫描占比 > 60%，每次顺序扫描行数大，索引使用率低，真实大小 > 50GB。

**核心问题**：大规模顺序扫描，IO 带宽成为瓶颈，单机行存架构对聚合类查询效率低。

**优化建议模板**：

1. **列存储评估**：若该表主要用于报表/聚合分析（非点查），评估 `cstore_fdw`（Citus 列存扩展）或 Citus 分布式列存方案，可显著降低扫描 IO；需要评估迁移成本和是否有实时写入需求（列存对高频写入不友好）。
2. **物化视图**：对固定的聚合查询模式（如按天/按维度汇总），创建物化视图并用 `pg_cron` 或外部调度定时刷新：
   ```sql
   CREATE MATERIALIZED VIEW schema.mv_table_daily_summary AS
     SELECT date_trunc('day', created_at) AS day, count(*), sum(amount)
     FROM schema.table GROUP BY 1;
   -- 定时 REFRESH MATERIALIZED VIEW CONCURRENTLY schema.mv_table_daily_summary;
   ```
3. **只读副本卸载**：将分析类查询路由到只读备库（Streaming Replication Standby），避免与主库 OLTP 负载争抢 CPU/IO；需确认已有只读副本，若无则需先评估新增副本的成本。
4. **分区裁剪**：若分析查询通常带时间过滤条件，按时间分区可让优化器跳过无关分区（Partition Pruning），大幅减少实际扫描的数据量。
5. **work_mem 评估**：分析查询常涉及大排序/哈希聚合，若执行计划显示磁盘溢出（`Sort Method: external merge`），建议评估调高该类查询会话级 `work_mem`（而非全局调整，避免并发下内存耗尽）：
   ```sql
   SET work_mem = '256MB';  -- 会话级，针对特定分析查询
   ```

## 类型 E：混合型负载大表

**判定**：同时具备 A/B/C/D 中两种以上特征。

**处理方式**：

1. 在报告中明确列出该表同时具备的多种特征（如「既有高频更新又有大量分析型顺序扫描」）。
2. 优先级排序：**先解决膨胀和索引问题（成本低、见效快、风险小）**，再考虑分区改造（成本高、需业务配合、有一定风险，需评估执行窗口和回滚方案）。
3. 若 A+D 混合（高频更新 + 分析扫描）尤其需要提示：直接在主表跑分析查询会加剧与 OLTP 更新的争抢，只读副本卸载优先级应提高。
