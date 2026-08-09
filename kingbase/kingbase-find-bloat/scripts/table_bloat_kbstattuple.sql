-- KingbaseES 精确模式：需要已安装 kbstattuple 扩展：
--   create extension if not exists kbstattuple;
-- kbstattuple(oid) 返回字段与 PG 的 pgstattuple 完全一致（table_len, dead_tuple_percent, free_percent ...）
-- 精确计算每张表的死元组占比 + 空闲空间占比，得到膨胀大小与膨胀比例
-- 已过滤实际大小 < 8MB 的表，避免小表噪音；已排除 KingbaseES 系统 schema（sys_ 前缀）
-- 注意：KingbaseES 无 round(double precision, integer) 重载，所有 round(x, 1) 均显式 cast 为 numeric

select
    current_database()                                            as database,
    n.nspname                                                      as schema_name,
    c.relname                                                       as object_name,
    'table'::text                                                   as object_type,
    coalesce(s.n_live_tup, 0)                                       as row_estimate,
    pg_relation_size(c.oid)                                         as real_size,
    round(
        pg_relation_size(c.oid)::numeric
        * (kbt.dead_tuple_percent + kbt.free_percent) / 100
    )::bigint                                                       as bloat_size,
    round((kbt.dead_tuple_percent + kbt.free_percent)::numeric, 1)  as bloat_ratio
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_user_tables s on s.relid = c.oid
cross join lateral kbstattuple(c.oid) as kbt
where c.relkind = 'r'
  and n.nspname not in ('pg_catalog', 'information_schema', 'pg_toast')
  and n.nspname not like 'sys\_%'
  and pg_relation_size(c.oid) >= 8 * 1024 * 1024
order by bloat_size desc;
