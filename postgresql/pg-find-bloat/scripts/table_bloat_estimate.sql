-- 降级估算模式：不依赖 pgstattuple 扩展，适用于无 superuser 权限的场景
-- 原理：用 pg_stats 中各列的平均宽度之和估算单行理论大小（含 24 字节元组头 + 15% 页填充/对齐余量），
-- 与 pg_relation_size 得到的实际大小比较，差值即为粗略膨胀估算
-- 注意：这是粗略估算，非精确值；统计信息过期（未 ANALYZE）会显著影响准确性，
-- 使用前建议先对目标库执行一次 ANALYZE（只读性质，不加锁）

with column_stats as (
    select
        schemaname,
        tablename,
        sum(avg_width) as avg_row_width
    from pg_stats
    where schemaname not in ('pg_catalog', 'information_schema')
    group by schemaname, tablename
),
table_info as (
    select
        n.nspname as schema_name,
        c.relname as object_name,
        c.oid,
        c.reltuples,
        pg_relation_size(c.oid) as real_size
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where c.relkind = 'r'
      and n.nspname not in ('pg_catalog', 'information_schema')
      and pg_relation_size(c.oid) >= 8 * 1024 * 1024
)
select
    current_database() as database,
    ti.schema_name,
    ti.object_name,
    'table'::text as object_type,
    ti.reltuples::bigint as row_estimate,
    ti.real_size,
    greatest(
        round(ti.real_size - ti.reltuples * (coalesce(cs.avg_row_width, 100) + 24) * 1.15),
        0
    )::bigint as bloat_size,
    round(
        greatest(
            ti.real_size - ti.reltuples * (coalesce(cs.avg_row_width, 100) + 24) * 1.15,
            0
        ) / nullif(ti.real_size, 0) * 100,
        1
    ) as bloat_ratio
from table_info ti
left join column_stats cs
    on cs.schemaname = ti.schema_name and cs.tablename = ti.object_name
order by bloat_size desc;
