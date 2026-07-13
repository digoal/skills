-- 需要已安装 pgstattuple 扩展：create extension if not exists pgstattuple;
-- 精确计算每张表的死元组占比 + 空闲空间占比，得到膨胀大小与膨胀比例
-- 已过滤实际大小 < 8MB 的表，避免小表噪音

select
    current_database()                                            as database,
    n.nspname                                                      as schema_name,
    c.relname                                                       as object_name,
    'table'::text                                                   as object_type,
    coalesce(s.n_live_tup, 0)                                       as row_estimate,
    pg_relation_size(c.oid)                                         as real_size,
    round(
        pg_relation_size(c.oid)::numeric
        * (pgst.dead_tuple_percent + pgst.free_percent) / 100
    )::bigint                                                       as bloat_size,
    round((pgst.dead_tuple_percent + pgst.free_percent)::numeric, 1) as bloat_ratio
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_user_tables s on s.relid = c.oid
cross join lateral pgstattuple(c.oid) as pgst
where c.relkind = 'r'
  and n.nspname not in ('pg_catalog', 'information_schema')
  and pg_relation_size(c.oid) >= 8 * 1024 * 1024
order by bloat_size desc;
