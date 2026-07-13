# 检查项 → 风险等级 / 扣分映射表

本表用于将 `scripts/queries/*.sql` 各查询产出的 `issue` 标记，映射到报告要求的三级风险，
并作为综合健康评分的扣分依据（🔴 高危 -10 分/项，🟡 警告 -3 分/项，🔵 建议 -1 分/项）。
"项"以单条记录（如一个表、一个字段、一个索引）为单位计数。

## 🔴 高危风险（每项 -10 分）

| issue 标记 | 来源脚本 | 说明 |
|---|---|---|
| `missing_primary_key` | 06 | 缺少主键的表，无法保证行唯一性，影响复制/去重/ORM 行为 |
| `money_uses_float` | 02 | 金额字段用 float/real，存在精度丢失风险，涉及资金正确性 |
| `pk_fk_uses_varchar` | 02 | 主键/外键使用 varchar，join 性能与索引效率显著下降 |
| `large_table` 且 `is_partitioned = false` | 04 | 超大表未分区，直接影响查询性能、维护窗口、VACUUM 效率 |
| `too_many_partitions` | 04 | 分区数超过 100，规划器开销与元数据膨胀风险 |
| `exact_duplicate_index` | 05 | 完全重复索引，浪费存储且拖慢写入，无任何收益 |

## 🟡 警告风险（每项 -3 分）

| issue 标记 | 来源脚本 | 说明 |
|---|---|---|
| `redundant_prefix_index` | 05 | 冗余最左前缀索引，增加维护成本 |
| `fk_without_index` | 06 | 外键未建索引，级联删除/更新与 join 性能受影响 |
| `unused_index` | 05 | 长期零扫描索引，占用存储与写入开销（需结合 stats_reset 复核） |
| `wide_composite_index` | 05 | 组合索引宽度过大，写入放大、B-Tree 深度增加 |
| `bool_stored_as_wrong_type` | 02 | 布尔语义字段类型不当，查询可读性与优化器统计不准 |
| `time_stored_as_string` | 02 | 时间语义字段用字符串存储，无法使用时间函数与范围索引 |
| `json_stored_as_string` | 02 | JSON 语义字段未用 jsonb，丧失 GIN 索引与 JSON 操作符能力 |
| `missing_audit_timestamp` | 06 | 缺少 created_at/updated_at，影响审计与增量同步 |
| `non_default_isolation_level` | 07 | 非 read committed 隔离级别，需确认业务是否真正需要 |
| `large_table` 且 `is_partitioned` 为 `NULL`（子分区自身超1GB）| 04 | 单个分区过大，可能需要二级分区或调整分区键 |

## 🔵 建议优化（每项 -1 分）

| issue 标记 | 来源脚本 | 说明 |
|---|---|---|
| `suspicious_name` / `suspicious_column_name` / `suspicious_index_name` | 01 | 命名不规范，影响可维护性与团队协作 |
| `missing_object_comment` / `missing_column_comment` | 03 | 缺少注释，新人理解成本高 |
| `unbounded_or_overused_text` | 02 | varchar 无长度约束或 text 滥用，缺少输入长度校验 |
| `ip_not_inet` | 02 | IP 字段未用 inet 类型，丧失网段运算与存储压缩优势 |
| `table_created_directly_in_public_schema` | 07 | public 模式建表，多租户/多应用场景下命名空间隔离不足 |
| `nullable_but_likely_required` | 06 | 业务关键字段允许 NULL，需人工确认是否应加 NOT NULL |

## 特殊标记（不直接计分，需人工复核，仅作为报告附注）

| issue 标记 | 处理方式 |
|---|---|
| `unused_unique_or_pk_index_review_needed` | 标注"需人工复核"，不计入 unused_index 扣分，因其承担约束语义 |
| `db_level_isolation_override_review_needed` | 标注"需人工复核" |
| `public_schema_open_create_review_needed` | 若 `public_role_can_create = true`，按 🔵 建议优化计 1 项；PG15+ 默认已收紧此权限，需结合版本判断 |

## 注释缺失率标红规则

数据库注释缺失率 = `columns_without_comment / total_columns`（来自 `03_comments.sql` 第 3 项汇总结果）。
若该比例 > 30%，除按上表对每个缺失注释的对象/字段计 🔵 -1 分外，额外在报告该数据库分区标注
"⚠️ 注释缺失率 XX%，超过 30% 阈值"的标红提示（不重复扣分，仅做视觉强调）。
